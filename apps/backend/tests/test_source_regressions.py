"""Review regressions: production query rules and retained retrieval evidence."""
import asyncio
import json
from unittest.mock import AsyncMock, patch

import boto3
from botocore.stub import Stubber

from test_source_library import OWNER, WORKSPACE, source


def test_dynamodb_exclusion_filters_keys_locally_across_empty_result_pages(tmp_path):
    from api.workspaces.persistence import Metadata

    client = boto3.client("dynamodb", region_name="ap-northeast-2",
                          aws_access_key_id="testing", aws_secret_access_key="testing")
    metadata = Metadata(tmp_path)
    metadata.local = False
    key = {"namespace": {"S": "project"}, "key": {"S": "source:one"}}
    source_item = {**key, "workspaceData": {"S": json.dumps(source(1))}}
    message_item = {"namespace": {"S": "project"}, "key": {"S": "message:one"},
                    "workspaceData": {"S": '{"content":"hello"}'}}
    expected = {
        "TableName": metadata.table, "KeyConditionExpression": "#ns = :ns",
        "ExpressionAttributeNames": {"#ns": "namespace"},
        "ExpressionAttributeValues": {":ns": {"S": "project"}}, "ConsistentRead": True,
    }
    with Stubber(client) as stubber:
        stubber.add_response("query", {"Items": [source_item], "LastEvaluatedKey": key}, expected)
        stubber.add_response("query", {"Items": [message_item]}, {**expected, "ExclusiveStartKey": key})
        with patch.object(metadata, "_client", return_value=client):
            assert metadata.items("project", exclude_prefix="source:") == {"message:one": {"content": "hello"}}


def test_same_url_retrieval_keeps_the_matching_identity_ahead_of_unrelated_aliases():
    from api.workspaces.research_sources import ResearchSources
    from core.source_catalog import SourceCatalog

    values = [
        {**source(index, "cooking ingredients " * 700), "url": "https://example.org/shared"}
        for index in range(8)
    ]
    values.append({**source(8, "Kubernetes latency=12 ms"), "url": "https://example.org/shared"})
    reader = ResearchSources(SourceCatalog("", OWNER, WORKSPACE, sources=values))
    question = {"id": "Q1", "question": "Kubernetes latency", "queries": ["Kubernetes latency"]}
    selected = reader.select({"brief": {"questions": [question]}, "round": 0})
    hydrated = reader.hydrate(next(iter(selected.values())), question, 7000)
    assert "latency=12 ms" in hydrated["content"]
    assert reader.evidence.sources[0]["id"] == "source-8"
    assert "cooking" not in hydrated["content"]


def test_passage_prefers_a_late_specific_result_over_an_early_generic_term():
    from core.source_catalog import SourceCatalog

    value = source(1, "Kubernetes overview. " + ("background material " * 600)
                   + "Kubernetes p99 latency=12 ms.")
    catalog = SourceCatalog("", OWNER, WORKSPACE, sources=[value])
    passage = catalog.passage("source-1", "Kubernetes p99 latency", 4000)
    assert "p99 latency=12 ms" in passage["source"]["excerpt"]
    assert passage["offset"] > 5000


def test_registered_followup_keeps_prior_web_evidence_for_the_same_url():
    from agents.deep_research import nodes
    from agents.deep_research.schemas import Extraction
    from api.workspaces.proposals import create_proposal
    from api.workspaces.research import run_research
    from api.workspaces.research_sources import ResearchSources
    from core.source_catalog import SourceCatalog, evidence_from_reads

    url = "https://example.org/measurements"
    stored = {**source("stored", "throughput=900 requests/s"), "url": url}
    reader = ResearchSources(SourceCatalog("", OWNER, WORKSPACE, sources=[stored]))
    state = {
        "genre": "blog", "brief": {"language": "en", "questions": [
            {"id": "Q1", "question": "latency", "queries": ["latency"]},
        ]}, "pendingQueries": [{"question_id": "Q1", "query": "latency"}], "round": 0, "sources": {},
    }
    config = {"configurable": {"workspaceSources": reader}}

    async def extract(_model, _system, content, _schema):
        fact = "latency=12 ms" if "latency=12 ms" in content else "throughput=900 requests/s"
        return Extraction.model_validate({
            "findings": [{"claim": fact, "source_ids": ["S1"], "strength": "strong"}],
            "gaps": [], "follow_up_queries": [],
        })

    async def run(_payload, _slots, _progress):
        web = [[{"url": url, "title": "Web measurement", "content": "latency=12 ms. " * 30, "score": 1}]]
        with patch.object(nodes, "search_many", new=AsyncMock(side_effect=[web, []])), \
                patch.object(nodes, "get_model", return_value=object()), \
                patch.object(nodes, "ainvoke_json", side_effect=extract):
            state.update(await nodes.search_sources_node(state, config))
            state.update(await nodes.extract_findings_node(state, config))
            state["pendingQueries"] = [{"question_id": "Q1", "query": "throughput"}]
            state.update(await nodes.search_sources_node(state, config))
            state.update(await nodes.extract_findings_node(state, config))
        state["_sourceReads"] = reader.evidence.reads
        state["_webEvidence"] = list(getattr(reader, "web_evidence", {}).values())
        state["artifact"] = {"contents": [{
            "title": "Measurements",
            "fullMarkdown": f"latency=12 ms and throughput=900 requests/s [1]({url}).",
        }]}
        return state

    with patch("api.workspaces.research._run_graph", side_effect=run):
        result = run_research({
            "ownerKey": OWNER, "workspaceId": WORKSPACE, "message": "Research",
            "researchGenre": "blog", "model": "global.anthropic.claude-sonnet-5-5", "sources": [stored],
        }, set(), lambda _: None)
    catalog = SourceCatalog("", OWNER, WORKSPACE, sources=[stored, *result["sources"]])
    retained = evidence_from_reads(catalog, result["sourceReads"]).sources
    proposal = create_proposal(result["proposals"][0], "job", "Research", retained)
    text = "\n".join(item.get("excerpt", "") for item in proposal["sources"])
    assert "latency=12 ms" in text
    assert "throughput=900 requests/s" in text


def test_last_question_uses_the_remaining_evidence_budget_instead_of_being_skipped():
    from api.workspaces.research_sources import ResearchSources
    from core.source_catalog import SourceCatalog

    values = [source(index, (f"target{index} " + "background " * 500)[:4000]) for index in range(6)]
    questions = [{"id": f"Q{index}", "question": f"target{index}", "queries": [f"target{index}"]}
                 for index in range(6)]
    reader = ResearchSources(SourceCatalog("", OWNER, WORKSPACE, sources=values))
    selected = reader.select({"brief": {"questions": questions}, "round": 0})
    for question in questions:
        candidate = next(value for value in selected.values() if question["id"] in value["question_ids"])
        reader.hydrate(candidate, question, 7000)
    assert len(reader.evidence.sources) == 6
    assert 20000 < reader.evidence.characters <= 22000
