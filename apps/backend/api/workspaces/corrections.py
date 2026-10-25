"""Full proposal copies and immutable before/after records for later comparison."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import PurePosixPath

from fastapi import HTTPException

from api.workspaces import files as storage
from api.workspaces.persistence import write_json


def _record_path(files, path):
    storage.validate_path(path)
    return files.safe(files.internal / "corrections" / f"{hashlib.sha256(path.encode()).hexdigest()}.json")


def correction_for(files, path):
    target = _record_path(files, path)
    return json.loads(target.read_bytes()) if target.exists() else None


def record_copy(files, record):
    write_json(_record_path(files, record["path"]), record)


def _copy_path(proposal, created_at):
    source = PurePosixPath(proposal["path"])
    stamp = datetime.fromtimestamp(created_at / 1000, timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = f".교정본-{stamp}-{proposal['id'][:8]}{source.suffix}"
    parent = "" if source.parent == PurePosixPath(".") else f"{source.parent}/"
    # Keep both the component's byte limit and the complete path's character limit.
    if len(parent) + len(suffix) >= 500:
        parent = ""
    stem = source.stem[:500 - len(parent) - len(suffix)]
    stem = stem.encode("utf-8")[:240 - len(suffix.encode("utf-8"))].decode("utf-8", errors="ignore")
    return storage.validate_path(parent + stem + suffix)


def save_proposal_copy(files, proposal_id):
    """Caller holds the project lock; retries return the original copy as it is now."""
    proposal = files.proposal(proposal_id)
    if proposal["baseVersion"] is None:
        raise HTTPException(422, "새 문서 제안은 변경 승인으로 저장해 주세요.")
    if saved := proposal.get("savedCopy"):
        return {"proposal": proposal, "file": files.read(saved["path"])}
    created_at = storage.now()
    path = _copy_path(proposal, created_at)
    if files.read(path, missing=True) is not None:
        raise HTTPException(409, "같은 이름의 파일이 있습니다. 잠시 후 교정본 저장을 다시 시도해 주세요.")
    record = {
        "proposalId": proposal_id, "sourcePath": proposal["path"], "path": path,
        "createdAt": created_at, "baseContent": proposal["baseContent"],
        "proposedContent": proposal["proposedContent"],
    }
    next_proposal = {**proposal, "savedCopy": {"path": path, "createdAt": created_at}}
    journal = files.safe(files.internal / "approval.json")
    write_json(journal, {
        "copy": record, "proposal": next_proposal, "previousVersion": None,
        "targetVersion": storage.version(record["proposedContent"]),
    })
    saved_file = files.save(path, record["proposedContent"], None, "전체 교정본 저장")
    record_copy(files, record)
    files.put_proposal(next_proposal)
    journal.unlink()
    return {"proposal": next_proposal, "file": saved_file}
