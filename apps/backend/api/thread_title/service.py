"""
Business logic for thread title agent.
"""
from typing import Dict, Any
from agents.thread_title.graph import graph


async def generate_title(
    messages: list,
    artifact: Dict[str, Any] = None,
    config: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Generate title for conversation."""
    state = {
        "messages": messages,
        "artifact": artifact,
    }
    # Handle config
    if not config:
        config = {}
    if "configurable" in config:
        final_config = config
    else:
        final_config = {"configurable": config}
    
    return await graph.ainvoke(state, config=final_config)

