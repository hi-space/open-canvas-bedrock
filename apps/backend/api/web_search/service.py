"""
Business logic for web search agent.
"""
from typing import Dict, Any
from agents.web_search.graph import graph


async def perform_web_search(
    messages: list,
    config: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Perform web search based on messages."""
    state = {
        "messages": messages,
        "query": None,
        "webSearchResults": None,
        "shouldSearch": False,
    }
    # Handle config
    if not config:
        config = {}
    if "configurable" in config:
        final_config = config
    else:
        final_config = {"configurable": config}
    
    return await graph.ainvoke(state, config=final_config)

