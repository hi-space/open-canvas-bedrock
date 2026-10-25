"""
Deep research node for Open Canvas graph.
"""
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig
from agents.open_canvas.state import OpenCanvasState
from agents.deep_research.graph import graph as deep_research_graph


async def deep_research_node(
    state: OpenCanvasState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Research the latest request in depth and write it as the selected genre."""
    result = await deep_research_graph.ainvoke(
        {
            "messages": state.get("_messages") or state.get("messages", []),
            "genre": state["researchGenre"],
            # Set by the API route from the verified session, never from the client config.
            "assetOwner": (config.get("configurable") or {}).get("research_asset_owner"),
        },
        config,
    )
    return {
        "artifact": result["artifact"],
        "messages": result["messages"][-1:],
    }
