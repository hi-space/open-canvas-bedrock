"""Deep research jobs in project workspaces: progress, new-file proposals, evidence and figures."""
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

URL_A = "https://docs.aws.amazon.com/bedrock/latest/userguide/kb-chunking.html"
URL_B = "https://aws.amazon.com/blogs/machine-learning/rerank"
FIGURE = "/api/research/assets/abc123def456/fig1.png"
MARKDOWN = (
    "# RAG 설계: 청킹과 리랭킹\n\n## 청킹\n\n기본 청킹은 약 300토큰입니다 [[1]](" + URL_A + ").\n\n"
    "![그림 1. 파이프라인](" + FIGURE + ")\n\n*그림 1. 파이프라인*\n\n"
    "## 리랭킹\n\n리랭커는 순위를 대체합니다 [[2]](" + URL_B + ").\n\n"
    "## 참고 자료\n\n1. [Chunking](" + URL_A + ") (docs.aws.amazon.com)\n2. [Rerank](" + URL_B + ") (aws.amazon.com)\n"
)


def research_state(markdown=MARKDOWN):
    return {
        "artifact": {"contents": [{"title": "RAG 설계: 청킹과 리랭킹", "fullMarkdown": markdown}]},
        "sources": {
            "S1": {"id": "S1", "url": URL_A, "title": "Chunking", "content": "Default chunking splits about 300 tokens."},
            "S2": {"id": "S2", "url": URL_B, "title": "Rerank", "content": "Reranker scores replace default ranking."},
            "S3": {"id": "S3", "url": "https://unused.example.com/x", "title": "Unused", "content": "never cited"},
        },
        "findings": [{"id": "F1", "question_id": "Q1", "claim": "Default chunking is about 300 tokens",
                      "detail": "sentence boundaries", "quote": "about 300 tokens", "source_ids": ["S1"],
                      "strength": "strong"}],
        "figures": [{"section_id": "s1", "number": 1, "caption": "파이프라인", "url": FIGURE}],
    }


class WorkspaceResearchTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.environment = patch.dict(os.environ, {
            "STORAGE_TYPE": "memory", "WORKSPACE_METADATA": "file", "WORKSPACE_ROOT": self.directory.name,
            "WORKSPACE_AUTH_MODE": "local", "WORKSPACE_LOCAL_SUB": "alice",
            "LANGSMITH_TRACING": "false", "LANGCHAIN_TRACING_V2": "false",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        from main import app
        self.client = TestClient(app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.workspace = self.client.post("/api/workspaces", json={"name": "리서치"}).json()["id"]

    def ask(self, state=None, error=None, **extra):
        progress_seen = []

        async def fake_graph(payload, slots, progress):
            self.assertEqual(payload["researchGenre"], "blog")
            self.assertLessEqual(slots, 50)
            progress("라운드 1: 쿼리 12개로 새 출처 24개 수집")
            progress_seen.append(self.job_message())
            if error:
                raise error
            return state or research_state()

        with patch("api.workspaces.research._run_graph", side_effect=fake_graph), \
                patch("api.workspaces.service.invoke_agent") as agent:
            response = self.client.post(f"/api/workspaces/{self.workspace}/chat", json={
                "message": "Bedrock KB RAG 설계를 정리해줘", "requestId": "r1", "researchGenre": "blog", **extra,
            })
        agent.assert_not_called()
        self.assertEqual(response.status_code, 202, response.text)
        job = self.client.get(f"/api/workspaces/{self.workspace}/jobs/{response.json()['job']['id']}").json()
        return job, progress_seen

    def job_message(self):
        jobs = self.client.get(f"/api/workspaces/{self.workspace}").json()["jobs"]
        return jobs[0]["message"]

    def test_research_proposes_a_new_file_with_evidence_and_figure_until_approved(self):
        job, progress = self.ask()
        self.assertEqual(job["status"], "completed", job)
        self.assertEqual(job["kind"], "research")
        self.assertEqual(progress, ["라운드 1: 쿼리 12개로 새 출처 24개 수집"])

        proposal = self.client.get(f"/api/workspaces/{self.workspace}/proposals/{job['proposalIds'][0]}").json()
        self.assertEqual(proposal["path"], "research/RAG 설계-청킹과 리랭킹.md")
        self.assertIsNone(proposal["baseVersion"])
        self.assertEqual(self.client.get(f"/api/workspaces/{self.workspace}").json()["files"], [])

        sources = {s["url"]: s for s in self.client.get(f"/api/workspaces/{self.workspace}").json()["sources"]}
        self.assertEqual(set(sources), {URL_A, URL_B})  # only cited sources join the project library
        self.assertIn("about 300 tokens", sources[URL_A]["excerpt"])

        decisions = {change["id"]: "accepted" for change in proposal["changes"]}
        approved = self.client.post(f"/api/workspaces/{self.workspace}/proposals/{proposal['id']}/decisions",
                                    json={"decisions": decisions})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["file"]["content"], MARKDOWN)

    def test_unread_citation_still_fails_the_job(self):
        forged = MARKDOWN.replace(URL_B, "https://forged.example.com/claim")
        state = research_state(forged)
        job, _ = self.ask(state)
        self.assertEqual(job["status"], "failed")

    def test_other_relative_images_are_not_exempt(self):
        job, _ = self.ask(research_state(MARKDOWN.replace(FIGURE, "/api/workspaces/x/files.png")))
        self.assertEqual(job["status"], "failed")

    def test_missing_search_key_is_explained_on_the_job(self):
        from agents.deep_research.search import SearchUnavailable
        from api.workspaces.research import ResearchError
        job, _ = self.ask(error=ResearchError("웹 검색이 설정되지 않았습니다. 서버의 TAVILY_API_KEY를 확인해 주세요."))
        self.assertEqual(job["status"], "failed")
        self.assertIn("TAVILY_API_KEY", job["error"])
        self.assertTrue(issubclass(SearchUnavailable, RuntimeError))

    def test_research_cannot_be_combined_with_a_selection(self):
        saved = self.client.put(f"/api/workspaces/{self.workspace}/files",
                                json={"path": "a.md", "content": "문장 하나.\n"}).json()
        response = self.client.post(f"/api/workspaces/{self.workspace}/chat", json={
            "message": "정리", "requestId": "r2", "researchGenre": "blog", "activePath": "a.md",
            "activeVersion": saved["version"], "selection": {"from": 0, "to": 2, "text": "문장"},
        })
        self.assertEqual(response.status_code, 422, response.text)


class DocumentPathTests(unittest.TestCase):
    def test_titles_become_safe_unique_paths(self):
        from api.workspaces.files import validate_path
        from api.workspaces.research import document_path
        path = document_path('a/b: "c"? .', {"research/a-b-c.md"})
        self.assertEqual(validate_path(path), path)
        self.assertEqual(path, "research/a-b-c-2.md")
        self.assertEqual(document_path("🧠 AgentCore Memory: 단기 vs 장기", set()),
                         "research/AgentCore Memory-단기 vs 장기.md")
        self.assertEqual(document_path("...", set()), "research/research.md")


if __name__ == "__main__":
    unittest.main()
