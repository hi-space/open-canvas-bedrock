"""Full correction copies preserve source files and immutable comparison records."""
import hashlib
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


BEFORE = "\ufeff# 기획서 😀\r\n\r\n첫 문장 입니다.\r\n\r\n두 번째 문장 입니다.\r\n\r\n[출처](https://example.org/source)\r\n"
AFTER = "\ufeff# 기획서 😀\r\n\r\n첫 문장입니다.\r\n\r\n두 번째 문장입니다.\r\n\r\n[출처](https://example.org/source)\r\n"


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    for key, value in {
        "STORAGE_TYPE": "memory",
        "WORKSPACE_METADATA": "file",
        "WORKSPACE_ROOT": str(tmp_path),
        "WORKSPACE_AUTH_MODE": "local",
        "WORKSPACE_LOCAL_SUB": "alice",
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
    }.items():
        monkeypatch.setenv(key, value)
    from main import app
    from api.workspaces.files import ProjectFiles

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/workspaces", json={"name": "교정본"})
        assert response.status_code == 200, response.text
        files = ProjectFiles(hashlib.sha256(b"alice").hexdigest(), response.json()["id"])
        yield client, files


def proposal_for(files, path="notes/기획서.md", before=BEFORE, after=AFTER):
    from api.workspaces.proposals import create_proposal

    with files.lock():
        original = files.read(path, missing=True) or files.save(path, before, None)
        proposal = create_proposal({
            "path": path, "baseContent": original["content"], "baseVersion": original["version"],
            "proposedContent": after, "explanation": "문서 전체를 교정했습니다.",
        }, "job", "전체 교정", [])
        files.put_proposal(proposal)
    return proposal


def copy(client, files, proposal):
    return client.post(f"/api/workspaces/{files.workspace}/proposals/{proposal['id']}/copy")


def history(client, files, path):
    response = client.get(f"/api/workspaces/{files.workspace}/history", params={"path": path})
    assert response.status_code == 200, response.text
    return response.json()


def test_copy_saves_the_full_document_without_approving_or_modifying_the_original(workspace):
    client, files = workspace
    proposal = proposal_for(files)
    response = copy(client, files, proposal)
    assert response.status_code == 200, response.text
    result = response.json()
    saved = result["file"]
    assert saved["path"].startswith("notes/기획서.교정본-")
    assert saved["path"].endswith(".md")
    assert saved["content"] == AFTER
    assert files.path(saved["path"]).read_bytes() == AFTER.encode("utf-8")
    assert files.read(proposal["path"])["content"] == BEFORE
    assert history(client, files, proposal["path"])["revisions"] == []
    assert result["proposal"]["changes"] == proposal["changes"]
    assert result["proposal"]["status"] == "pending"
    assert result["proposal"]["appliedVersion"] == proposal["baseVersion"]
    assert result["proposal"]["savedCopy"]["path"] == saved["path"]
    record = history(client, files, saved["path"])["correction"]
    assert record == {
        "proposalId": proposal["id"], "sourcePath": proposal["path"], "path": saved["path"],
        "createdAt": result["proposal"]["savedCopy"]["createdAt"],
        "baseContent": BEFORE, "proposedContent": AFTER,
    }
    detail = client.get(f"/api/workspaces/{files.workspace}").json()
    assert detail["proposals"][0]["savedCopy"] == result["proposal"]["savedCopy"]
    assert {item["path"] for item in detail["files"]} == {proposal["path"], saved["path"]}


def test_partial_decisions_and_later_source_edits_do_not_change_the_full_copy(workspace):
    client, files = workspace
    proposal = proposal_for(files)
    assert len(proposal["changes"]) == 2
    response = client.post(f"/api/workspaces/{files.workspace}/proposals/{proposal['id']}/decisions", json={
        "decisions": {proposal["changes"][0]["id"]: "accepted", proposal["changes"][1]["id"]: "rejected"},
    })
    assert response.status_code == 200, response.text
    decided = response.json()["proposal"]
    assert response.json()["file"]["content"] == BEFORE.replace("첫 문장 입니다.", "첫 문장입니다.")
    with files.lock():
        files.save(proposal["path"], "사용자가 나중에 쓴 원문\n", response.json()["file"]["version"])
    response = copy(client, files, proposal)
    assert response.status_code == 200, response.text
    assert response.json()["file"]["content"] == AFTER
    assert response.json()["proposal"]["changes"] == decided["changes"]
    assert files.read(proposal["path"])["content"] == "사용자가 나중에 쓴 원문\n"
    assert history(client, files, response.json()["file"]["path"])["correction"]["baseContent"] == BEFORE


def test_retry_returns_the_same_copy_without_overwriting_later_edits(workspace):
    client, files = workspace
    proposal = proposal_for(files)
    response = copy(client, files, proposal)
    assert response.status_code == 200, response.text
    saved = response.json()["file"]
    with files.lock():
        files.save(saved["path"], "교정본에 직접 추가한 내용\n", saved["version"])
    repeated = copy(client, files, proposal)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["file"]["path"] == saved["path"]
    assert repeated.json()["file"]["content"] == "교정본에 직접 추가한 내용\n"
    assert len(files.list()) == 2
    assert history(client, files, saved["path"])["correction"]["proposedContent"] == AFTER


