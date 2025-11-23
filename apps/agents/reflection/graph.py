"""
Reflection graph implementation.
"""
from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START
from reflection.state import ReflectionGraphState
from reflection.prompts import REFLECT_SYSTEM_PROMPT, REFLECT_USER_PROMPT
from utils import format_reflections
from bedrock_client import get_bedrock_model
from store.store import store


@tool
def generate_reflections(styleRules: list[str], content: list[str]) -> Dict[str, Any]:
    """Generate reflections based on the context provided.
    
    Args:
        styleRules: The complete new list of style rules and guidelines.
        content: The complete new list of memories/facts about the user.
    
    Returns:
        Dictionary with styleRules and content.
    """
    return {"styleRules": styleRules, "content": content}


async def reflect_node(
    state: ReflectionGraphState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Reflect on the conversation and artifact."""
    configurable = config.get("configurable", {}) if config else {}
    assistant_id = configurable.get("open_canvas_assistant_id")
    
    if not assistant_id:
        raise ValueError("Assistant ID is required for reflections.")
    
    # Get existing reflections from store
    namespace = ["memories", assistant_id]
    key = "reflection"
    store_item = store.get_item(namespace, key)
    existing_reflections = {}
    if store_item and store_item.get("value"):
        existing_reflections = store_item["value"]
    
    memories_as_string = format_reflections(existing_reflections) if existing_reflections else "No reflections found."
    
    # Get artifact content
    artifact = state.get("artifact")
    artifact_content = "No artifact found."
    if artifact:
        if isinstance(artifact, dict):
            if "contents" in artifact and artifact["contents"]:
                content = artifact["contents"][0]
                if isinstance(content, dict):
                    if "fullMarkdown" in content:
                        artifact_content = content["fullMarkdown"]
                    elif "code" in content:
                        artifact_content = content["code"]
        artifact_content = str(artifact_content)
    
    # Format messages
    messages = state.get("messages", [])
    conversation = "\n\n".join([
        f"<{msg.__class__.__name__}>\n{msg.content}\n</{msg.__class__.__name__}>"
        for msg in messages
    ])
    
    # Get model
    model = get_bedrock_model(config, temperature=0)
    model_with_tools = model.bind_tools([generate_reflections], tool_choice="generate_reflections")
    
    # Format prompts
    formatted_system_prompt = REFLECT_SYSTEM_PROMPT.replace(
        "{artifact}",
        artifact_content
    ).replace("{reflections}", memories_as_string)
    
    formatted_user_prompt = REFLECT_USER_PROMPT.replace(
        "{conversation}",
        conversation
    )
    
    # Invoke model
    result = await model_with_tools.ainvoke([
        SystemMessage(content=formatted_system_prompt),
        HumanMessage(content=formatted_user_prompt),
    ])
    
    # Extract tool call
    tool_calls = result.tool_calls if hasattr(result, "tool_calls") else []
    if not tool_calls:
        raise ValueError("Reflection tool call failed.")
    
    reflection_tool_call = tool_calls[0]
    new_memories = {
        "styleRules": reflection_tool_call["args"].get("styleRules", []),
        "content": reflection_tool_call["args"].get("content", []),
    }
    
    # Store new memories to store
    namespace = ["memories", assistant_id]
    key = "reflection"
    store.put_item(namespace, key, new_memories)
    
    return {
        "reflections": new_memories
    }


# Build graph
builder = StateGraph(ReflectionGraphState)
builder.add_node("reflect", reflect_node)
builder.add_edge(START, "reflect")

graph = builder.compile()
graph.name = "reflection"

