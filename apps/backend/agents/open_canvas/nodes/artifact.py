"""
Artifact generation and modification nodes.
"""
from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from agents.open_canvas.state import OpenCanvasState
from core.bedrock_client import get_bedrock_model
from core.utils import (
    format_messages, format_reflections, get_model_config,
    get_artifact_content, is_artifact_markdown_content,
    get_formatted_reflections, format_artifact_content_with_template,
    is_thinking_model, extract_thinking_and_response_tokens,
    estimate_input_size, truncate_content
)
from agents.open_canvas.prompts import (
    GENERATE_ARTIFACT_PROMPT,
    UPDATE_HIGHLIGHTED_TEXT_PROMPT,
    FOLLOWUP_ARTIFACT_PROMPT,
    CHANGE_ARTIFACT_LANGUAGE_PROMPT,
    CHANGE_ARTIFACT_READING_LEVEL_PROMPT,
    CHANGE_ARTIFACT_TO_PIRATE_PROMPT,
    CHANGE_ARTIFACT_LENGTH_PROMPT,
    ADD_EMOJIS_TO_ARTIFACT_PROMPT,
    CUSTOM_ACTION_REFLECTIONS_PROMPT,
    CUSTOM_ACTION_PREFIX_PROMPT,
    CURRENT_ARTIFACT_PROMPT,
    NO_ARTIFACT_PROMPT,
)
from agents.open_canvas.rewrite_artifact_utils import (
    build_meta_prompt,
    build_rewrite_prompt,
    create_new_artifact_content
)
from store.store import store
import uuid


async def generate_artifact_node(
    state: OpenCanvasState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Generate a new artifact."""
    model = get_bedrock_model(config)
    
    # Get reflections (simplified)
    configurable = config.get("configurable", {}) if config else {}
    reflections_dict = configurable.get("reflections", {})
    reflections = format_reflections(reflections_dict) if reflections_dict else "No reflections found."
    
    # Format messages with size limit
    messages = state.get("_messages", state.get("messages", []))
    
    # Estimate maximum safe input size
    MAX_SAFE_INPUT_SIZE = 200 * 1024  # 200KB of text
    reflections_size = estimate_input_size(reflections)
    reserved_size = 2000  # For prompt template and system message
    available_for_conversation = MAX_SAFE_INPUT_SIZE - reflections_size - reserved_size
    
    if available_for_conversation > 0:
        conversation = format_messages(messages, max_length=available_for_conversation)
    else:
        conversation = format_messages(messages, max_length=MAX_SAFE_INPUT_SIZE // 2)
        print(f"Warning: Reflections are very large ({reflections_size} chars). "
              f"Truncating conversation history.", flush=True)
    
    # Build prompt
    prompt = GENERATE_ARTIFACT_PROMPT.format(
        reflections=reflections,
        conversation=conversation
    )
    
    # Use astream for streaming responses
    # Accumulate the full response for the final artifact
    # Note: ChatBedrockConverse returns content as a list of dicts with 'text' keys
    full_content = ""
    async for chunk in model.astream([
        SystemMessage(content="You are a helpful AI assistant."),
        HumanMessage(content=prompt),
    ]):
        if hasattr(chunk, "content"):
            if isinstance(chunk.content, str):
                chunk_content = chunk.content
            elif isinstance(chunk.content, list):
                # ChatBedrockConverse returns content as list of dicts: [{'type': 'text', 'text': '...', 'index': 0}]
                chunk_content = "".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in chunk.content
                )
            else:
                chunk_content = str(chunk.content)
            full_content += chunk_content
        else:
            full_content += str(chunk)
    
    # Create final response message
    response = AIMessage(content=full_content)
    
    # Create artifact without title (title will be set by frontend using thread title)
    artifact = {
        "type": "text",
        "contents": [{
            "type": "text",
            "index": 1,
            "fullMarkdown": full_content
        }]
    }
    
    return {
        "artifact": artifact,
        "messages": [response]
    }


async def update_highlighted_text_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Update highlighted text in markdown artifact."""
    # Get model
    model_config = get_model_config(config)
    model_name = model_config.get("modelName", "")
    
    # For Bedrock, use configured model (TypeScript version has fallback logic)
    model = get_bedrock_model(config)
    
    # Get current artifact content
    artifact = state.get("artifact")
    current_artifact_content = get_artifact_content(artifact) if artifact else None
    
    if not current_artifact_content:
        raise ValueError("No artifact found")
    
    if not is_artifact_markdown_content(current_artifact_content):
        raise ValueError("Artifact is not markdown content")
    
    highlighted_text_data = state.get("highlightedText")
    if not highlighted_text_data:
        raise ValueError("Cannot partially regenerate an artifact without a highlight")
    
    markdown_block = highlighted_text_data.get("markdownBlock", "")
    selected_text = highlighted_text_data.get("selectedText", "")
    full_markdown = highlighted_text_data.get("fullMarkdown", "")
    
    # Build prompt
    formatted_prompt = UPDATE_HIGHLIGHTED_TEXT_PROMPT.format(
        highlightedText=selected_text,
        textBlocks=markdown_block
    )
    
    # Get recent user message
    messages = state.get("_messages", state.get("messages", []))
    recent_user_message = messages[-1] if messages else None
    
    if not recent_user_message or not isinstance(recent_user_message, HumanMessage):
        raise ValueError("Expected a human message")
    
    # Stream model for real-time updates
    response_content = ""
    async for chunk in model.astream([
        SystemMessage(content=formatted_prompt),
        recent_user_message,
    ]):
        if hasattr(chunk, "content"):
            if isinstance(chunk.content, str):
                chunk_content = chunk.content
            elif isinstance(chunk.content, list):
                chunk_content = "".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in chunk.content
                )
            else:
                chunk_content = str(chunk.content)
            response_content += chunk_content
        else:
            response_content += str(chunk)
    
    # Update artifact
    contents = artifact.get("contents", [])
    current_index = artifact.get("currentIndex", len(contents))
    
    # Find previous content
    prev_content = None
    for content in contents:
        if content.get("index") == current_index and content.get("type") == "text":
            prev_content = content
            break
    
    if not prev_content:
        raise ValueError("Previous content not found")
    
    if markdown_block not in full_markdown:
        raise ValueError("Selected text not found in current content")
    
    new_full_markdown = full_markdown.replace(markdown_block, response_content)
    new_curr_index = len(contents) + 1
    
    updated_artifact_content = {
        **prev_content,
        "index": new_curr_index,
        "fullMarkdown": new_full_markdown,
    }
    
    return {
        "artifact": {
            **artifact,
            "currentIndex": new_curr_index,
            "contents": contents + [updated_artifact_content],
        },
    }


