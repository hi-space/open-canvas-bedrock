"""Persisted chat jobs and the IAM boundary to AgentCore Runtime."""
import json
import os
import re
import uuid
from urllib.parse import urlsplit
import ipaddress
import logging

import boto3
from botocore.config import Config
from fastapi import HTTPException

from api.writing.models import WritingSource
from api.workspaces.files import ProjectFiles, now, validate_path
from api.workspaces.proposals import create_proposal, utf16_offset
from core.models import get_default_model_name

logger = logging.getLogger(__name__)


def invoke_agent(payload):
    arn = os.environ.get("AGENTCORE_RUNTIME_ARN")
    if not arn:
        if os.environ.get("WORKSPACE_AUTH_MODE") != "local":
            raise RuntimeError("Agent runtime not configured")
        from workspace_agent import run_agent
        return run_agent(payload)
    client = boto3.client(
        "bedrock-agentcore",
        region_name=os.environ.get("AGENTCORE_REGION", "ap-northeast-2"),
        config=Config(connect_timeout=10, read_timeout=600, retries={"max_attempts": 0}),
    )
    response = client.invoke_agent_runtime(
        agentRuntimeArn=arn, runtimeSessionId=str(uuid.uuid4()),
        payload=json.dumps(payload, ensure_ascii=False).encode(),
        contentType="application/json", accept="application/json",
    )
    body = response["response"]
    try:
        data = body.read(12 * 1024 * 1024 + 1)
        if len(data) > 12 * 1024 * 1024:
            raise ValueError("Agent response exceeds limit")
        return json.loads(data)
    finally:
        body.close()


def sources_from(records):
    return [value for key, value in records.items() if key.startswith("source:")]


def within_source_limits(sources):
    return len(sources) <= 50 and sum(len(item.get("excerpt") or "") for item in sources.values()) <= 100000


def prepare_job(files, request):
    mapping_key = "request:" + request.requestId
    previous = files.metadata.get(files.namespace, mapping_key)
    if previous:
        return files.metadata.get(files.namespace, "job:" + previous["jobId"]), None
    records = files.metadata.items(files.namespace)
    active_jobs = [value for key, value in records.items() if key.startswith("job:")
                   and value["status"] in {"running", "queued"} and now() - value["updatedAt"] < 900000]
    if active_jobs:
        raise HTTPException(409, "이 프로젝트에서 에이전트가 작업 중입니다. 완료 후 다시 요청해 주세요.")
    selection = None
    active = None
    if request.activePath:
        validate_path(request.activePath)
        active = files.read(request.activePath)
        if request.activeVersion and active["version"] != request.activeVersion:
            raise HTTPException(409, "문서가 변경되었습니다. 최신 내용을 확인한 뒤 요청해 주세요.")
    if request.selection and request.researchGenre:
        raise HTTPException(422, "딥 리서치는 새 문서를 만듭니다. 문장 선택을 해제한 뒤 요청해 주세요.")
    if request.selection:
        if not active or not request.activeVersion:
            raise HTTPException(422, "선택한 문서의 저장 버전이 필요합니다.")
        start = utf16_offset(active["content"], request.selection.from_)
        end = utf16_offset(active["content"], request.selection.to)
        if start >= end or active["content"][start:end] != request.selection.text:
            raise HTTPException(409, "선택 내용이 문서와 다릅니다. 다시 선택해 주세요.")
        selection = {"path": request.activePath, "start": start, "end": end, "text": request.selection.text}
    history_records = sorted(
        [value for key, value in records.items() if key.startswith("message:")],
        key=lambda item: item["createdAt"],
    )
    history = []
    size = 0
    for message in reversed(history_records[-40:]):
        content = message["content"][:16000]
        if size + len(content) > 64000:
            break
        history.insert(0, {"role": message["role"], "content": content})
        size += len(content)
    job = {
        "id": str(uuid.uuid4()), "status": "queued", "createdAt": now(), "updatedAt": now(),
        "message": "프로젝트 파일을 확인하고 있습니다.", "proposalIds": [],
    }
    if request.researchGenre:
        job.update(kind="research", message="리서치를 계획하고 있습니다.")
    payload = {
        "ownerKey": files.owner, "workspaceId": files.workspace,
        "message": request.message, "model": request.model or get_default_model_name(),
        "history": history, "sources": sources_from(records),
    }
    if request.activePath:
        payload["activePath"] = request.activePath
    if selection:
        payload["selection"] = selection
    if request.researchGenre:
        payload["researchGenre"] = request.researchGenre
    user_message = {
        "id": str(uuid.uuid4()), "role": "user", "content": request.message,
        "createdAt": now(), "jobId": job["id"],
    }
    files.metadata.put(files.namespace, "message:" + user_message["id"], user_message)
    files.metadata.put(files.namespace, "job:" + job["id"], job)
    files.metadata.put(files.namespace, mapping_key, {"jobId": job["id"]})
    return job, payload


