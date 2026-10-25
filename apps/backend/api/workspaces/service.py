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
from botocore.exceptions import ClientError, ReadTimeoutError
from fastapi import HTTPException

from api.writing.models import WritingSource
from api.workspaces.files import ProjectFiles, now, validate_path
from api.workspaces.html_documents import html_selection, is_html_path
from api.workspaces.jobs import JobHeartbeat, job_is_stale
from api.workspaces.proposals import create_proposal, utf16_offset
from api.workspaces.research_context import snapshot_context
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
        # The agent replies within its 720 s deadline; AgentCore ends a
        # synchronous request at 15 minutes.
        config=Config(connect_timeout=10, read_timeout=930, retries={"max_attempts": 0}),
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
                   and value["status"] in {"running", "queued"} and not job_is_stale(value, now())]
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
        if is_html_path(request.activePath):
            try:
                resolved = html_selection(active["content"], request.selection.nodeId)
            except ValueError as error:
                raise HTTPException(409, str(error)) from error
            if any(selection[key] != resolved[key] for key in ("start", "end", "text")):
                raise HTTPException(409, "선택 내용이 HTML 요소 전체와 다릅니다. 다시 선택해 주세요.")
            selection["nodeId"] = resolved["nodeId"]
        elif request.selection.nodeId is not None:
            raise HTTPException(422, "HTML 영역 ID는 HTML 문서에서만 사용할 수 있습니다.")
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
        context_paths = request.contextPaths
        if context_paths is None:
            context_paths = [request.activePath] if request.activePath else []
        payload["projectContext"] = snapshot_context(files, context_paths)
        job["contextPaths"] = [item["path"] for item in payload["projectContext"]]
        job["truncatedContextPaths"] = [
            item["path"] for item in payload["projectContext"] if item["truncated"]
        ]
    if request.outputFormat:
        payload["outputFormat"] = request.outputFormat
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
        timestamp = now()
        if job and job["status"] == "running" and not job_is_stale(job, timestamp):
            job.update(message=status[:500], updatedAt=timestamp)
            files.metadata.put(files.namespace, "job:" + job_id, job)


GENERIC_FAILURE = "에이전트 작업을 완료하지 못했습니다. 원본은 변경되지 않았습니다. 다시 요청해 주세요."
TIME_LIMIT_FAILURE = (
    "요청이 길어 제한 시간 안에 끝나지 않았습니다. 원본은 변경되지 않았습니다. "
    "문서나 범위를 나누어 다시 요청해 주세요."
)


def _failure_detail(error):
    """Service-authored text only: AWS error messages and our own HTTP statuses carry no request data."""
    if isinstance(error, ClientError):
        return ": " + str(error.response.get("Error", {}).get("Message", ""))[:300]
    if isinstance(error, HTTPException):
        return f", status={error.status_code}"
    return ""


def failure_reason(error):
    """The message persisted on a failed job and shown in the workspace chat."""
    from api.workspaces.research import ResearchError

    if isinstance(error, ResearchError):
        return str(error)
    # Our HTTP details are written for people and carry no request data.
    if isinstance(error, HTTPException) and isinstance(error.detail, str):
        return error.detail
    if isinstance(error, ReadTimeoutError) or (
        isinstance(error, ClientError)
        and "initialization time exceeded" in str(error.response.get("Error", {}).get("Message", ""))
    ):
        return TIME_LIMIT_FAILURE
    return GENERIC_FAILURE


def run_job(owner, workspace, job_id, payload):
    files = ProjectFiles(owner, workspace)
    heartbeat = None
    claimed = False
    try:
        with files.lock():
            files.require()
            job = files.metadata.get(files.namespace, "job:" + job_id)
            if not job or job["status"] != "queued" or job_is_stale(job, now()):
                return
            job.update(status="running", updatedAt=now())
            files.metadata.put(files.namespace, "job:" + job_id, job)
            claimed = True
        heartbeat = JobHeartbeat(files, job_id)
        heartbeat.start()
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
        if payload.get("outputFormat") == "html" and any(
            not isinstance(edit, dict) or not isinstance(edit.get("path"), str)
            or not edit["path"].lower().endswith(".html")
            or edit.get("baseVersion") is not None or edit.get("baseContent") != ""
            for edit in edits
        ):
            raise ValueError("HTML generation must propose new .html files")
        proposals = [create_proposal(
            edit, job_id, payload["message"], list(combined.values()), payload.get("selection"),
        ) for edit in edits]
        with files.lock():
            job = files.metadata.get(files.namespace, "job:" + job_id)
            if not job or job["status"] != "running" or job_is_stale(job, now()):
                return
            if payload.get("outputFormat") == "html" and any(
                files.read(proposal["path"], missing=True) is not None for proposal in proposals
            ):
                raise ValueError("HTML generation cannot target an existing file")
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
        logger.warning("Workspace job failed (%s%s)", type(error).__name__, _failure_detail(error))
        reason = failure_reason(error)
        try:
            with files.lock():
                job = files.metadata.get(files.namespace, "job:" + job_id)
                if claimed and job and job["status"] == "running":
                    job.update(status="failed", updatedAt=now(), error=reason)
                    files.metadata.put(files.namespace, "job:" + job_id, job)
        except Exception:
            logger.error("Could not persist workspace job failure")
    finally:
        if heartbeat is not None:
            heartbeat.stop()
