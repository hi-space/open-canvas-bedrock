"""Same-origin workspace API; each endpoint verifies identity and ownership."""
import os
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from api.workspaces.files import ProjectFiles, now
from api.workspaces.corrections import correction_for, save_proposal_copy
from api.workspaces.identity import owner_key
from api.workspaces.jobs import job_is_stale
from api.workspaces.models import CreateWorkspace, SaveFile, ChatRequest, Decisions, SourceInput
from api.workspaces.proposals import apply_decisions
from api.workspaces.service import prepare_job, run_job
from api.workspaces.sources import SourceLibrary

router = APIRouter()


@router.get("")
def list_workspaces(owner=Depends(owner_key)):
    files = ProjectFiles(owner)
    with files.lock():
        workspaces = list(files.metadata.items(files.owner_namespace).values())
    return {"workspaces": sorted(workspaces, key=lambda item: item["createdAt"]),
            "storage": os.environ.get("WORKSPACE_STORAGE_MODE", "local")}


@router.post("")
def create_workspace(body: CreateWorkspace, owner=Depends(owner_key)):
    files = ProjectFiles(owner)
    with files.lock():
        if len(files.metadata.items(files.owner_namespace)) >= 100:
            raise HTTPException(422, "프로젝트는 최대 100개입니다.")
        workspace = {"id": str(uuid.uuid4()), "name": body.name, "createdAt": now(), "updatedAt": now()}
        project = ProjectFiles(owner, workspace["id"])
        project.safe(project.files).mkdir(parents=True, exist_ok=True)
        files.metadata.put(files.owner_namespace, workspace["id"], workspace)
    return workspace


def authorized(owner, workspace):
    files = ProjectFiles(owner, workspace)
    files.require()
    return files


def expire_job(job):
    if job_is_stale(job, now()):
        return {**job, "status": "failed", "error": "작업 연결이 중단되었습니다. 다시 요청해 주세요."}
    return job


@router.get("/{workspace}")
def snapshot(workspace: str, owner=Depends(owner_key)):
    files = authorized(owner, workspace)
    with files.lock():
        records = files.metadata.items(files.namespace, exclude_prefix="source:")
        return {
            "workspace": files.require(), "files": files.list(),
            "messages": sorted([v for k, v in records.items() if k.startswith("message:")],
                               key=lambda item: item["createdAt"])[-200:],
            "proposals": sorted([v for k, v in records.items() if k.startswith("proposal:")],
                                key=lambda item: item["createdAt"], reverse=True)[:100],
            "jobs": sorted([expire_job(v) for k, v in records.items() if k.startswith("job:")],
                           key=lambda item: item["createdAt"], reverse=True)[:100],
            "sources": SourceLibrary(files).summaries(),
        }


@router.get("/{workspace}/files")
def get_file(workspace: str, path: str = Query(max_length=500), owner=Depends(owner_key)):
    files = authorized(owner, workspace)
    with files.lock():
        return files.read(path)


@router.put("/{workspace}/files")
def save_file(workspace: str, body: SaveFile, owner=Depends(owner_key)):
    files = authorized(owner, workspace)
    with files.lock():
        return files.save(body.path, body.content, body.baseVersion)


@router.get("/{workspace}/history")
def history(workspace: str, path: str = Query(max_length=500), owner=Depends(owner_key)):
    files = authorized(owner, workspace)
    with files.lock():
        return {"revisions": files.history(path), "correction": correction_for(files, path)}


@router.post("/{workspace}/sources")
def add_source(workspace: str, body: SourceInput, owner=Depends(owner_key)):
    files = authorized(owner, workspace)
    with files.lock():
        return SourceLibrary(files).put(body.model_dump(exclude_none=True))


@router.get("/{workspace}/sources/{source_id}")
def read_source(workspace: str, source_id: str, owner=Depends(owner_key)):
    files = authorized(owner, workspace)
    with files.lock():
        return SourceLibrary(files).read(source_id)


@router.delete("/{workspace}/sources/{source_id}")
def remove_source(workspace: str, source_id: str, owner=Depends(owner_key)):
    files = authorized(owner, workspace)
    with files.lock():
        SourceLibrary(files).remove(source_id)
    return {"ok": True}


@router.post("/{workspace}/chat", status_code=202)
def chat(workspace: str, body: ChatRequest, tasks: BackgroundTasks, owner=Depends(owner_key)):
    files = authorized(owner, workspace)
    with files.lock():
        job, payload = prepare_job(files, body)
    if payload is not None:
        tasks.add_task(run_job, owner, workspace, job["id"], payload)
    return {"job": job}


@router.get("/{workspace}/jobs/{job_id}")
def get_job(workspace: str, job_id: str, owner=Depends(owner_key)):
    files = authorized(owner, workspace)
    with files.lock():
        job = files.metadata.get(files.namespace, "job:" + job_id)
        if not job:
            raise HTTPException(404, "작업을 찾을 수 없습니다.")
        return expire_job(job)


@router.get("/{workspace}/proposals/{proposal_id}")
def get_proposal(workspace: str, proposal_id: str, owner=Depends(owner_key)):
    files = authorized(owner, workspace)
    with files.lock():
        return files.proposal(proposal_id)


@router.post("/{workspace}/proposals/{proposal_id}/decisions")
def decide(workspace: str, proposal_id: str, body: Decisions, owner=Depends(owner_key)):
    files = authorized(owner, workspace)
    with files.lock():
        return apply_decisions(files, proposal_id, body.decisions)


@router.post("/{workspace}/proposals/{proposal_id}/copy")
def copy_proposal(workspace: str, proposal_id: str, owner=Depends(owner_key)):
    files = authorized(owner, workspace)
    with files.lock():
        return save_proposal_copy(files, proposal_id)