def test_comparison_snapshots_survive_the_rolling_history_limit(workspace):
    client, files = workspace
    proposal = proposal_for(files)
    response = copy(client, files, proposal)
    assert response.status_code == 200, response.text
    saved = response.json()["file"]
    for index in range(32):
        with files.lock():
            saved = files.save(saved["path"], f"후속 편집 {index}\n", saved["version"])
    result = history(client, files, saved["path"])
    assert len(result["revisions"]) == 30
    assert result["correction"]["baseContent"] == BEFORE
    assert result["correction"]["proposedContent"] == AFTER


@pytest.mark.parametrize("path", [
    "가" * 75 + ".markdown",
    "/".join(["d" * 69] * 7 + ["x.MD"]),
])
def test_long_utf8_and_deep_names_still_create_valid_copies(workspace, path):
    client, files = workspace
    proposal = proposal_for(files, path=path)
    response = copy(client, files, proposal)
    assert response.status_code == 200, response.text
    saved = response.json()["file"]
    assert len(saved["path"]) <= 500
    assert len(saved["name"].encode("utf-8")) <= 240
    assert saved["path"].split(".")[-1] == path.split(".")[-1]
    assert saved["content"] == AFTER
    assert files.read(path)["content"] == BEFORE


def test_existing_destination_is_never_overwritten(workspace):
    client, files = workspace
    first = proposal_for(files)
    # Distinct proposals can share the short ID suffix used in the filename.
    second = {**first, "id": first["id"][:8] + str(uuid.uuid4())[8:]}
    with files.lock():
        files.put_proposal(second)
    with patch("api.workspaces.files.now", return_value=1792936800000):
        response = copy(client, files, first)
        assert response.status_code == 200, response.text
        saved = response.json()["file"]
        response = copy(client, files, second)
    assert response.status_code == 409, response.text
    assert files.read(saved["path"])["content"] == AFTER
    assert files.read(first["path"])["content"] == BEFORE
    assert len(files.list()) == 2
    assert not files.proposal(second["id"]).get("savedCopy")


def test_html_copy_retains_canonical_ids_and_exact_proposed_document(workspace):
    client, files = workspace
    before = '<!doctype html><html><body><p data-oc-id="copy">문장 입니다.</p></body></html>'
    after = '<!doctype html><html><body><p data-oc-id="copy">문장입니다.</p></body></html>'
    proposal = proposal_for(files, "page.html", before, after)
    response = copy(client, files, proposal)
    assert response.status_code == 200, response.text
    assert response.json()["file"]["content"] == proposal["proposedContent"]
    record = history(client, files, response.json()["file"]["path"])["correction"]
    assert record["baseContent"] == proposal["baseContent"]
    assert record["proposedContent"] == proposal["proposedContent"]
    assert files.read("page.html")["content"] == proposal["baseContent"]


def test_copy_checks_project_ownership(workspace, monkeypatch):
    client, files = workspace
    proposal = proposal_for(files)
    response = copy(client, files, proposal)
    assert response.status_code == 200, response.text
    monkeypatch.setenv("WORKSPACE_LOCAL_SUB", "bob")
    response = copy(client, files, proposal)
    assert response.status_code == 404, response.text
    assert len(files.list()) == 2


def test_new_file_proposals_keep_the_existing_approval_flow(workspace):
    client, files = workspace
    from api.workspaces.proposals import create_proposal

    proposal = create_proposal({
        "path": "new.md", "baseContent": "", "baseVersion": None,
        "proposedContent": "# 새 문서\n", "explanation": "새 문서",
    }, "job", "새 문서", [])
    with files.lock():
        files.put_proposal(proposal)
    response = copy(client, files, proposal)
    assert response.status_code == 422, response.text
    assert files.list() == []


def test_copy_is_recovered_when_proposal_metadata_fails_after_the_file_write(workspace):
    client, files = workspace
    from api.workspaces.files import ProjectFiles

    proposal = proposal_for(files)
    with patch.object(ProjectFiles, "put_proposal", side_effect=RuntimeError("metadata interrupted")):
        response = copy(client, files, proposal)
    assert response.status_code == 500, response.text
    assert len(files.list()) == 2
    # Any subsequent project request acquires the lock and completes the journal.
    detail = client.get(f"/api/workspaces/{files.workspace}")
    assert detail.status_code == 200, detail.text
    saved_path = detail.json()["proposals"][0]["savedCopy"]["path"]
    assert history(client, files, saved_path)["correction"]["baseContent"] == BEFORE
    response = copy(client, files, proposal)
    assert response.status_code == 200, response.text
    assert response.json()["file"]["path"] == saved_path
    assert len(files.list()) == 2
    assert files.read(proposal["path"])["content"] == BEFORE


def test_failed_file_write_can_be_retried_without_losing_the_comparison(workspace):
    client, files = workspace
    from api.workspaces.files import ProjectFiles

    proposal = proposal_for(files)
    with patch.object(ProjectFiles, "save", side_effect=OSError("disk write interrupted")):
        response = copy(client, files, proposal)
    assert response.status_code == 500, response.text
    assert len(files.list()) == 1
    response = copy(client, files, proposal)
    assert response.status_code == 200, response.text
    assert response.json()["file"]["content"] == AFTER
    assert history(client, files, response.json()["file"]["path"])["correction"]["baseContent"] == BEFORE
