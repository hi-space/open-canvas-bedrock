"""Concurrent source edits and interrupted review publication remain recoverable."""
import hashlib
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from api.workspaces.files import ProjectFiles
from api.workspaces.models import ChatRequest
from api.workspaces.proposals import create_proposal, apply_decisions
from api.workspaces.service import prepare_job, run_job, sources_from


class JobConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        environment = patch.dict(os.environ, {
            "WORKSPACE_ROOT": self.directory.name, "WORKSPACE_METADATA": "file",
            "WORKSPACE_AUTH_MODE": "local",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.files = ProjectFiles(hashlib.sha256(b"test").hexdigest(), "00000000-0000-0000-0000-000000000001")
        with self.files.lock():
            self.files.metadata.put(self.files.owner_namespace, self.files.workspace, {"id": self.files.workspace})
            self.original = self.files.save("draft.md", "초안.\n", None)

    def source(self, index):
        return {"id": f"source-{index}", "title": f"자료 {index}",
                "url": f"https://example.com/{index}", "excerpt": "제공된 원문"}

    def prepare(self):
        with self.files.lock():
            return prepare_job(self.files, ChatRequest(message="다듬기", requestId="request-1"))

    def test_concurrent_source_addition_does_not_exceed_project_capacity(self):
        with self.files.lock():
            for index in range(49):
                self.files.metadata.put(self.files.namespace, f"source:source-{index}", self.source(index))
        job, payload = self.prepare()

        def invoke(_payload):
            with self.files.lock():
                self.files.metadata.put(self.files.namespace, "source:source-50", self.source(50))
            return {"message": "완료", "proposals": [], "events": []}

        with patch("api.workspaces.service.fetch_requested_sources", return_value=[self.source(49)]):
            with patch("api.workspaces.service.invoke_agent", side_effect=invoke):
                run_job(self.files.owner, self.files.workspace, job["id"], payload)
        records = self.files.metadata.items(self.files.namespace)
        sources = sources_from(records)
        self.assertEqual(len(sources), 50)
        self.assertIn("source-50", {source["id"] for source in sources})

    def test_runtime_fetched_evidence_is_validated_and_persisted_with_cited_proposal(self):
        job, payload = self.prepare()
        source = self.source(1)
        result = {
            "message": "출처를 연결했습니다.", "sources": [source], "events": [],
            "proposals": [{
                "path": "draft.md", "baseVersion": self.original["version"],
                "baseContent": self.original["content"],
                "proposedContent": "초안 [1](https://example.com/1).\n", "explanation": "출처 추가",
            }],
        }
        with patch("api.workspaces.service.fetch_requested_sources", return_value=[]):
            with patch("api.workspaces.service.invoke_agent", return_value=result):
                run_job(self.files.owner, self.files.workspace, job["id"], payload)
        records = self.files.metadata.items(self.files.namespace)
        self.assertEqual(records["job:" + job["id"]]["status"], "completed")
        self.assertEqual(records["source:" + source["id"]]["url"], source["url"])

    def test_rejection_metadata_failure_recovers_without_touching_changed_file(self):
        proposal = create_proposal({
            "path": "draft.md", "baseVersion": self.original["version"],
            "baseContent": self.original["content"], "proposedContent": "수정안\n", "explanation": "교정",
        }, "job", "교정", [])
        with self.files.lock():
            self.files.put_proposal(proposal)
            with patch.object(self.files.metadata, "put", side_effect=RuntimeError("database unavailable")):
                with self.assertRaises(RuntimeError):
                    apply_decisions(self.files, proposal["id"], {change["id"]: "rejected" for change in proposal["changes"]})
        # The original is untouched; recovery publishes the decision summary.
        with self.files.lock():
            self.assertEqual(self.files.read("draft.md")["content"], self.original["content"])
            summary = self.files.metadata.get(self.files.namespace, "proposal:" + proposal["id"])
            self.assertEqual(summary["status"], "rejected")
            self.assertEqual(summary["pendingCount"], 0)


if __name__ == "__main__":
    unittest.main()