def fetch_requested_sources(message, sources):
    """Fetch explicitly supplied URLs outside the private agent VPC."""
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        return []
    existing = {source["url"] for source in sources if source.get("excerpt")}
    urls = list(dict.fromkeys(re.findall(r"https?://[^\s<>\"']+", message)))[:5]
    collected = []
    for candidate in urls:
        url = candidate.rstrip(".,;!)]}")
        try:
            host = (urlsplit(url).hostname or "").lower()
            if not host or host == "localhost" or host.endswith((".local", ".internal")):
                continue
            try:
                if not ipaddress.ip_address(host).is_global:
                    continue
            except ValueError:
                pass
            source_id = "web-" + __import__("hashlib").sha256(url.encode()).hexdigest()[:24]
            source = WritingSource(id=source_id, title=host, url=url)
            if url in existing:
                continue
            from firecrawl import Firecrawl
            result = Firecrawl(api_key=key, timeout=30, max_retries=0).scrape(url, formats=["markdown"])
            if result.markdown:
                source = WritingSource(
                    id=source_id, title=(getattr(result.metadata, "title", None) or host)[:500],
                    url=url, excerpt=result.markdown[:20000],
                )
                collected.append(source.model_dump(exclude_none=True))
        except Exception:
            # No URL, credential or scraped text is copied into logs.
            continue
    return collected


def report_progress(files, job_id, status):
    """Long jobs report each step; the update also keeps the job from expiring as stalled."""
    with files.lock():
        job = files.metadata.get(files.namespace, "job:" + job_id)
        if job and job["status"] == "running":
            job.update(message=status[:500], updatedAt=now())
            files.metadata.put(files.namespace, "job:" + job_id, job)


def run_job(owner, workspace, job_id, payload):
    files = ProjectFiles(owner, workspace)
    try:
        with files.lock():
            files.require()
            job = files.metadata.get(files.namespace, "job:" + job_id)
            job.update(status="running", updatedAt=now())
            files.metadata.put(files.namespace, "job:" + job_id, job)
        fetched = fetch_requested_sources(payload["message"], payload["sources"])
        combined = {source["id"]: source for source in payload["sources"]}
        for source in fetched:
            candidate = {**combined, source["id"]: source}
            if within_source_limits(candidate):
                combined = candidate
        payload["sources"] = list(combined.values())
        if payload.get("researchGenre"):
            from api.workspaces.research import run_research

            with files.lock():
                existing_paths = {item["path"] for item in files.list()}
            result = run_research(payload, existing_paths, lambda status: report_progress(files, job_id, status))
        else:
            result = invoke_agent(payload)
        if not isinstance(result, dict) or not isinstance(result.get("message"), str):
            raise ValueError("Invalid runtime result")
        if not result["message"].strip() or len(result["message"]) > 16000:
            raise ValueError("Invalid assistant message")
        returned_sources = result.get("sources", [])
        if not isinstance(returned_sources, list) or len(returned_sources) > 50:
            raise ValueError("Invalid returned sources")
        for value in returned_sources:
            source = WritingSource.model_validate(value).model_dump(exclude_none=True)
            previous = combined.get(source["id"])
            if previous and previous["url"] != source["url"]:
                raise ValueError("Source identity changed")
            combined[source["id"]] = source
        if not within_source_limits(combined):
            raise ValueError("Returned evidence exceeds source limits")
        edits = result.get("proposals", [])
        if not isinstance(edits, list) or len(edits) > 20:
            raise ValueError("Too many proposals")
        if len({edit.get("path") for edit in edits if isinstance(edit, dict)}) != len(edits):
            raise ValueError("Duplicate file proposals")
        proposals = [create_proposal(
            edit, job_id, payload["message"], list(combined.values()), payload.get("selection"),
        ) for edit in edits]
        with files.lock():
            # A person can edit the source library while the model is running.
            # Keep their latest records and retain the job's evidence in proposals.
            current_sources = {source["id"]: source for source in sources_from(files.metadata.items(files.namespace))}
            for value in [*fetched, *returned_sources]:
                source = WritingSource.model_validate(value).model_dump(exclude_none=True)
                if source["id"] in current_sources:
                    continue
                candidate = {**current_sources, source["id"]: source}
                if source["id"] in combined and within_source_limits(candidate):
                    files.metadata.put(files.namespace, "source:" + source["id"], source)
                    current_sources = candidate
            for proposal in proposals:
                files.put_proposal(proposal)
            message = {
                "id": str(uuid.uuid4()), "role": "assistant", "content": result["message"],
                "createdAt": now(), "jobId": job_id,
            }
            files.metadata.put(files.namespace, "message:" + message["id"], message)
            job.update(
                status="completed", updatedAt=now(), message="작업을 완료했습니다.",
                proposalIds=[proposal["id"] for proposal in proposals],
            )
            files.metadata.put(files.namespace, "job:" + job_id, job)
    except Exception as error:
        logger.warning("Workspace job failed (%s)", type(error).__name__)
        from api.workspaces.research import ResearchError
        reason = (str(error) if isinstance(error, ResearchError)
                  else "에이전트 작업을 완료하지 못했습니다. 원본은 변경되지 않았습니다. 다시 요청해 주세요.")
        try:
            with files.lock():
                job = files.metadata.get(files.namespace, "job:" + job_id)
                if job:
                    job.update(status="failed", updatedAt=now(), error=reason)
                    files.metadata.put(files.namespace, "job:" + job_id, job)
        except Exception:
            logger.error("Could not persist workspace job failure")
