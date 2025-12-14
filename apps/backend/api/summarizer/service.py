"""
Business logic for summarizer agent.
"""
from typing import Dict, Any
from agents.summarizer.graph import graph


async def summarize(
    messages: list,
    thread_id: str,
    config: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Summarize conversation messages."""
    state = {
        "messages": messages,
        "threadId": thread_id,
    }
    # Handle config
    if not config:
        config = {}
    if "configurable" in config:
        final_config = config
    else:
        final_config = {"configurable": config}
    
    return await graph.ainvoke(state, config=final_config)