async def rewrite_artifact_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Rewrite entire artifact."""
    model = get_bedrock_model(config)
    model_config = get_model_config(config)
    model_name = model_config.get("modelName", "")
    
    # Get reflections
    reflections = get_formatted_reflections(config)
    
    # Get current artifact content
    artifact = state.get("artifact")
    current_artifact_content = get_artifact_content(artifact) if artifact else None
    
    if not current_artifact_content:
        raise ValueError("No artifact found")
    
    # Get artifact content string
    artifact_content = current_artifact_content.get("fullMarkdown", "")
    
    # Optionally update artifact meta using LLM
    # Use current artifact content as fallback
    artifact_meta = {
        "type": "text",
        "title": current_artifact_content.get("title", "Untitled"),
        "language": "other"
    }
    artifact_type = "text"
    is_new_type = False
    
    # Build meta prompt
    meta_prompt = build_meta_prompt(artifact_meta) if is_new_type else ""
    
    # Build full prompt
    formatted_prompt = build_rewrite_prompt(
        artifact_content,
        reflections,
        meta_prompt
    )
    
    # Get recent human message
    messages = state.get("_messages", state.get("messages", []))
    recent_human_message = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            recent_human_message = msg
            break
    
    if not recent_human_message:
        raise ValueError("No recent human message found")
    
    # Stream model for real-time updates
    artifact_content_text = ""
    async for chunk in model.astream([
        SystemMessage(content=formatted_prompt),
        recent_human_message,
    ]):
        if hasattr(chunk, "content"):
            if isinstance(chunk.content, str):
                chunk_content = chunk.content
            elif isinstance(chunk.content, list):
                chunk_content = "".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in chunk.content
                )
            else:
                chunk_content = str(chunk.content)
            artifact_content_text += chunk_content
        else:
            artifact_content_text += str(chunk)
    
    # Handle thinking models
    thinking_message = None
    if is_thinking_model(model_name):
        extracted = extract_thinking_and_response_tokens(artifact_content_text)
        if extracted["thinking"]:
            thinking_message = AIMessage(
                id=f"thinking-{uuid.uuid4()}",
                content=extracted["thinking"]
            )
        artifact_content_text = extracted["response"]
    
    # Create new artifact content
    new_artifact_content = create_new_artifact_content(
        artifact_type,
        state,
        current_artifact_content,
        artifact_meta,
        artifact_content_text
    )
    
    contents = artifact.get("contents", [])
    result = {
        "artifact": {
            **artifact,
            "currentIndex": new_artifact_content["index"],
            "contents": contents + [new_artifact_content],
        },
    }
    
    if thinking_message:
        result["messages"] = [thinking_message]
        result["_messages"] = [thinking_message]
    
    return result


async def rewrite_artifact_theme_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Rewrite artifact theme (language, length, reading level, emojis)."""
    model = get_bedrock_model(config)
    model_config = get_model_config(config)
    model_name = model_config.get("modelName", "")
    
    # Get reflections
    reflections = get_formatted_reflections(config)
    
    # Get current artifact content
    artifact = state.get("artifact")
    current_artifact_content = get_artifact_content(artifact) if artifact else None
    
    if not current_artifact_content:
        raise ValueError("No artifact found")
    
    if not is_artifact_markdown_content(current_artifact_content):
        raise ValueError("Current artifact content is not markdown")
    
    artifact_content = current_artifact_content.get("fullMarkdown", "")
    
    # Determine which prompt to use
    if state.get("language"):
        formatted_prompt = CHANGE_ARTIFACT_LANGUAGE_PROMPT.format(
            newLanguage=state.get("language"),
            artifactContent=artifact_content,
            reflections=reflections
        )
    elif state.get("readingLevel"):
        reading_level = state.get("readingLevel")
        if reading_level == "pirate":
            formatted_prompt = CHANGE_ARTIFACT_TO_PIRATE_PROMPT.format(
                artifactContent=artifact_content,
                reflections=reflections
            )
        else:
            # Map reading level
            level_map = {
                "child": "elementary school student",
                "teenager": "high school student",
                "college": "college student",
                "phd": "PhD student",
            }
            new_reading_level = level_map.get(reading_level, reading_level)
            formatted_prompt = CHANGE_ARTIFACT_READING_LEVEL_PROMPT.format(
                newReadingLevel=new_reading_level,
                artifactContent=artifact_content,
                reflections=reflections
            )
    elif state.get("artifactLength"):
        length_map = {
            "shortest": "much shorter than it currently is",
            "short": "slightly shorter than it currently is",
            "long": "slightly longer than it currently is",
            "longest": "much longer than it currently is",
        }
        new_length = length_map.get(state.get("artifactLength"), state.get("artifactLength"))
        formatted_prompt = CHANGE_ARTIFACT_LENGTH_PROMPT.format(
            newLength=new_length,
            artifactContent=artifact_content,
            reflections=reflections
        )
    elif state.get("regenerateWithEmojis"):
        formatted_prompt = ADD_EMOJIS_TO_ARTIFACT_PROMPT.format(
            artifactContent=artifact_content,
            reflections=reflections
        )
    else:
        raise ValueError("No theme selected")
    
    # Invoke model
    response = await model.ainvoke([
        HumanMessage(content=formatted_prompt),
    ])
    
    # Extract content
    artifact_content_text = response.content
    if isinstance(artifact_content_text, list):
        artifact_content_text = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in artifact_content_text
        )
    elif not isinstance(artifact_content_text, str):
        artifact_content_text = str(artifact_content_text)
    
    # Handle thinking models
    thinking_message = None
    if is_thinking_model(model_name):
        extracted = extract_thinking_and_response_tokens(artifact_content_text)
        if extracted["thinking"]:
            thinking_message = AIMessage(
                id=f"thinking-{uuid.uuid4()}",
                content=extracted["thinking"]
            )
        artifact_content_text = extracted["response"]
    
    # Create new artifact
    contents = artifact.get("contents", [])
    new_index = len(contents) + 1
    
    new_artifact_content = {
        **current_artifact_content,
        "index": new_index,
        "fullMarkdown": artifact_content_text,
    }
    
    result = {
        "artifact": {
            **artifact,
            "currentIndex": new_index,
            "contents": contents + [new_artifact_content],
        },
    }
    
    if thinking_message:
        result["messages"] = [thinking_message]
        result["_messages"] = [thinking_message]
    
    return result


