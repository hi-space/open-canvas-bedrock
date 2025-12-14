"""
Thread title generation graph.
"""
from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START
from agents.thread_title.state import TitleGenerationState
from agents.thread_title.prompts import TITLE_SYSTEM_PROMPT, TITLE_USER_PROMPT
from core.bedrock_client import get_bedrock_model


@tool
def generate_title(title: str) -> Dict[str, Any]:
    """Generate a concise title for the conversation.
    
    Args:
        title: The generated title for the conversation.
    
    Returns:
        Dictionary with title.
    """
    return {"title": title}


async def generate_title_node(
    state: TitleGenerationState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Generate title for the conversation."""
    configurable = config.get("configurable", {}) if config else {}
    thread_id = configurable.get("open_canvas_thread_id")
    
    if not thread_id:
        raise ValueError("open_canvas_thread_id not found in configurable")
    
    # Get artifact content
    artifact = state.get("artifact")
    artifact_content = None
    if artifact:
        if isinstance(artifact, dict):
            if "contents" in artifact and artifact["contents"]:
                content = artifact["contents"][0]
                if isinstance(content, dict):
                    if "fullMarkdown" in content:
                        artifact_content = content["fullMarkdown"]
                    elif "code" in content:
                        artifact_content = content["code"]
    
    artifact_context = (
        f"An artifact was generated during this conversation:\n\n{artifact_content}"
        if artifact_content
        else "No artifact was generated during this conversation."
    )
    
    # Format messages
    messages = state.get("messages", [])
    conversation = "\n\n".join([
        f"<{msg.__class__.__name__}>\n{msg.content}\n</{msg.__class__.__name__}>"
        for msg in messages
    ])
    
    # Get model
    model = get_bedrock_model(config, temperature=0)
    model_with_tools = model.bind_tools([generate_title], tool_choice="generate_title")
    
    # Format prompts
    formatted_user_prompt = TITLE_USER_PROMPT.replace(
        "{conversation}",
        conversation
    ).replace("{artifact_context}", artifact_context)
    
    # Invoke model
    result = await model_with_tools.ainvoke([
        SystemMessage(content=TITLE_SYSTEM_PROMPT),
        HumanMessage(content=formatted_user_prompt),
    ])
    
    # Extract tool call
    tool_calls = result.tool_calls if hasattr(result, "tool_calls") else []
    if not tool_calls:
        raise ValueError("Title generation tool call failed.")
    
    title_tool_call = tool_calls[0]
    title = title_tool_call["args"].get("title", "")
    
    # Update thread metadata (simplified - in real implementation, use LangGraph client)
    # For now, return the title
    return {
        "title": title,
        "thread_id": thread_id
    }


# Build graph
builder = StateGraph(TitleGenerationState)
builder.add_node("generateThreadTitle", generate_title_node)
builder.add_edge(START, "generateThreadTitle")

graph = builder.compile()
graph.name = "thread_title"

