"""Run in a disposable API task to verify real mounts, AgentCore and approval."""
import hashlib
import json
import shutil
import uuid

from fastapi import HTTPException

from api.workspaces.files import ProjectFiles
from api.workspaces.models import ChatRequest
from api.workspaces.proposals import apply_decisions, create_proposal
from api.workspaces.service import prepare_job, run_job
from core.models import get_default_model_name


def main():
    owner = hashlib.sha256(f"workspace-release-probe:{uuid.uuid4()}".encode()).hexdigest()
    workspace = str(uuid.uuid4())
    files = ProjectFiles(owner, workspace)
    original = "\ufeff# 첫 번째 초안\r\n\r\n한글과 이모지 😀를 보존합니다.\r\n"
    selected = "첫 번째 초안"
    prefix = original[:original.index(selected)]
    start = len(prefix.encode("utf-16-le")) // 2
    expected = original.replace(selected, "연결 검증 완료", 1)
    model = get_default_model_name()
    assert model == "global.anthropic.claude-opus-5-5"
    try:
        with files.lock():
            files.metadata.put(files.owner_namespace, workspace, {
                "id": workspace, "name": "Temporary deployment probe", "createdAt": 0, "updatedAt": 0,
            })
            document = files.save("verification.md", original, None)
            job, payload = prepare_job(files, ChatRequest(
                message="선택한 문구를 정확히 '연결 검증 완료'로 바꾸는 수정안을 만들어 주세요. propose_edit 도구를 사용하고 원본은 보존하세요.",
                requestId=str(uuid.uuid4()), activePath="verification.md",
                activeVersion=document["version"],
                selection={"from": start, "to": start + len(selected), "text": selected},
                model=model,
            ))
        run_job(owner, workspace, job["id"], payload)
        with files.lock():
            completed = files.metadata.get(files.namespace, "job:" + job["id"])
            if completed["status"] != "completed" or not completed["proposalIds"]:
                raise RuntimeError("The live agent did not return a completed file proposal.")
            assert files.read("verification.md")["content"] == original
            proposal = files.proposal(completed["proposalIds"][0])
            assert proposal["baseContent"] == original
            assert proposal["baseVersion"] == document["version"]
            assert proposal["proposedContent"] == expected
            decisions = {change["id"]: "accepted" for change in proposal["changes"]}
            approved = apply_decisions(files, proposal["id"], decisions)
            assert approved["file"]["content"] == expected
            repeated = apply_decisions(files, proposal["id"], decisions)
            assert repeated["file"]["version"] == approved["file"]["version"]

            stale = create_proposal({
                "path": "verification.md", "baseContent": expected,
                "baseVersion": approved["file"]["version"],
                "proposedContent": expected + "추가 수정안\r\n", "explanation": "Version conflict probe",
            }, "stale-probe", "Version conflict probe", [])
            files.put_proposal(stale)
            newer = files.save("verification.md", expected + "사용자의 최신 수정\r\n", approved["file"]["version"])
            try:
                apply_decisions(files, stale["id"], {change["id"]: "accepted" for change in stale["changes"]})
                raise AssertionError("Stale approval unexpectedly succeeded")
            except HTTPException as error:
                assert error.status_code == 409
            assert files.read("verification.md")["version"] == newer["version"]
        print(json.dumps({
            "ok": True, "model": model, "agentReadSharedFile": True,
            "unchangedBeforeApproval": True, "approvedWritePersisted": True,
            "duplicateApprovalIdempotent": True, "staleApprovalBlocked": True,
            "unicodeAndCrLfPreserved": True, "metadata": "dynamodb",
        }))
    finally:
        # The owner hash and project above were generated solely for this probe.
        for key in files.metadata.items(files.namespace):
            files.metadata.delete(files.namespace, key)
        files.metadata.delete(files.owner_namespace, workspace)
        directory = files.root / owner
        if directory.exists():
            shutil.rmtree(directory)


if __name__ == "__main__":
    main()
