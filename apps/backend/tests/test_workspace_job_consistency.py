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

    def test_concurrent_source_addition_keeps_both_user_and_job_sources_past_fifty(self):
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
        self.assertEqual(len(sources), 51)
        self.assertIn("source-49", {source["id"] for source in sources})
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

    def test_failed_jobs_log_the_safe_service_reason_without_request_content(self):
        from botocore.exceptions import ClientError
        from fastapi import HTTPException

        runtime = ClientError({"Error": {
            "Code": "RuntimeClientError",
            "Message": "Runtime initialization time exceeded. Please make sure that initialization completes in 120s.",
        }}, "InvokeAgentRuntime")
        rejected = HTTPException(502, "AI가 확인되지 않은 출처를 추가했습니다.")
        for error, expected in ((runtime, "initialization time exceeded"), (rejected, "status=502")):
            job, payload = self.prepare()
            with patch("api.workspaces.service.fetch_requested_sources", return_value=[]), \
                    patch("api.workspaces.service.invoke_agent", side_effect=error), \
                    self.assertLogs("api.workspaces.service", "WARNING") as logs:
                run_job(self.files.owner, self.files.workspace, job["id"], payload)
            self.assertIn(expected, logs.output[0])
            self.assertNotIn("다듬기", logs.output[0])
            with self.files.lock():
                self.files.metadata.delete(self.files.namespace, "request:request-1")

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


class FailureReasonTests(unittest.TestCase):
    def test_failed_jobs_explain_what_the_person_can_do_without_internal_details(self):
        from botocore.exceptions import ClientError, ReadTimeoutError
        from fastapi import HTTPException
        from api.workspaces.research import ResearchError
        from api.workspaces.service import GENERIC_FAILURE, TIME_LIMIT_FAILURE, failure_reason

        def runtime(message):
            return ClientError({"Error": {"Code": "RuntimeClientError", "Message": message}}, "InvokeAgentRuntime")

        cases = [
            (ResearchError("프로젝트 출처 한도가 가득 찼습니다."), "프로젝트 출처 한도가 가득 찼습니다."),
            (HTTPException(502, "AI가 확인되지 않은 출처를 추가했습니다."), "AI가 확인되지 않은 출처를 추가했습니다."),
            (runtime("Runtime initialization time exceeded. Please make sure that initialization completes in 120s."),
             TIME_LIMIT_FAILURE),
            (ReadTimeoutError(endpoint_url="https://bedrock-agentcore.example"), TIME_LIMIT_FAILURE),
            (runtime("Received error (502) from runtime. Please check your CloudWatch logs."), GENERIC_FAILURE),
            (HTTPException(500, {"private": "structure"}), GENERIC_FAILURE),
            (ValueError("Invalid runtime result with SECRET"), GENERIC_FAILURE),
        ]
        for error, expected in cases:
            with self.subTest(error=type(error).__name__):
                self.assertEqual(failure_reason(error), expected)
        self.assertIn("원본은 변경되지 않았습니다", TIME_LIMIT_FAILURE)
