"""
Routing nodes for Open Canvas graph.
"""
from typing import Dict, Any, Literal
from langchain_core.runnables import RunnableConfig
from agents.open_canvas.state import OpenCanvasState
from agents.open_canvas.generate_path import generate_path
from core.utils import create_ai_message_from_web_results


async def generate_path_node(
    state: OpenCanvasState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Generate path/routing node with URL handling, document processing, and dynamic routing."""
    return await generate_path(state, config)


async def route_node(state: OpenCanvasState) -> str:
    """Route to next node based on state."""
    next_node = state.get("next")
    if not next_node:
        raise ValueError("'next' state field not set.")
    return next_node


def route_after_followup(state: OpenCanvasState, config: RunnableConfig) -> Literal["reflect", "cleanState"]:
    """Route after generateFollowup: skip reflection if no assistant_id."""
    configurable = config.get("configurable", {}) if config else {}
    assistant_id = configurable.get("open_canvas_assistant_id")
    
    # Skip reflection if no assistant_id (no assistants mode)
    if not assistant_id:
        return "cleanState"
    return "reflect"


async def route_post_web_search(state: OpenCanvasState) -> Dict[str, Any]:
    """Route after web search."""
    artifact = state.get("artifact")
    includes_artifacts = artifact and isinstance(artifact, dict) and artifact.get("contents", [])
    web_search_results = state.get("webSearchResults", [])
    
    if not web_search_results:
        return {
            "next": "rewriteArtifact" if includes_artifacts else "generateArtifact",
            "webSearchEnabled": False,
        }
    
    web_search_message = create_ai_message_from_web_results(web_search_results)
    
    return {
        "next": "rewriteArtifact" if includes_artifacts else "generateArtifact",
        "webSearchEnabled": False,
        "messages": [web_search_message],
        "_messages": [web_search_message],
    }
