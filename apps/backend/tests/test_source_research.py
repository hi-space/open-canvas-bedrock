"""Research retrieves question-relevant passages instead of the whole library."""
import asyncio
import json
from unittest.mock import AsyncMock, patch

from test_source_library import OWNER, WORKSPACE, project, source
from test_workspace_research import research_state


def test_research_runs_with_an_over_old_limit_source_library(project):
    from api.workspaces.research import run_research
    from api.workspaces.sources import SourceLibrary

    with project.lock():
        library = SourceLibrary(project)
        for index in range(60):
            library.put(source(index, "Earlier unrelated evidence. " * 100))
        snapshot = library.snapshot()
    with patch("api.workspaces.research._run_graph", new=AsyncMock(return_value=research_state())):
        result = run_research({
            "ownerKey": OWNER, "workspaceId": WORKSPACE, "sourceSnapshot": snapshot,
            "message": "New research", "model": "global.anthropic.claude-sonnet-5-5",
            "history": [], "researchGenre": "blog", "sources": [],
        }, set(), lambda _message: None)
    assert len(result["sources"]) == 2
    assert result["proposals"][0]["path"].endswith(".md")
    assert len(result["sourceReads"]) == 2


def test_research_extracts_only_relevant_passages_and_records_actual_prompt_ranges(project):
    from agents.deep_research import nodes
    from agents.deep_research.schemas import Extraction
    from api.workspaces.research_sources import ResearchSources
    from api.workspaces.sources import SourceLibrary
    from core.source_catalog import SourceCatalog

    with project.lock():
        library = SourceLibrary(project)
        for index in range(60):
            library.put(source(index, "UNRELATED_COOKING_RECIPE"))
        library.put(source(60, "배경 " * 3000 + "Kubernetes 오토스케일링 지연은 12초입니다."))
        library.put(source(61, "벡터 검색 recall 측정 결과는 91%입니다."))
        snapshot = library.snapshot()
    reader = ResearchSources(SourceCatalog(project.root, OWNER, WORKSPACE, snapshot))
    questions = [
        {"id": "Q1", "question": "Kubernetes 오토스케일링 지연", "queries": ["autoscaling"]},
        {"id": "Q2", "question": "벡터 검색 recall 측정", "queries": ["vector recall"]},
    ]
    state = {
        "genre": "blog", "brief": {"questions": questions, "language": "ko"},
        "pendingQueries": [], "sources": {}, "round": 0,
    }
    config = {"configurable": {"workspaceSources": reader}}
    received = []

    async def extract(_model, _system, content, _schema):
        received.append(content)
        return Extraction(findings=[], gaps=[], follow_up_queries=[])

    async def run():
        with patch.object(nodes, "search_many", new=AsyncMock(return_value=[])):
            state.update(await nodes.search_sources_node(state, config))
        assert reader.evidence.reads == []  # Selecting a candidate is not reading it.
        with patch.object(nodes, "get_model", return_value=object()), \
                patch.object(nodes, "ainvoke_json", side_effect=extract):
            state.update(await nodes.extract_findings_node(state, config))

    asyncio.run(run())
    assert len(received) == 2
    assert "오토스케일링 지연은 12초" in received[0]
    assert "벡터 검색 recall" not in received[0]
    assert "벡터 검색 recall" in received[1]
    assert "오토스케일링 지연은 12초" not in received[1]
    assert "UNRELATED_COOKING_RECIPE" not in json.dumps(received)
    assert {read["id"] for read in reader.evidence.reads} == {"source-60", "source-61"}
    assert reader.evidence.reads[0]["ranges"][0][0] > 0
    assert reader.evidence.characters <= 32000


def test_followup_can_read_a_different_passage_of_an_already_used_source():
    from agents.deep_research import nodes
    from agents.deep_research.schemas import Extraction
    from api.workspaces.research_sources import ResearchSources
    from core.source_catalog import SourceCatalog

    text = "latency=12. " + ("배경 " * 3000) + "throughput=900."
    reader = ResearchSources(SourceCatalog("", OWNER, WORKSPACE, sources=[source(1, text)]))
    state = {
        "genre": "blog", "brief": {"language": "en", "questions": [
            {"id": "Q1", "question": "latency", "queries": ["latency"]},
        ]}, "pendingQueries": [], "sources": {}, "round": 0,
    }
    config = {"configurable": {"workspaceSources": reader}}
    received = []

    async def extract(_model, _system, content, _schema):
        received.append(content)
        return Extraction(findings=[], gaps=[], follow_up_queries=[])

    async def run():
        with patch.object(nodes, "search_many", new=AsyncMock(return_value=[])), \
                patch.object(nodes, "get_model", return_value=object()), \
                patch.object(nodes, "ainvoke_json", side_effect=extract):
            state.update(await nodes.search_sources_node(state, config))
            state.update(await nodes.extract_findings_node(state, config))
            state["pendingQueries"] = [{"question_id": "Q1", "query": "throughput"}]
            state.update(await nodes.search_sources_node(state, config))
            state.update(await nodes.extract_findings_node(state, config))

    asyncio.run(run())
    assert len(received) == 2
    assert "throughput=900." not in received[0]
    assert "throughput=900." in received[1]
    assert len(reader.evidence.reads[0]["ranges"]) == 2