async def custom_action_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Handle custom quick action."""
    custom_quick_action_id = state.get("customQuickActionId")
    if not custom_quick_action_id:
        raise ValueError("No custom quick action ID found.")
    
    model = get_bedrock_model(config)
    
    # Get user_id from config
    configurable = config.get("configurable", {}) if config else {}
    user_id = configurable.get("userId", "anonymous")
    
    # Get custom actions from store
    namespace = ["custom_actions", user_id]
    key = "actions"
    store_item = store.get_item(namespace, key)
    
    if not store_item or not store_item.get("value"):
        raise ValueError(f"No custom actions found for user {user_id}.")
    
    custom_actions = store_item["value"]
    if not isinstance(custom_actions, dict):
        raise ValueError(f"Invalid custom actions format for user {user_id}.")
    
    custom_quick_action = custom_actions.get(custom_quick_action_id)
    if not custom_quick_action:
        raise ValueError(f"No custom quick action found from ID {custom_quick_action_id} for user {user_id}")
    
    # Get reflections if needed
    reflections = ""
    if custom_quick_action.get("includeReflections"):
        reflections = get_formatted_reflections(config)
        reflections_prompt = CUSTOM_ACTION_REFLECTIONS_PROMPT.format(reflections=reflections)
    else:
        reflections_prompt = ""
    
    # Build prompt
    formatted_prompt = f"<custom-instructions>\n{custom_quick_action.get('prompt', '')}\n</custom-instructions>"
    
    if reflections_prompt:
        formatted_prompt += f"\n\n{reflections_prompt}"
    
    if custom_quick_action.get("includePrefix"):
        formatted_prompt = CUSTOM_ACTION_PREFIX_PROMPT.format(custom_instructions=formatted_prompt)
    
    if custom_quick_action.get("includeRecentHistory"):
        messages = state.get("_messages", state.get("messages", []))
        recent_messages = messages[-5:] if len(messages) > 5 else messages
        conversation = "\n".join([
            f"<{msg.__class__.__name__}>\n{msg.content if isinstance(msg.content, str) else str(msg.content)}\n</{msg.__class__.__name__}>"
            for msg in recent_messages
        ])
        formatted_prompt += f"\n\nHere is the recent conversation history:\n<conversation>\n{conversation}\n</conversation>"
    
    # Get artifact content
    artifact = state.get("artifact")
    current_artifact_content = get_artifact_content(artifact) if artifact else None
    
    if current_artifact_content:
        artifact_content = current_artifact_content.get("fullMarkdown", "")
    else:
        artifact_content = "No artifacts generated yet."
    
    formatted_prompt += f"\n\nHere is the current artifact content:\n<artifact-content>\n{artifact_content}\n</artifact-content>"
    
    # Stream model for real-time updates
    new_content = ""
    async for chunk in model.astream([
        HumanMessage(content=formatted_prompt),
    ]):
        if hasattr(chunk, "content"):
            if isinstance(chunk.content, str):
                chunk_content = chunk.content
            elif isinstance(chunk.content, list):
                chunk_content = "".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in chunk.content
                )
            else:
                chunk_content = str(chunk.content)
            new_content += chunk_content
        else:
            new_content += str(chunk)
    
    if not current_artifact_content:
        return {}
    
    # Create new artifact content
    contents = artifact.get("contents", [])
    new_index = len(contents) + 1
    
    new_artifact_content = {
        **current_artifact_content,
        "index": new_index,
        "fullMarkdown": new_content,
    }
    
    return {
        "artifact": {
            **artifact,
            "currentIndex": new_index,
            "contents": contents + [new_artifact_content],
        },
    }
