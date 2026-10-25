"""Validated diff proposals; only explicit decisions can update canonical files."""
from copy import deepcopy
from difflib import SequenceMatcher
import uuid

from fastapi import HTTPException

from api.writing.models import WritingRequest, WritingResponse, WritingSource
from api.writing.service import _validate_citations
from api.workspaces.files import now, validate_content, validate_path, version
from api.workspaces.html_documents import (
    html_citation_text, html_source_ids, is_html_path, prepare_html, replace_html_selection, validate_html,
)
from api.workspaces.persistence import write_json


def utf16_offset(text, offset):
    if not isinstance(offset, int) or offset < 0:
        raise HTTPException(422, "문장 선택 범위를 다시 확인해 주세요.")
    encoded = text.encode("utf-16-le")
    if offset * 2 > len(encoded):
        raise HTTPException(422, "문장 선택 범위를 다시 확인해 주세요.")
    try:
        return len(encoded[:offset * 2].decode("utf-16-le"))
    except UnicodeDecodeError:
        raise HTTPException(422, "문자 중간을 선택할 수 없습니다.") from None


def changes_for(before, after):
    groups = []
    active = None
    # Autojunk bounds comparisons for long/repetitive documents.
    for operation, start, end, new_start, new_end in SequenceMatcher(
        None, before, after, autojunk=len(before) > 10000,
    ).get_opcodes():
        if operation == "equal":
            if active and end - start <= 24 and "\n\n" not in before[start:end] and "\r\n\r\n" not in before[start:end]:
                active[1], active[3] = end, new_end
            else:
                if active:
                    groups.append(active)
                active = None
        elif active:
            active[1], active[3] = end, new_end
        else:
            active = [start, end, new_start, new_end]
    if active:
        groups.append(active)
    if len(groups) > 1000:
        groups = [[0, len(before), 0, len(after)]]
    return [{
        "id": f"c{index}",
        "from": len(before[:start].encode("utf-16-le")) // 2,
        "to": len(before[:end].encode("utf-16-le")) // 2,
        "before": before[start:end], "after": after[new_start:new_end], "decision": "pending",
    } for index, (start, end, new_start, new_end) in enumerate(groups)]


def citation_check(before, after, sources, explanation="승인한 변경", *, html_document=False):
    if html_document:
        before, after = html_citation_text(before), html_citation_text(after)
    _validate_citations(
        WritingRequest(document=before, instruction="기존 출처 보존", sources=[
            WritingSource.model_validate(source) for source in sources
        ]),
        WritingResponse(replacement=after, explanation=explanation),
    )


def create_proposal(edit, job_id, instruction, sources, selection=None):
    if not isinstance(edit, dict):
        raise ValueError("Invalid proposal")
    path = validate_path(edit["path"])
    before, after = edit["baseContent"], edit["proposedContent"]
    if not isinstance(before, str) or not isinstance(after, str):
        raise ValueError("Invalid document")
    validate_content(before)
    validate_content(after)
    if edit["baseVersion"] != (version(before) if edit["baseVersion"] is not None else None):
        raise ValueError("Invalid base version")
    if edit["baseVersion"] is None and before:
        raise ValueError("New file has a nonempty base")
    explanation = edit["explanation"]
    if not isinstance(explanation, str) or not explanation.strip() or len(explanation) > 4000:
        raise ValueError("Invalid explanation")
    replacement = None
    prefix = ""
    if selection is not None:
        if path != selection["path"]:
            raise ValueError("A selected-text request cannot edit another file")
        start, end = selection["start"], selection["end"]
        if before[start:end] != selection["text"]:
            raise ValueError("Selection does not match proposal base")
        prefix, suffix = before[:start], before[end:]
        if not after.startswith(prefix) or (suffix and not after.endswith(suffix)):
            raise ValueError("Proposal changed content outside the selection")
        if len(after) < len(prefix) + len(suffix):
            raise ValueError("Proposal overlaps the selection boundary")
        replacement = after[len(prefix):len(after) - len(suffix) if suffix else len(after)]
    if is_html_path(path):
        if before:
            validate_html(before)
        source_ids = {source["id"] for source in sources} | html_source_ids(before)
        if selection is not None:
            after = replace_html_selection(before, selection, replacement, source_ids)
            replacement = after[len(prefix):len(after) - len(suffix) if suffix else len(after)]
        else:
            after = prepare_html(after)
            validate_html(after, source_ids)
        validate_content(after)
        # A tag, its content, inline styles and provenance are one review unit.
        # Preserve an empty base for new files so their preview shows generated HTML.
        changes = [] if before == after else [{
            "id": "c0",
            "from": len(prefix.encode("utf-16-le")) // 2,
            "to": len((prefix + selection["text"] if selection else before).encode("utf-16-le")) // 2,
            "before": selection["text"] if selection else before,
            "after": replacement if selection else after,
            "decision": "pending",
        }]
    elif selection is not None:
        changes = changes_for(selection["text"], replacement)
        offset = len(prefix.encode("utf-16-le")) // 2
        for change in changes:
            change["from"] += offset
            change["to"] += offset
    else:
        changes = changes_for(before, after)
    citation_check(before, after, sources, explanation, html_document=is_html_path(path))
    return {
        "id": str(uuid.uuid4()), "jobId": job_id, "path": path, "kind": "ai",
        "instruction": instruction, "explanation": explanation, "baseContent": before,
        "proposedContent": after, "baseVersion": edit["baseVersion"],
        "appliedVersion": edit["baseVersion"], "changes": changes,
        "createdAt": now(), "status": "pending" if changes else "rejected",
        "sources": sources,
    }


