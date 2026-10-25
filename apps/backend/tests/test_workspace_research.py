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

    def test_html_research_has_citations_and_a_figure_and_requires_approval(self):
        job, _ = self.ask(outputFormat="html")
        self.assertEqual(job["status"], "completed", job)
        proposal = self.client.get(f"/api/workspaces/{self.workspace}/proposals/{job['proposalIds'][0]}").json()
        self.assertEqual(proposal["path"], "research/RAG 설계-청킹과 리랭킹.html")
        self.assertIn("<!doctype html>", proposal["proposedContent"].lower())
        self.assertIn(f'href="{URL_A}"', proposal["proposedContent"])
        self.assertIn(f'src="{FIGURE}"', proposal["proposedContent"])
        self.assertEqual(self.client.get(f"/api/workspaces/{self.workspace}").json()["files"], [])
        approved = self.client.post(
            f"/api/workspaces/{self.workspace}/proposals/{proposal['id']}/decisions",
            json={"decisions": {"c0": "accepted"}},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["file"]["content"], proposal["proposedContent"])

    def test_html_research_lists_private_material_without_inventing_a_public_url(self):
        saved = self.client.put(f"/api/workspaces/{self.workspace}/files", json={
            "path": "notes/customer.md", "content": "고객이 요청한 조건은 세 가지입니다.",
        }).json()
        job, _ = self.ask(outputFormat="html", activePath=saved["path"], activeVersion=saved["version"])
        self.assertEqual(job["status"], "completed", job)
        proposal = self.client.get(f"/api/workspaces/{self.workspace}/proposals/{job['proposalIds'][0]}").json()
        self.assertIn("notes/customer.md", proposal["proposedContent"])
        self.assertIn(saved["version"][:12], proposal["proposedContent"])
        self.assertNotIn('href="notes/customer.md"', proposal["proposedContent"])

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

    def test_selected_project_material_is_snapshotted_before_research(self):
        saved = self.client.put(f"/api/workspaces/{self.workspace}/files", json={
            "path": "notes/brief.md", "content": "# 내부 자료\n\n고객은 세 가지 구성을 비교합니다.",
        }).json()
        self.client.put(f"/api/workspaces/{self.workspace}/files", json={
            "path": "unselected.md", "content": "이 문서는 선택하지 않았습니다.",
        })
        received = []

        async def graph(payload, slots, progress):
            received.extend(payload.get("projectContext", []))
            self.client.put(f"/api/workspaces/{self.workspace}/files", json={
                "path": saved["path"], "content": "# 새 버전", "baseVersion": saved["version"],
            })
            return research_state()

        with patch("api.workspaces.research._run_graph", side_effect=graph):
            response = self.client.post(f"/api/workspaces/{self.workspace}/chat", json={
                "message": "우리 자료를 바탕으로 조사", "requestId": "context", "researchGenre": "blog",
                "activePath": saved["path"], "activeVersion": saved["version"],
                "contextPaths": [saved["path"]],
            })
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(received, [{
            "path": "notes/brief.md", "version": saved["version"],
            "content": "# 내부 자료\n\n고객은 세 가지 구성을 비교합니다.", "truncated": False,
        }])
        current = self.client.get(f"/api/workspaces/{self.workspace}/files", params={"path": saved["path"]}).json()
        self.assertEqual(current["content"], "# 새 버전")

    def test_research_context_rejects_outside_or_missing_project_files(self):
        for path, status in [("../other.md", 422), ("missing.md", 404)]:
            with self.subTest(path=path), patch(
                "api.workspaces.research._run_graph", return_value=research_state()
            ):
                response = self.client.post(f"/api/workspaces/{self.workspace}/chat", json={
                    "message": "조사", "requestId": "bad-context", "researchGenre": "blog",
                    "contextPaths": [path],
                })
                self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(self.client.get(f"/api/workspaces/{self.workspace}").json()["jobs"], [])

    def test_context_paths_have_a_five_file_limit_and_require_research(self):
        for extra in [
            {"researchGenre": "blog", "contextPaths": [f"{n}.md" for n in range(6)]},
            {"contextPaths": ["a.md"]},
        ]:
            with self.subTest(extra=extra), patch(
                "api.workspaces.research._run_graph", return_value=research_state()
            ), patch("api.workspaces.service.invoke_agent", return_value={"message": "완료", "proposals": []}):
                response = self.client.post(f"/api/workspaces/{self.workspace}/chat", json={
                    "message": "자료 읽기", "requestId": "context-limit", **extra,
                })
                self.assertEqual(response.status_code, 422, response.text)

    def test_an_explicit_empty_context_excludes_the_active_document(self):
        saved = self.client.put(f"/api/workspaces/{self.workspace}/files", json={
            "path": "private.md", "content": "선택 해제한 파일",
        }).json()
        received = []

        async def graph(payload, slots, progress):
            received.extend(payload.get("projectContext", []))
            return research_state()

        with patch("api.workspaces.research._run_graph", side_effect=graph):
            response = self.client.post(f"/api/workspaces/{self.workspace}/chat", json={
                "message": "웹만 조사", "requestId": "web-only", "researchGenre": "blog",
                "activePath": "private.md", "activeVersion": saved["version"], "contextPaths": [],
            })
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(received, [])


