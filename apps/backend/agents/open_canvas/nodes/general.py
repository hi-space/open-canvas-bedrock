"""
General input handling node for Open Canvas graph.
"""
from typing import Dict, Any
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from agents.open_canvas.state import OpenCanvasState
from core.bedrock_client import get_bedrock_model
from core.utils import (
    get_artifact_content, get_formatted_reflections,
    format_artifact_content_with_template
)
from agents.open_canvas.prompts import (
    REPLY_TO_GENERAL_INPUT_PROMPT,
    CURRENT_ARTIFACT_PROMPT,
    NO_ARTIFACT_PROMPT,
)


async def reply_to_general_input_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Reply to general input without generating/updating artifact."""
    model = get_bedrock_model(config)
    
    # Get reflections
    reflections = get_formatted_reflections(config)
    
    # Get current artifact content
    artifact = state.get("artifact")
    current_artifact_content = get_artifact_content(artifact) if artifact else None
    
    # Build prompt
    if current_artifact_content:
        current_artifact_prompt = format_artifact_content_with_template(
            CURRENT_ARTIFACT_PROMPT,
            current_artifact_content
        )
    else:
        current_artifact_prompt = NO_ARTIFACT_PROMPT
    
    prompt = REPLY_TO_GENERAL_INPUT_PROMPT.format(
        reflections=reflections,
        current_artifact_prompt=current_artifact_prompt
    )
    
    # Get messages
    messages = state.get("_messages", state.get("messages", []))
    
    # Invoke model
    response = await model.ainvoke([
        SystemMessage(content=prompt),
        *messages,
    ])
    
    return {
        "messages": [response],
        "_messages": [response],
    }
