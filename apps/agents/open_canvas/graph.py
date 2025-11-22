"""
Open Canvas main graph implementation.
"""
from typing import Dict, Any, Literal
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from open_canvas.state import OpenCanvasState
from bedrock_client import get_bedrock_model
from utils import (
    format_messages, format_reflections, get_model_config,
    get_artifact_content, is_artifact_code_content, is_artifact_markdown_content,
    get_formatted_reflections, format_artifact_content_with_template,
    is_thinking_model, extract_thinking_and_response_tokens
)
from reflection.graph import graph as reflection_graph
from web_search.graph import graph as web_search_graph
from summarizer.graph import graph as summarizer_graph
from thread_title.graph import graph as thread_title_graph

# Character limit for summarization (~ 4 chars per token, max tokens of 75000)
CHARACTER_MAX = 300000


async def generate_path_node(
    state: OpenCanvasState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Generate path/routing node."""
    # Routing logic based on state
    if state.get("highlightedCode"):
        return {"next": "updateArtifact"}
    if state.get("highlightedText"):
        return {"next": "updateHighlightedText"}
    if state.get("language") or state.get("artifactLength") or state.get("regenerateWithEmojis") or state.get("readingLevel"):
        return {"next": "rewriteArtifactTheme"}
    if state.get("addComments") or state.get("addLogs") or state.get("portLanguage") or state.get("fixBugs"):
        return {"next": "rewriteCodeArtifactTheme"}
    if state.get("customQuickActionId"):
        return {"next": "customAction"}
    if state.get("webSearchEnabled"):
        return {"next": "webSearch"}
    if state.get("artifact"):
        return {"next": "rewriteArtifact"}
    return {"next": "generateArtifact"}


async def route_node(state: OpenCanvasState) -> str:
    """Route to next node based on state."""
    next_node = state.get("next")
    if not next_node:
        raise ValueError("'next' state field not set.")
    return next_node


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
    
    # Format messages
    messages = state.get("_messages", state.get("messages", []))
    conversation = format_messages(messages)
    
    # Build prompt
    prompt = f"""You are an AI assistant tasked with generating a new artifact based on the user's request.
Ensure you use markdown syntax when appropriate, as the text you generate will be rendered in markdown.

Use the full chat history as context when generating the artifact.

Follow these rules and guidelines:
- Do not wrap it in any XML tags you see in this prompt.
- If writing code, do not add inline comments unless the user has specifically requested them.
- Do NOT include triple backticks when generating code. The code should be in plain text.

You also have the following reflections on style guidelines and general memories/facts about the user:
{reflections}

Here is the conversation:
{conversation}

Generate the artifact based on the user's request."""
    
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
    from langchain_core.messages import AIMessage
    response = AIMessage(content=full_content)
    
    # Create artifact (simplified structure)
    artifact = {
        "type": "text",  # Could be determined by model
        "title": "Generated Artifact",
        "contents": [{
            "fullMarkdown": full_content
        }]
    }
    
    return {
        "artifact": artifact,
        "messages": [response]
    }


async def generate_followup_node(
    state: OpenCanvasState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Generate followup message after artifact generation."""
    from open_canvas.prompts import FOLLOWUP_ARTIFACT_PROMPT
    
    model = get_bedrock_model(config)
    
    # Get artifact content
    artifact = state.get("artifact")
    artifact_content = ""
    if artifact:
        current_content = get_artifact_content(artifact)
        if current_content:
            if current_content.get("type") == "code":
                artifact_content = current_content.get("code", "")
            else:
                artifact_content = current_content.get("fullMarkdown", "")
    
    # Get reflections
    reflections = get_formatted_reflections(config)
    
    # Get conversation history
    messages = state.get("messages", [])
    conversation = format_messages(messages)
    
    # Build prompt
    prompt = FOLLOWUP_ARTIFACT_PROMPT.format(
        artifactContent=artifact_content,
        reflections=reflections,
        conversation=conversation
    )
    
    response = await model.ainvoke([
        SystemMessage(content="You are a helpful AI assistant."),
        HumanMessage(content=prompt),
    ])
    
    return {
        "messages": [response]
    }


async def reflect_node(
    state: OpenCanvasState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Reflect on conversation and artifact."""
    # Use reflection graph
    reflection_state = {
        "messages": state.get("messages", []),
        "artifact": state.get("artifact"),
    }
    result = await reflection_graph.ainvoke(reflection_state, config)
    return {}


async def clean_state_node(state: OpenCanvasState) -> Dict[str, Any]:
    """Clean state after processing."""
    return {
        "next": None,
        "highlightedCode": None,
        "highlightedText": None,
        "language": None,
        "artifactLength": None,
        "regenerateWithEmojis": None,
        "readingLevel": None,
        "addComments": None,
        "addLogs": None,
        "portLanguage": None,
        "fixBugs": None,
        "customQuickActionId": None,
        "webSearchEnabled": None,
    }


def simple_token_calculator(state: OpenCanvasState) -> Literal["summarizer", "END"]:
    """Calculate if summarization is needed."""
    messages = state.get("_messages", state.get("messages", []))
    total_chars = sum(
        len(msg.content) if isinstance(msg.content, str) else len(str(msg.content))
        for msg in messages
    )
    if total_chars > CHARACTER_MAX:
        return "summarizer"
    return END


def conditionally_generate_title(state: OpenCanvasState) -> Literal["generateTitle", "summarizer", "END"]:
    """Conditionally route to title generation."""
    messages = state.get("messages", [])
    if len(messages) > 2:
        return simple_token_calculator(state)
    return "generateTitle"


async def generate_title_node(
    state: OpenCanvasState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Generate title for conversation.
    
    Based on origin implementation, this should:
    1. Skip if messages.length > 2 (not first human-AI conversation)
    2. Try to generate title, but continue even if it fails
    3. Map thread_id to open_canvas_thread_id for thread_title graph
    """
    # Skip if it's not first human-AI conversation (should never occur in practice
    # due to the conditional edge which is called before this node)
    messages = state.get("messages", [])
    if len(messages) > 2:
        return {}
    
    # Map thread_id to open_canvas_thread_id for thread_title graph
    configurable = config.get("configurable", {}) if config else {}
    thread_id = configurable.get("thread_id")
    
    # If thread_id is not available, skip title generation gracefully
    if not thread_id:
        # Return empty dict to continue without error (origin uses try-catch)
        return {}
    
    title_state = {
        "messages": messages,
        "artifact": state.get("artifact"),
    }
    
    title_config = {
        "configurable": {
            **configurable,
            "open_canvas_thread_id": thread_id,
        }
    }
    
    # Try to generate title, but continue even if it fails (origin pattern)
    try:
        result = await thread_title_graph.ainvoke(title_state, config=title_config)
    except Exception as e:
        # Log error but continue without failing (origin pattern)
        import sys
        print(f"Failed to call generate title graph: {e}", file=sys.stderr, flush=True)
        # Return empty dict to continue without error
        return {}
    
    return {}


async def summarizer_node(
    state: OpenCanvasState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Summarize messages if too long."""
    summarizer_state = {
        "messages": state.get("_messages", state.get("messages", [])),
        "threadId": config.get("configurable", {}).get("thread_id", ""),
    }
    result = await summarizer_graph.ainvoke(summarizer_state, config)
    return result


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


async def route_post_web_search(state: OpenCanvasState) -> Dict[str, Any]:
    """Route after web search."""
    artifact = state.get("artifact")
    includes_artifacts = artifact and isinstance(artifact, dict) and artifact.get("contents", [])
    web_search_results = state.get("webSearchResults", [])
    
    if not web_search_results:
        return {
            "next": "rewriteArtifact" if includes_artifacts else "generateArtifact",
            "webSearchEnabled": False,
        }
    
    from utils import create_ai_message_from_web_results
    web_search_message = create_ai_message_from_web_results(web_search_results)
    
    return {
        "next": "rewriteArtifact" if includes_artifacts else "generateArtifact",
        "webSearchEnabled": False,
        "messages": [web_search_message],
        "_messages": [web_search_message],
    }


# Implemented nodes
async def update_artifact_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Update artifact based on highlighted code."""
    from langchain_core.messages import HumanMessage, AIMessage
    from open_canvas.prompts import UPDATE_HIGHLIGHTED_ARTIFACT_PROMPT
    
    # Get model - for Bedrock, we'll use the configured model
    # Note: TypeScript version has fallback to gpt-4o for non-OpenAI models
    # For Bedrock, we'll use the configured model
    model = get_bedrock_model(config)
    
    # Get reflections
    reflections = get_formatted_reflections(config)
    
    # Get current artifact content
    artifact = state.get("artifact")
    current_artifact_content = get_artifact_content(artifact) if artifact else None
    
    if not current_artifact_content:
        raise ValueError("No artifact found")
    
    if not is_artifact_code_content(current_artifact_content):
        raise ValueError("Current artifact content is not code")
    
    highlighted_code = state.get("highlightedCode")
    if not highlighted_code:
        raise ValueError("Cannot partially regenerate an artifact without a highlight")
    
    # Extract highlighted section with context
    code = current_artifact_content.get("code", "")
    start_char_index = highlighted_code.get("startCharIndex", 0)
    end_char_index = highlighted_code.get("endCharIndex", len(code))
    
    start = max(0, start_char_index - 500)
    end = min(len(code), end_char_index + 500)
    
    before_highlight = code[start:start_char_index]
    highlighted_text = code[start_char_index:end_char_index]
    after_highlight = code[end_char_index:end]
    
    # Build prompt
    formatted_prompt = UPDATE_HIGHLIGHTED_ARTIFACT_PROMPT.format(
        highlightedText=highlighted_text,
        beforeHighlight=before_highlight,
        afterHighlight=after_highlight,
        reflections=reflections
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
    content = ""
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
            content += chunk_content
        else:
            content += str(chunk)
    
    # Build updated artifact
    entire_text_before = code[:start_char_index]
    entire_text_after = code[end_char_index:]
    entire_updated_content = entire_text_before + content + entire_text_after
    
    # Create new artifact content
    contents = artifact.get("contents", [])
    new_index = len(contents) + 1
    
    new_artifact_content = {
        **current_artifact_content,
        "index": new_index,
        "code": entire_updated_content,
    }
    
    new_artifact = {
        **artifact,
        "currentIndex": new_index,
        "contents": contents + [new_artifact_content],
    }
    
    return {
        "artifact": new_artifact,
    }


async def update_highlighted_text_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Update highlighted text in markdown artifact."""
    from langchain_core.messages import HumanMessage
    from open_canvas.prompts import UPDATE_HIGHLIGHTED_TEXT_PROMPT
    
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
    from langchain_core.messages import HumanMessage, AIMessage
    from open_canvas.prompts import (
        UPDATE_ENTIRE_ARTIFACT_PROMPT, OPTIONALLY_UPDATE_META_PROMPT,
        GET_TITLE_TYPE_REWRITE_ARTIFACT
    )
    import uuid
    
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
    if is_artifact_markdown_content(current_artifact_content):
        artifact_content = current_artifact_content.get("fullMarkdown", "")
    else:
        artifact_content = current_artifact_content.get("code", "")
    
    # Optionally update artifact meta (simplified - skip tool calling for now)
    # In full implementation, this would use tool calling to determine type/title
    artifact_type = current_artifact_content.get("type", "text")
    artifact_title = current_artifact_content.get("title", "Untitled")
    
    # Build meta prompt (simplified)
    meta_prompt = ""
    if artifact_type == "code":
        meta_prompt = OPTIONALLY_UPDATE_META_PROMPT.format(
            artifactType=artifact_type,
            artifactTitle=""
        )
    elif artifact_title:
        meta_prompt = OPTIONALLY_UPDATE_META_PROMPT.format(
            artifactType=artifact_type,
            artifactTitle=f"And its title is (do NOT include this in your response):\n{artifact_title}"
        )
    
    # Build prompt
    formatted_prompt = UPDATE_ENTIRE_ARTIFACT_PROMPT.format(
        artifactContent=artifact_content,
        reflections=reflections,
        updateMetaPrompt=meta_prompt
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
    contents = artifact.get("contents", [])
    new_index = len(contents) + 1
    
    if artifact_type == "code":
        new_artifact_content = {
            "index": new_index,
            "type": "code",
            "title": artifact_title,
            "language": current_artifact_content.get("language", "other"),
            "code": artifact_content_text,
        }
    else:
        new_artifact_content = {
            "index": new_index,
            "type": "text",
            "title": artifact_title,
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


async def reply_to_general_input_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Reply to general input without generating/updating artifact."""
    from langchain_core.messages import HumanMessage
    from open_canvas.prompts import CURRENT_ARTIFACT_PROMPT, NO_ARTIFACT_PROMPT
    
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
    
    prompt = f"""You are an AI assistant tasked with responding to the users question.
  
The user has generated artifacts in the past. Use the following artifacts as context when responding to the users question.

You also have the following reflections on style guidelines and general memories/facts about the user to use when generating your response.
<reflections>
{reflections}
</reflections>

{current_artifact_prompt}"""
    
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


async def custom_action_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Handle custom quick action."""
    from langchain_core.messages import HumanMessage
    
    custom_quick_action_id = state.get("customQuickActionId")
    if not custom_quick_action_id:
        raise ValueError("No custom quick action ID found.")
    
    model = get_bedrock_model(config)
    
    # Get store and custom actions (simplified - would need store implementation)
    configurable = config.get("configurable", {}) if config else {}
    # For now, assume custom actions are passed in config
    custom_actions = configurable.get("customActions", {})
    
    if not custom_actions:
        raise ValueError("No custom actions found.")
    
    custom_quick_action = custom_actions.get(custom_quick_action_id)
    if not custom_quick_action:
        raise ValueError(f"No custom quick action found from ID {custom_quick_action_id}")
    
    # Get reflections if needed
    reflections = ""
    if custom_quick_action.get("includeReflections"):
        reflections = get_formatted_reflections(config)
        reflections_prompt = f"""You also have the following reflections on style guidelines and general memories/facts about the user:
<reflections>
{reflections}
</reflections>"""
    else:
        reflections_prompt = ""
    
    # Build prompt
    formatted_prompt = f"<custom-instructions>\n{custom_quick_action.get('prompt', '')}\n</custom-instructions>"
    
    if reflections_prompt:
        formatted_prompt += f"\n\n{reflections_prompt}"
    
    if custom_quick_action.get("includePrefix"):
        formatted_prompt = f"""You are an AI assistant. The user has provided custom instructions for you to follow.
{formatted_prompt}"""
    
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
        if is_artifact_markdown_content(current_artifact_content):
            artifact_content = current_artifact_content.get("fullMarkdown", "")
        else:
            artifact_content = current_artifact_content.get("code", "")
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
    
    if is_artifact_markdown_content(current_artifact_content):
        new_artifact_content = {
            **current_artifact_content,
            "index": new_index,
            "fullMarkdown": new_content,
        }
    else:
        new_artifact_content = {
            **current_artifact_content,
            "index": new_index,
            "code": new_content,
        }
    
    return {
        "artifact": {
            **artifact,
            "currentIndex": new_index,
            "contents": contents + [new_artifact_content],
        },
    }


async def rewrite_artifact_theme_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Rewrite artifact theme (language, length, reading level, emojis)."""
    from langchain_core.messages import AIMessage
    from open_canvas.prompts import (
        CHANGE_ARTIFACT_LANGUAGE_PROMPT, CHANGE_ARTIFACT_READING_LEVEL_PROMPT,
        CHANGE_ARTIFACT_TO_PIRATE_PROMPT, CHANGE_ARTIFACT_LENGTH_PROMPT,
        ADD_EMOJIS_TO_ARTIFACT_PROMPT
    )
    import uuid
    
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


async def rewrite_code_artifact_theme_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Rewrite code artifact theme (comments, logs, port language, fix bugs)."""
    from langchain_core.messages import AIMessage
    from open_canvas.prompts import (
        ADD_COMMENTS_TO_CODE_ARTIFACT_PROMPT, ADD_LOGS_TO_CODE_ARTIFACT_PROMPT,
        PORT_LANGUAGE_CODE_ARTIFACT_PROMPT, FIX_BUGS_CODE_ARTIFACT_PROMPT
    )
    import uuid
    
    model = get_bedrock_model(config)
    model_config = get_model_config(config)
    model_name = model_config.get("modelName", "")
    
    # Get current artifact content
    artifact = state.get("artifact")
    current_artifact_content = get_artifact_content(artifact) if artifact else None
    
    if not current_artifact_content:
        raise ValueError("No artifact found")
    
    if not is_artifact_code_content(current_artifact_content):
        raise ValueError("Current artifact content is not code")
    
    artifact_content = current_artifact_content.get("code", "")
    
    # Determine which prompt to use
    if state.get("addComments"):
        formatted_prompt = ADD_COMMENTS_TO_CODE_ARTIFACT_PROMPT.format(
            artifactContent=artifact_content
        )
    elif state.get("portLanguage"):
        language_map = {
            "typescript": "TypeScript",
            "javascript": "JavaScript",
            "cpp": "C++",
            "java": "Java",
            "php": "PHP",
            "python": "Python",
            "html": "HTML",
            "sql": "SQL",
        }
        new_language = language_map.get(state.get("portLanguage"), state.get("portLanguage"))
        formatted_prompt = PORT_LANGUAGE_CODE_ARTIFACT_PROMPT.format(
            newLanguage=new_language,
            artifactContent=artifact_content
        )
    elif state.get("addLogs"):
        formatted_prompt = ADD_LOGS_TO_CODE_ARTIFACT_PROMPT.format(
            artifactContent=artifact_content
        )
    elif state.get("fixBugs"):
        formatted_prompt = FIX_BUGS_CODE_ARTIFACT_PROMPT.format(
            artifactContent=artifact_content
        )
    else:
        raise ValueError("No theme selected")
    
    # Stream model for real-time updates
    artifact_content_text = ""
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
    contents = artifact.get("contents", [])
    new_index = len(contents) + 1
    
    new_artifact_content = {
        "index": new_index,
        "type": "code",
        "title": current_artifact_content.get("title", "Untitled"),
        "language": state.get("portLanguage") or current_artifact_content.get("language", "other"),
        "code": artifact_content_text,
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


# Build graph
builder = StateGraph(OpenCanvasState)
builder.add_node("generatePath", generate_path_node)
builder.add_edge(START, "generatePath")
builder.add_node("replyToGeneralInput", reply_to_general_input_node)
builder.add_node("rewriteArtifact", rewrite_artifact_node)
builder.add_node("rewriteArtifactTheme", rewrite_artifact_theme_node)
builder.add_node("rewriteCodeArtifactTheme", rewrite_code_artifact_theme_node)
builder.add_node("updateArtifact", update_artifact_node)
builder.add_node("updateHighlightedText", update_highlighted_text_node)
builder.add_node("generateArtifact", generate_artifact_node)
builder.add_node("customAction", custom_action_node)
builder.add_node("generateFollowup", generate_followup_node)
builder.add_node("cleanState", clean_state_node)
builder.add_node("reflect", reflect_node)
builder.add_node("generateTitle", generate_title_node)
builder.add_node("summarizer", summarizer_node)
builder.add_node("webSearch", web_search_node)
builder.add_node("routePostWebSearch", route_post_web_search)

# Add conditional edges
builder.add_conditional_edges(
    "generatePath",
    route_node,
    {
        "updateArtifact": "updateArtifact",
        "rewriteArtifactTheme": "rewriteArtifactTheme",
        "rewriteCodeArtifactTheme": "rewriteCodeArtifactTheme",
        "replyToGeneralInput": "replyToGeneralInput",
        "generateArtifact": "generateArtifact",
        "rewriteArtifact": "rewriteArtifact",
        "customAction": "customAction",
        "updateHighlightedText": "updateHighlightedText",
        "webSearch": "webSearch",
    }
)

# Add edges
builder.add_edge("generateArtifact", "generateFollowup")
builder.add_edge("updateArtifact", "generateFollowup")
builder.add_edge("updateHighlightedText", "generateFollowup")
builder.add_edge("rewriteArtifact", "generateFollowup")
builder.add_edge("rewriteArtifactTheme", "generateFollowup")
builder.add_edge("rewriteCodeArtifactTheme", "generateFollowup")
builder.add_edge("customAction", "generateFollowup")
builder.add_edge("webSearch", "routePostWebSearch")
builder.add_conditional_edges(
    "routePostWebSearch",
    lambda s: s.get("next", "generateArtifact"),
    {
        "generateArtifact": "generateArtifact",
        "rewriteArtifact": "rewriteArtifact",
    }
)
builder.add_edge("replyToGeneralInput", "cleanState")
builder.add_edge("generateFollowup", "reflect")
builder.add_edge("reflect", "cleanState")
builder.add_conditional_edges(
    "cleanState",
    conditionally_generate_title,
    {
        END: END,
        "generateTitle": "generateTitle",
        "summarizer": "summarizer",
    }
)
builder.add_edge("generateTitle", END)
builder.add_edge("summarizer", END)

graph = builder.compile()
graph.name = "open_canvas"

