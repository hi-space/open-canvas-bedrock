"""Deep research writer: graph flow, citation fidelity and canvas streaming, offline.

Only the external boundaries are replaced: the Bedrock model, Tavily search and figure rendering.
"""
import asyncio
import json
import os
import unittest
from unittest.mock import patch

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from agents.deep_research.assemble import assemble
from agents.deep_research.genres import get_profile

BRIEF = {
    "title": "RAG 평가", "language": "ko", "audience": "ML 엔지니어", "thesis": "RAG 품질은 검색 단계가 좌우한다",
    "questions": [
        {"id": "Q1", "question": "검색 품질 지표는?", "queries": ["rag retrieval metrics", "recall@k rag"]},
        {"id": "Q2", "question": "생성 품질 평가는?", "queries": ["rag faithfulness eval"]},
    ],
}
OUTLINE = {
    "title": "RAG 품질의 병목은 검색이다",
    "sections": [
        {"id": "s1", "heading": "왜 검색인가", "goal": "문제 제기", "key_points": ["p"], "finding_ids": ["F1", "F99"],
         "words": 300, "figure": {"kind": "concept", "request": "pipeline", "caption": "RAG 파이프라인"}},
        {"id": "s2", "heading": "평가 방법", "goal": "방법", "key_points": ["p"], "finding_ids": ["F2"], "words": 300},
    ],
}


class Recorder:
    def __init__(self):
        self.calls = []
        self.extract_rounds = 0

    def reply(self, system: str) -> str:
        """Answers by which hat the system prompt describes."""
        if "research lead" in system:
            return json.dumps(BRIEF, ensure_ascii=False)
        if "research analyst" in system:
            self.extract_rounds += 1
            return json.dumps({
                "findings": [{"claim": "recall@5 가 0.62에서 0.81로 올랐다", "detail": "BEIR, 2025",
                              "quote": "recall improved", "source_ids": ["S1", "S2", "S404"], "strength": "strong"}],
                "gaps": ["지연 시간 수치 없음"] if self.extract_rounds <= 2 else [],
                "follow_up_queries": ["rag reranker latency benchmark"],
            }, ensure_ascii=False)
        if "editor-in-chief" in system:
            return json.dumps(OUTLINE, ensure_ascii=False)
        if "senior reviewer" in system:
            return json.dumps({"global_notes": ["전환을 매끄럽게"],
                               "sections": [{"id": "s1", "score": 3, "notes": ["수치를 넣을 것"]}]})
        if "expert author" in system:
            return "## 초안\n검색이 중요하다 [S1]."
        return "ok"  # Open Canvas follow-up and title nodes


class FakeChat(BaseChatModel):
    """A real LangChain chat model, so astream_events sees its runs and stream chunks."""
    recorder: Any

    @property
    def _llm_type(self) -> str:
        return "fake-research"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.recorder.calls.append(messages[0].content)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.recorder.reply(messages[0].content)))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        if "final editor" not in messages[0].content:
            yield ChatGenerationChunk(message=AIMessageChunk(content=self._generate(messages).generations[0].message.content))
            return
        self.recorder.calls.append(messages[0].content)
        heading = "## 왜 검색인가" if 'heading="왜 검색인가"' in messages[1].content else "## 평가 방법"
        for piece in [heading, "\n검색 품질이 답을 결정한다 [S1, S2]", " 그리고 [S77]."]:
            yield ChatGenerationChunk(message=AIMessageChunk(content=[{"type": "text", "text": piece, "index": 0}]))


async def fake_search(queries, max_results):
    return [[{"url": f"https://example.com/{q.replace(' ', '-')}/{i}", "title": f"{q} {i}", "content": "x" * 400,
              "snippet": "", "publishedDate": "2025-05-01", "score": 1 - i / 10}
             for i in range(2)] for q in queries]


class DeepResearchGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ, {
            "STORAGE_TYPE": "memory", "LANGCHAIN_TRACING_V2": "false",
            "BEDROCK_MODEL_ID": "global.anthropic.claude-sonnet-5-5",
        })
        cls.environment.start()

    @classmethod
    def tearDownClass(cls):
        cls.environment.stop()

    def run_graph(self, genre="blog"):
        from agents.open_canvas.graph import graph
        recorder = Recorder()
        model = FakeChat(recorder=recorder)
        events = []

        async def run():
            state = {"messages": [HumanMessage(content="RAG 평가 방법을 정리해줘")], "researchGenre": genre}
            config = {"configurable": {"research_asset_owner": "a" * 64}}  # set by the route from the session
            async for event in graph.astream_events(state, version="v2", config=config):
                events.append(event)

        with patch("core.bedrock_client.get_bedrock_model", return_value=model), \
                patch("agents.open_canvas.nodes.post_processing.get_bedrock_model", return_value=model), \
                patch("agents.thread_title.graph.get_bedrock_model", return_value=model), \
                patch("agents.deep_research.nodes.search_many", side_effect=fake_search), \
                patch("agents.deep_research.nodes.available_kinds", return_value=["concept"]), \
                patch("agents.deep_research.nodes.render_figure", return_value="/api/research/assets/r/fig1.png"):
            asyncio.run(run())
        return recorder, events

    def test_research_loops_until_gaps_close_then_writes_with_citations_and_figures(self):
        model, events = self.run_graph("blog")
        ends = {e["metadata"].get("langgraph_node"): e for e in events
                if e["event"] == "on_chain_end" and e["name"] == "generateArtifact"}
        markdown = ends["generateArtifact"]["data"]["output"]["artifact"]["contents"][0]["fullMarkdown"]

        self.assertEqual(model.extract_rounds, 4)  # 2 questions × 2 rounds (blog allows 2)
        self.assertTrue(markdown.startswith("# RAG 품질의 병목은 검색이다"))
        self.assertIn("[[1]](https://example.com/rag-retrieval-metrics/0)[[2]](https://example.com/rag-retrieval-metrics/1)", markdown)
        self.assertNotIn("S77", markdown)  # unknown citation dropped, never linked
        self.assertIn("![그림 1. RAG 파이프라인](/api/research/assets/r/fig1.png)", markdown)
        self.assertIn("## 참고 자료", markdown)
        self.assertLess(markdown.index("그림 1"), markdown.index("## 평가 방법"))

    def test_final_pass_streams_under_generate_artifact_node(self):
        _, events = self.run_graph("blog")
        streamed = [e for e in events if e["event"] == "on_chat_model_stream"
                    and e["metadata"].get("langgraph_node") == "generateArtifact"]
        self.assertGreater(len(streamed), 0)
        self.assertGreater(len({e["run_id"] for e in streamed}), 1)  # one model run per section

    def test_linkedin_runs_one_round_into_a_single_post(self):
        model, events = self.run_graph("linkedin")
        outline_prompt = next(c for c in model.calls if "editor-in-chief" in c)
        self.assertIn("exactly one section", outline_prompt)
        self.assertEqual(model.extract_rounds, 2)  # 2 questions × 1 round

    def test_findings_drop_sources_the_analyst_did_not_read(self):
        _, events = self.run_graph("blog")
        output = next(e["data"]["output"] for e in events
                      if e["event"] == "on_chain_end" and e["name"] == "extractFindings")
        self.assertTrue(all(sid != "S404" for f in output["findings"] for sid in f["source_ids"]))


class SourceBudgetTests(unittest.TestCase):
    def test_first_round_leaves_room_for_gap_filling_rounds(self):
        from agents.deep_research import nodes

        async def many(queries, max_results):
            return [[{"url": f"https://x.dev/{q}/{i}", "title": "t", "content": "c" * 300, "snippet": "",
                      "publishedDate": "", "score": 0} for i in range(30)] for q in queries]

        state = {"genre": "blog", "round": 0, "sources": {}, "brief": {"language": "en"},
                 "pendingQueries": [{"question_id": "Q1", "query": "a"}, {"question_id": "Q2", "query": "b"}]}
        with patch.object(nodes, "search_many", side_effect=many):
            first = asyncio.run(nodes.search_sources_node(state, {}))
            later = asyncio.run(nodes.search_sources_node(
                {**state, "round": 1, "sources": first["sources"],
                 "pendingQueries": [{"question_id": "Q1", "query": "c"}]}, {}))
        self.assertEqual(len(first["sources"]), 24)   # 60% of blog's 40
        self.assertEqual(len(later["sources"]), 40)


class AssetAccessTests(unittest.TestCase):
    def test_figures_are_served_only_to_their_owner(self):
        import hashlib
        from tempfile import TemporaryDirectory
        from fastapi.testclient import TestClient
        from agents.deep_research.diagrams.assets import run_dir

        with TemporaryDirectory() as root, patch.dict(os.environ, {
            "RESEARCH_ASSETS_DIR": root, "WORKSPACE_AUTH_MODE": "local", "WORKSPACE_LOCAL_SUB": "alice",
            "STORAGE_TYPE": "memory", "LANGCHAIN_TRACING_V2": "false",
        }):
            alice = hashlib.sha256(b"alice").hexdigest()
            (run_dir(alice, "run1") / "fig1.png").write_bytes(b"\x89PNG")
            from main import app
            with TestClient(app) as client:
                own = client.get("/api/research/assets/run1/fig1.png")
                self.assertEqual(own.status_code, 200)
                self.assertIn("private", own.headers["cache-control"])
                with patch.dict(os.environ, {"WORKSPACE_LOCAL_SUB": "bob"}):
                    self.assertEqual(client.get("/api/research/assets/run1/fig1.png").status_code, 404)


class AssembleTests(unittest.TestCase):
    sources = {"S1": {"url": "https://a.dev/x", "title": "A", "publishedDate": ""},
               "S2": {"url": "https://b.dev/y", "title": "B", "publishedDate": "2025-01-02T00:00"}}

    def test_paper_numbers_by_first_use_and_lists_references(self):
        md = assemble("T", [("s1", "## One\nx [S2]. y [S1; S2].")], [], self.sources, get_profile("paper"), "en")
        self.assertIn("x [[1]](https://b.dev/y). y [[2]](https://a.dev/x)[[1]](https://b.dev/y).", md)
        self.assertIn("## References\n\n1. [B](https://b.dev/y) (b.dev, 2025-01-02)\n2. [A](https://a.dev/x) (a.dev)", md)

    def test_finding_ids_and_repeated_title_never_reach_the_document(self):
        md = assemble("T", [("s1", "# T\n\n## One\nx [S1, F47]. y [F3].")], [], self.sources, get_profile("blog"), "en")
        self.assertTrue(md.startswith("# T\n\n## One\nx [[1]](https://a.dev/x). y.\n"))
        self.assertEqual(md.count("# T"), 1)

    def test_linkedin_strips_markers_and_has_no_reference_list(self):
        md = assemble("T", [("post", "🚀 Title\n\nBody [S1].")], [], self.sources, get_profile("linkedin"), "ko")
        self.assertEqual(md, "🚀 Title\n\nBody.\n")


if __name__ == "__main__":
    unittest.main()
