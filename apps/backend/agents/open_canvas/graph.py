"""
Open Canvas main graph implementation.
"""
from langgraph.graph import StateGraph, START, END
from agents.open_canvas.state import OpenCanvasState
from agents.open_canvas.nodes import (
    generate_path_node,
    route_node,
    route_after_followup,
    route_post_web_search,
    generate_artifact_node,
    rewrite_artifact_node,
    update_highlighted_text_node,
    rewrite_artifact_theme_node,
    custom_action_node,
    generate_followup_node,
    reflect_node,
    clean_state_node,
    generate_title_node,
    summarizer_node,
    web_search_node,
    reply_to_general_input_node,
)

# Build graph
builder = StateGraph(OpenCanvasState)
builder.add_node("generatePath", generate_path_node)
builder.add_edge(START, "generatePath")
builder.add_node("replyToGeneralInput", reply_to_general_input_node)
builder.add_node("rewriteArtifact", rewrite_artifact_node)
builder.add_node("rewriteArtifactTheme", rewrite_artifact_theme_node)
builder.add_node("updateHighlightedText", update_highlighted_text_node)
builder.add_node("generateArtifact", generate_artifact_node)
builder.add_node("customAction", custom_action_node)
builder.add_node("generateFollowup", generate_followup_node)
builder.add_node("cleanState", clean_state_node)
builder.add_node("reflect", reflect_node)
builder.add_node("generateTitle", generate_title_node)
builder.add_node("summarizer", summarizer_node)
builder.add_node("webSearch", web_search_node)
builder.add_node("routePostWebSearch", route_post_web_search)

# Add conditional edges
builder.add_conditional_edges(
    "generatePath",
    route_node,
    {
        "rewriteArtifactTheme": "rewriteArtifactTheme",
        "replyToGeneralInput": "replyToGeneralInput",
        "generateArtifact": "generateArtifact",
        "rewriteArtifact": "rewriteArtifact",
        "customAction": "customAction",
        "updateHighlightedText": "updateHighlightedText",
        "webSearch": "webSearch",
    }
)

# Add edges
builder.add_edge("generateArtifact", "generateFollowup")
builder.add_edge("updateHighlightedText", "generateFollowup")
builder.add_edge("rewriteArtifact", "generateFollowup")
builder.add_edge("rewriteArtifactTheme", "generateFollowup")
builder.add_edge("customAction", "generateFollowup")
builder.add_edge("webSearch", "routePostWebSearch")
builder.add_conditional_edges(
    "routePostWebSearch",
    lambda s: s.get("next", "generateArtifact"),
    {
        "generateArtifact": "generateArtifact",
        "rewriteArtifact": "rewriteArtifact",
    }
)
builder.add_edge("replyToGeneralInput", "generateFollowup")
builder.add_conditional_edges(
    "generateFollowup",
    route_after_followup,
    {
        "reflect": "reflect",
        "cleanState": "cleanState",
    }
)
builder.add_edge("reflect", "cleanState")
builder.add_conditional_edges(
    "cleanState",
    lambda state: state.get("_next_route", END),
    {
        END: END,
        "generateTitle": "generateTitle",
        "summarizer": "summarizer",
    }
)
builder.add_edge("generateTitle", END)
builder.add_edge("summarizer", END)

graph = builder.compile()
graph.name = "open_canvas"