def assembled(proposal):
    content = proposal["baseContent"]
    for change in reversed(proposal["changes"]):
        if change["decision"] == "accepted":
            start = utf16_offset(proposal["baseContent"], change["from"])
            end = utf16_offset(proposal["baseContent"], change["to"])
            content = content[:start] + change["after"] + content[end:]
    return content


def recover_approval(files):
    """Finish a committed write after process exit, or discard an unwritten intent."""
    import json
    journal = files.safe(files.internal / "approval.json")
    if not journal.exists():
        return
    intent = json.loads(journal.read_bytes())
    if intent.get("metadataOnly"):
        files.put_proposal(intent["proposal"])
        journal.unlink()
        return
    current = files.read(intent["proposal"]["path"], missing=True)
    current_version = current["version"] if current else None
    if current_version == intent["targetVersion"]:
        files.put_proposal(intent["proposal"])
    elif current_version != intent["previousVersion"]:
        raise HTTPException(409, "중단된 승인 이후 파일이 변경되었습니다. 관리자에게 복구를 요청해 주세요.")
    journal.unlink()


def apply_decisions(files, proposal_id, decisions):
    proposal = files.proposal(proposal_id)
    by_id = {change["id"]: change for change in proposal["changes"]}
    if any(key not in by_id for key in decisions):
        raise HTTPException(422, "수정안에 없는 변경입니다.")
    next_proposal = deepcopy(proposal)
    changed = False
    for change in next_proposal["changes"]:
        decision = decisions.get(change["id"])
        if decision is None or decision == change["decision"]:
            continue
        if change["decision"] != "pending":
            raise HTTPException(409, "이미 처리한 변경입니다. 새 수정안을 요청해 주세요.")
        change["decision"] = decision
        changed = True
    current = files.read(proposal["path"], missing=True)
    if not changed:
        return {"proposal": proposal, "file": current}
    current_version = current["version"] if current else None
    statuses = {change["decision"] for change in next_proposal["changes"]}
    next_proposal["status"] = (
        "pending" if statuses == {"pending"} else "accepted" if statuses == {"accepted"}
        else "rejected" if statuses == {"rejected"} else "partial"
    )
    should_write = any(
        decision == "accepted" and by_id[change_id]["decision"] == "pending"
        for change_id, decision in decisions.items()
    )
    if should_write:
        if current_version != proposal["appliedVersion"]:
            raise HTTPException(409, "수정안 이후 원본이 변경되었습니다. 최신 문서로 다시 요청해 주세요.")
        accepted_content = assembled(next_proposal)
        if is_html_path(proposal["path"]):
            try:
                if len(next_proposal["changes"]) != 1:
                    raise ValueError("HTML changes must be atomic")
                allowed_sources = (
                    {source["id"] for source in proposal["sources"]}
                    | html_source_ids(proposal["baseContent"])
                )
                validate_html(accepted_content, allowed_sources)
                if prepare_html(accepted_content) != accepted_content:
                    raise ValueError("HTML proposal IDs must already be canonical")
                validate_content(accepted_content)
            except ValueError as error:
                raise HTTPException(409, "HTML 수정안이 유효하지 않습니다. 문서 전체를 다시 검토해 주세요.") from error
        try:
            citation_check(
                proposal["baseContent"], accepted_content, proposal["sources"],
                html_document=is_html_path(proposal["path"]),
            )
        except HTTPException:
            raise HTTPException(409, "이 변경만 반영하면 출처가 사라집니다. 관련 변경을 함께 승인해 주세요.") from None
        next_proposal["appliedVersion"] = version(accepted_content)
        journal = files.internal / "approval.json"
        write_json(journal, {
            "proposal": next_proposal, "previousVersion": current_version,
            "targetVersion": next_proposal["appliedVersion"],
        })
        current = files.save(proposal["path"], accepted_content, current_version, "AI 수정 승인")
        files.put_proposal(next_proposal)
        journal.unlink()
    else:
        journal = files.internal / "approval.json"
        write_json(journal, {"proposal": next_proposal, "metadataOnly": True})
        files.put_proposal(next_proposal)
        journal.unlink()
    return {"proposal": next_proposal, "file": current}
