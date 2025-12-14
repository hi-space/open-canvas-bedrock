"""
Web search node for Open Canvas graph.
"""
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig
from agents.open_canvas.state import OpenCanvasState
from agents.web_search.graph import graph as web_search_graph


async def web_search_node(
    state: OpenCanvasState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Perform web search."""
    web_search_state = {
        "messages": state.get("messages", []),
        "query": None,
        "webSearchResults": None,
        "shouldSearch": True,
    }
    result = await web_search_graph.ainvoke(web_search_state, config)
    return result
