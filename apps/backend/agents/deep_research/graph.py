"""
Deep research writer graph.

planResearch → searchSources → extractFindings ─(gaps left)→ prepareFollowups → searchSources
                                               └→ buildOutline → createDiagrams → draftSections
                                                  → reviewDraft → generateArtifact
"""
from langgraph.graph import StateGraph, START, END

from agents.deep_research.nodes import (
    build_outline_node,
    create_diagrams_node,
    draft_sections_node,
    extract_findings_node,
    generate_artifact_node,
    plan_research_node,
    prepare_followups_node,
    review_draft_node,
    route_after_extraction,
    search_sources_node,
)
from agents.deep_research.state import DeepResearchState

builder = StateGraph(DeepResearchState)
builder.add_node("planResearch", plan_research_node)
builder.add_node("searchSources", search_sources_node)
builder.add_node("extractFindings", extract_findings_node)
builder.add_node("prepareFollowups", prepare_followups_node)
builder.add_node("buildOutline", build_outline_node)
builder.add_node("createDiagrams", create_diagrams_node)
builder.add_node("draftSections", draft_sections_node)
builder.add_node("reviewDraft", review_draft_node)
# Named like Open Canvas' own writer so the canvas streams its tokens and applies its artifact.
builder.add_node("generateArtifact", generate_artifact_node)

builder.add_edge(START, "planResearch")
builder.add_edge("planResearch", "searchSources")
builder.add_edge("searchSources", "extractFindings")
builder.add_conditional_edges(
    "extractFindings",
    route_after_extraction,
    {"prepareFollowups": "prepareFollowups", "buildOutline": "buildOutline"},
)
builder.add_edge("prepareFollowups", "searchSources")
builder.add_edge("buildOutline", "createDiagrams")
builder.add_edge("createDiagrams", "draftSections")
builder.add_edge("draftSections", "reviewDraft")
builder.add_edge("reviewDraft", "generateArtifact")
builder.add_edge("generateArtifact", END)

graph = builder.compile()
graph.name = "deep_research"
