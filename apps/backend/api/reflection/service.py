"""
Business logic for reflection agent.
"""
from typing import Dict, Any
from agents.reflection.graph import graph
from core.utils import extract_latest_artifact_version


async def run_reflection(
    messages: list,
    artifact: Dict[str, Any] = None,
    config: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Run reflection on conversation and artifact."""
    # Extract only the latest artifact version to reduce data transfer between nodes
    artifact = extract_latest_artifact_version(artifact)
    
    state = {
        "messages": messages,
        "artifact": artifact,
    }
    # Handle config - it may already have configurable nested or be flat
    if not config:
        config = {}
    if "configurable" in config:
        # Config already has configurable nested
        final_config = config
    else:
        # Config is flat, wrap it
        final_config = {"configurable": config}
    
    return await graph.ainvoke(state, config=final_config)

