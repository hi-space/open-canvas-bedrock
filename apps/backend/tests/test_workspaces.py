"""Cloud workspace behavior: ownership, exact versions, and approved writes."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.environment = patch.dict(os.environ, {
            "STORAGE_TYPE": "memory",
            "WORKSPACE_METADATA": "file",
            "WORKSPACE_ROOT": self.directory.name,
            "WORKSPACE_AUTH_MODE": "local",
            "WORKSPACE_LOCAL_SUB": "alice",
            "LANGSMITH_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        from main import app
        self.client = TestClient(app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def create(self):
        response = self.client.post("/api/workspaces", json={"name": "글쓰기"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def write(self, workspace, path="draft.md", content="원문\n", version=None):
        return self.client.put(f"/api/workspaces/{workspace}/files", json={
            "path": path, "content": content, "baseVersion": version,
        })

    def test_create_list_and_import_exact_utf8(self):
        workspace = self.create()
        content = "\ufeff# 초안 😀\r\n\r\n문장\r\n"
        response = self.write(workspace, content=content)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["content"], content)
        self.assertEqual(response.json()["bytes"], len(content.encode("utf-8")))
        self.assertEqual(len(response.json()["version"]), 64)
        files = self.client.get(f"/api/workspaces/{workspace}").json()["files"]
        self.assertEqual(files[0]["path"], "draft.md")
        self.assertEqual(
            self.client.get(f"/api/workspaces/{workspace}/files", params={"path": "draft.md"}).json()["content"],
            content,
        )

    def test_other_owner_cannot_list_or_read_project(self):
        workspace = self.create()
        self.write(workspace)
        with patch.dict(os.environ, {"WORKSPACE_LOCAL_SUB": "bob"}):
            self.assertEqual(self.client.get("/api/workspaces").json()["workspaces"], [])
            self.assertEqual(self.client.get(f"/api/workspaces/{workspace}").status_code, 404)
            self.assertEqual(self.write(workspace).status_code, 404)

    def test_create_only_and_stale_writes_preserve_current_content(self):
        workspace = self.create()
        first = self.write(workspace).json()
        self.assertEqual(self.write(workspace, content="덮어쓰기").status_code, 409)
        second = self.write(workspace, content="수정\n", version=first["version"])
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(self.write(workspace, content="오래된 수정", version=first["version"]).status_code, 409)
        current = self.client.get(f"/api/workspaces/{workspace}/files", params={"path": "draft.md"}).json()
        self.assertEqual(current["content"], "수정\n")
        history = self.client.get(f"/api/workspaces/{workspace}/history", params={"path": "draft.md"}).json()
        self.assertTrue(any(revision["content"] == "원문\n" for revision in history["revisions"]))

    def test_invalid_paths_and_symlinks_cannot_escape(self):
        workspace = self.create()
        for name in ["../other.md", "/tmp/a.md", ".canvas/a.md", "x\\a.md", "a/../../b.md", "x.py", "a//b.md"]:
            with self.subTest(name=name):
                response = self.write(workspace, path=name)
                self.assertEqual(response.status_code, 422, response.text)
        self.write(workspace)
        files = next(Path(self.directory.name).glob(f"*/{workspace}/files"))
        (files / "escape").symlink_to("/tmp", target_is_directory=True)
        self.assertEqual(self.write(workspace, path="escape/a.md").status_code, 422)

    def test_missing_identity_fails_closed_when_alb_mode_enabled(self):
        with patch.dict(os.environ, {"WORKSPACE_AUTH_MODE": "alb", "ALB_SIGNER_ARN": "expected"}):
            self.assertEqual(self.client.get("/api/workspaces").status_code, 401)

    def test_agent_proposal_does_not_write_until_approval_and_repeats_are_safe(self):
        workspace = self.create()
        original = self.write(workspace, content="첫 문장.\n\n둘째 문장.\n").json()
        result = {
            "message": "수정안을 준비했습니다.", "events": [],
            "proposals": [{
                "path": "draft.md", "baseVersion": original["version"],
                "baseContent": original["content"],
                "proposedContent": "첫 문장을 다듬었습니다.\n\n둘째 문장.\n",
                "explanation": "첫 문장 교정",
            }],
        }
        with patch("api.workspaces.service.invoke_agent", return_value=result):
            response = self.client.post(f"/api/workspaces/{workspace}/chat", json={
                "message": "첫 문장 교정", "requestId": "request-1",
                "activePath": "draft.md", "activeVersion": original["version"],
            })
        self.assertEqual(response.status_code, 202, response.text)
        job_id = response.json()["job"]["id"]
        job = self.client.get(f"/api/workspaces/{workspace}/jobs/{job_id}").json()
        self.assertEqual(job["status"], "completed", job)
        before = self.client.get(f"/api/workspaces/{workspace}/files", params={"path": "draft.md"}).json()
        self.assertEqual(before["content"], original["content"])
        proposal_id = job["proposalIds"][0]
        proposal = self.client.get(f"/api/workspaces/{workspace}/proposals/{proposal_id}").json()
        decisions = {change["id"]: "accepted" for change in proposal["changes"]}
        approved = self.client.post(f"/api/workspaces/{workspace}/proposals/{proposal_id}/decisions", json={"decisions": decisions})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["file"]["content"], result["proposals"][0]["proposedContent"])
        repeated = self.client.post(f"/api/workspaces/{workspace}/proposals/{proposal_id}/decisions", json={"decisions": decisions})
        self.assertEqual(repeated.status_code, 200, repeated.text)
        with patch("api.workspaces.service.invoke_agent") as invoke:
            duplicate = self.client.post(f"/api/workspaces/{workspace}/chat", json={
                "message": "첫 문장 교정", "requestId": "request-1",
            })
        self.assertEqual(duplicate.json()["job"]["id"], job_id)
        invoke.assert_not_called()

    def test_stale_proposal_never_overwrites_a_later_manual_save(self):
        workspace = self.create()
        original = self.write(workspace).json()
        with patch("api.workspaces.service.invoke_agent", return_value={
            "message": "교정", "events": [], "proposals": [{
                "path": "draft.md", "baseVersion": original["version"],
                "baseContent": original["content"], "proposedContent": "AI 수정\n",
                "explanation": "교정",
            }],
        }):
            response = self.client.post(f"/api/workspaces/{workspace}/chat", json={
                "message": "교정", "requestId": "request-2",
            })
        job = self.client.get(f"/api/workspaces/{workspace}/jobs/{response.json()['job']['id']}").json()
        proposal_id = job["proposalIds"][0]
        self.write(workspace, content="사용자의 최신 수정\n", version=original["version"])
        proposal = self.client.get(f"/api/workspaces/{workspace}/proposals/{proposal_id}").json()
        response = self.client.post(f"/api/workspaces/{workspace}/proposals/{proposal_id}/decisions", json={
            "decisions": {change["id"]: "accepted" for change in proposal["changes"]},
        })
        self.assertEqual(response.status_code, 409, response.text)
        current = self.client.get(f"/api/workspaces/{workspace}/files", params={"path": "draft.md"}).json()
        self.assertEqual(current["content"], "사용자의 최신 수정\n")

    def test_stale_proposal_can_be_rejected_without_overwriting_manual_save(self):
        workspace = self.create()
        original = self.write(workspace).json()
        from api.workspaces.files import ProjectFiles
        from api.workspaces.proposals import create_proposal
        import hashlib
        files = ProjectFiles(hashlib.sha256(b"alice").hexdigest(), workspace)
        proposal = create_proposal({
            "path": "draft.md", "baseVersion": original["version"],
            "baseContent": original["content"], "proposedContent": "AI 수정\n",
            "explanation": "교정",
        }, "job", "교정", [])
        with files.lock():
            files.put_proposal(proposal)
        self.write(workspace, content="최신 수동 수정\n", version=original["version"])
        response = self.client.post(f"/api/workspaces/{workspace}/proposals/{proposal['id']}/decisions", json={
            "decisions": {change["id"]: "rejected" for change in proposal["changes"]},
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["file"]["content"], "최신 수동 수정\n")
        self.assertEqual(response.json()["proposal"]["status"], "rejected")

    def test_partial_approval_cannot_drop_a_moved_citation(self):
        workspace = self.create()
        first = "첫 번째 문단에서는 연구 방법과 대상을 충분히 설명합니다. " * 5
        second = "다음 문단에서는 측정 결과를 독자가 이해하도록 자세히 소개합니다. " * 5
        original = self.write(workspace, content=first + "[1](https://example.com/source)\n\n" + second + "\n").json()
        from api.workspaces.files import ProjectFiles
        from api.workspaces.proposals import create_proposal
        import hashlib
        files = ProjectFiles(hashlib.sha256(b"alice").hexdigest(), workspace)
        proposal = create_proposal({
            "path": "draft.md", "baseVersion": original["version"],
            "baseContent": original["content"],
            "proposedContent": first + "\n\n" + second + "[1](https://example.com/source)\n",
            "explanation": "출처 위치 조정",
        }, "job", "다듬기", [])
        self.assertGreaterEqual(len(proposal["changes"]), 2)
        with files.lock():
            files.put_proposal(proposal)
        response = self.client.post(f"/api/workspaces/{workspace}/proposals/{proposal['id']}/decisions", json={
            "decisions": {proposal["changes"][0]["id"]: "accepted"},
        })
        self.assertEqual(response.status_code, 409, response.text)
        content = self.client.get(f"/api/workspaces/{workspace}/files", params={"path": "draft.md"}).json()["content"]
        self.assertEqual(content, original["content"])
        response = self.client.post(f"/api/workspaces/{workspace}/proposals/{proposal['id']}/decisions", json={
            "decisions": {change["id"]: "accepted" for change in proposal["changes"]},
        })
        self.assertEqual(response.status_code, 200, response.text)

    def test_completed_file_write_is_recovered_after_metadata_failure(self):
        workspace = self.create()
        original = self.write(workspace).json()
        from api.workspaces.files import ProjectFiles
        from api.workspaces.proposals import create_proposal, apply_decisions
        import hashlib
        files = ProjectFiles(hashlib.sha256(b"alice").hexdigest(), workspace)
        proposal = create_proposal({
            "path": "draft.md", "baseVersion": original["version"],
            "baseContent": original["content"], "proposedContent": "승인된 내용\n",
            "explanation": "교정",
        }, "job", "교정", [])
        with files.lock():
            files.put_proposal(proposal)
            with patch.object(files, "put_proposal", side_effect=RuntimeError("interrupted")):
                with self.assertRaises(RuntimeError):
                    apply_decisions(files, proposal["id"], {change["id"]: "accepted" for change in proposal["changes"]})
        self.assertTrue((files.internal / "approval.json").exists())
        # Acquiring the next lock finalizes the already written approval.
        with files.lock():
            recovered = files.proposal(proposal["id"])
            self.assertEqual(recovered["status"], "accepted")
            self.assertEqual(files.read("draft.md")["content"], "승인된 내용\n")
        self.assertFalse((files.internal / "approval.json").exists())


if __name__ == "__main__":
    unittest.main()