class ResearchContextTests(unittest.TestCase):
    def test_short_documents_are_preserved_and_long_excerpts_are_bounded(self):
        from api.workspaces.research_context import context_excerpt
        self.assertEqual(context_excerpt("짧은 원문", 20), "짧은 원문")
        excerpt = context_excerpt("도입 " * 100 + "결론 " * 100, 100)
        self.assertLessEqual(len(excerpt), 100)
        self.assertTrue(excerpt.strip())

    def test_source_documents_share_a_total_context_budget(self):
        from api.workspaces.research_context import snapshot_context

        class Files:
            def read(self, path):
                return {"path": path, "version": "a" * 64, "content": "한" * 16000}

        context = snapshot_context(Files(), [f"{n}.md" for n in range(5)])
        self.assertEqual(len(context), 5)
        self.assertLessEqual(sum(len(item["content"]) for item in context), 30000)
        self.assertTrue(all(item["truncated"] for item in context))
        self.assertTrue(all(0 < len(item["content"]) <= 12000 for item in context))


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

    def test_html_names_have_their_own_collision_check(self):
        from api.workspaces.research import document_path
        self.assertEqual(
            document_path("연구", {"research/연구.html", "research/연구-2.html"}, "html"),
            "research/연구-3.html",
        )


class ResearchSourceBudgetTests(unittest.TestCase):
    def test_nearly_full_library_keeps_new_registrations_within_the_remaining_slot(self):
        from agents.deep_research.assemble import assemble
        from agents.deep_research.genres import get_profile
        from api.workspaces.research import run_research
        from api.workspaces.service import within_source_limits

        existing = [{"id": f"old-{index}", "title": "Registered", "url": f"https://provided.example/{index}"}
                    for index in range(49)]
        existing[0]["excerpt"] = "Provided measured result."
        sources = {
            "S1": {"id": "S1", "url": existing[0]["url"], "title": "Provided",
                   "origin": "supplied", "content": "Provided measured result."},
            "S2": {"id": "S2", "url": URL_A, "title": "First", "content": "A measured result."},
            "S3": {"id": "S3", "url": URL_B, "title": "Second", "content": "Another measured result."},
        }

        async def stream(inputs, **_kwargs):
            # Exercise the real adapter's budget contract and the real assembler.
            options = {
                "max_cited": inputs.get("maxCitedSources"),
                "max_new_cited": inputs.get("maxNewCitedSources"),
            }
            markdown = assemble("Research", [("s1", "First [S2]. Second [S3].")], [], sources,
                                get_profile("blog"), "en", **options)
            yield {"generateArtifact": {
                "artifact": {"contents": [{"title": "Research", "fullMarkdown": markdown}]},
                "sources": sources, "findings": [], "figures": [],
            }}

        with patch("agents.deep_research.graph.graph.astream", side_effect=stream):
            result = run_research({
                "ownerKey": "a" * 64, "message": "Research", "history": [], "sources": existing,
                "model": "global.anthropic.claude-sonnet-5-5", "researchGenre": "blog",
            }, set(), lambda _status: None)
        combined = {item["id"]: item for item in [*existing, *result["sources"]]}
        self.assertTrue(within_source_limits(combined))
        self.assertEqual(len(result["sources"]), 1)


if __name__ == "__main__":
    unittest.main()
