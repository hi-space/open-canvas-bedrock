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
    get_artifact_content, is_artifact_markdown_content,
    get_formatted_reflections, format_artifact_content_with_template,
    is_thinking_model, extract_thinking_and_response_tokens, create_context_document_messages,
    get_string_from_content
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
    """Generate path/routing node with URL handling, document processing, and dynamic routing."""
    from open_canvas.generate_path import generate_path
    return await generate_path(state, config)


async def route_node(state: OpenCanvasState) -> str:
    """Route to next node based on state."""
    next_node = state.get("next")
    if not next_node:
        raise ValueError("'next' state field not set.")
    return next_node


def route_after_followup(state: OpenCanvasState, config: RunnableConfig) -> Literal["reflect", "cleanState"]:
    """Route after generateFollowup: skip reflection if no assistant_id."""
    configurable = config.get("configurable", {}) if config else {}
    assistant_id = configurable.get("open_canvas_assistant_id")
    
    # Skip reflection if no assistant_id (no assistants mode)
    if not assistant_id:
        return "cleanState"
    return "reflect"


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
    from utils import estimate_input_size
    
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


async def generate_followup_node(
    state: OpenCanvasState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Generate followup message after artifact generation."""
    from open_canvas.prompts import FOLLOWUP_ARTIFACT_PROMPT
    from utils import estimate_input_size, truncate_content
    
    model = get_bedrock_model(config)
    
    # Get artifact content
    artifact = state.get("artifact")
    artifact_content = ""
    if artifact:
        current_content = get_artifact_content(artifact)
        if current_content:
            artifact_content = current_content.get("fullMarkdown", "")
    
    # Get reflections
    reflections = get_formatted_reflections(config)
    
    # Get conversation history
    messages = state.get("messages", [])
    
    # Estimate maximum safe input size
    # Bedrock models typically have context windows, but we'll be conservative
    # Rough estimate: ~200K characters should be safe for most models
    MAX_SAFE_INPUT_SIZE = 200 * 1024  # 200KB of text
    
    # Calculate current sizes
    artifact_size = estimate_input_size(artifact_content)
    reflections_size = estimate_input_size(reflections)
    
    # Calculate available size for conversation
    # Reserve space for prompt template, system message, and safety margin
    reserved_size = 5000  # For prompt template and system message
    available_for_conversation = MAX_SAFE_INPUT_SIZE - artifact_size - reflections_size - reserved_size
    
    # Format conversation with size limit
    if available_for_conversation > 0:
        conversation = format_messages(messages, max_length=available_for_conversation)
    else:
        # If artifact/reflections are too large, truncate them
        print(f"Warning: Artifact ({artifact_size} chars) and reflections ({reflections_size} chars) "
              f"are very large. Truncating conversation history.", flush=True)
        conversation = "[Conversation history truncated due to large artifact/reflections]"
        # Truncate artifact if needed
        if artifact_size > MAX_SAFE_INPUT_SIZE * 0.6:  # If artifact is > 60% of max
            artifact_content = truncate_content(artifact_content, int(MAX_SAFE_INPUT_SIZE * 0.5))
            print(f"Truncated artifact content to {len(artifact_content)} characters", flush=True)
    
    # Build prompt
    prompt = FOLLOWUP_ARTIFACT_PROMPT.format(
        artifactContent=artifact_content,
        reflections=reflections,
        conversation=conversation
    )
    
    # Final safety check
    total_size = estimate_input_size(prompt)
    if total_size > MAX_SAFE_INPUT_SIZE * 1.2:  # 20% safety margin
        print(f"Warning: Total prompt size ({total_size} chars) exceeds safe limit. "
              f"Attempting to send anyway, but may fail.", flush=True)
    
    try:
        response = await model.ainvoke([
            SystemMessage(content="You are a helpful AI assistant."),
            HumanMessage(content=prompt),
        ])
    except Exception as e:
        error_msg = str(e)
        if "too long" in error_msg.lower() or "Input is too long" in error_msg:
            print(f"Error: Input too long ({total_size} chars). "
                  f"Artifact: {artifact_size}, Reflections: {reflections_size}, "
                  f"Conversation: {len(conversation)}", flush=True)
            # Return a fallback message
            from langchain_core.messages import AIMessage
            return {
                "messages": [AIMessage(
                    content="I apologize, but the input is too large for me to process. "
                           "Please try with a smaller artifact or shorter conversation history."
                )]
            }
        raise
    
    return {
        "messages": [response]
    }


async def reflect_node(
    state: OpenCanvasState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Reflect on conversation and artifact."""
    # Check if assistant_id is available
    configurable = config.get("configurable", {}) if config else {}
    assistant_id = configurable.get("open_canvas_assistant_id")
    
    # Skip reflection if assistant_id is not available
    if not assistant_id:
        import sys
        print("Skipping reflection: Assistant ID is not available.", file=sys.stderr, flush=True)
        return {}
    
    # Use reflection graph with error handling
    try:
        reflection_state = {
            "messages": state.get("messages", []),
            "artifact": state.get("artifact"),
        }
        result = await reflection_graph.ainvoke(reflection_state, config)
        import sys
        print(f"Reflection completed successfully for assistant {assistant_id}", file=sys.stderr, flush=True)
    except Exception as e:
        import sys
        print(f"Error during reflection: {e}", file=sys.stderr, flush=True)
        # Continue without failing the entire graph
        pass
    
    return {}


async def clean_state_node(state: OpenCanvasState) -> Dict[str, Any]:
    """Clean state after processing and determine next route.
    
    This node cleans up state and determines the next routing decision
    to avoid unnecessary conditional edge function calls.
    """
    # Clean state
    cleaned_state = {
        "next": None,
        "highlightedText": None,
        "language": None,
        "artifactLength": None,
        "regenerateWithEmojis": None,
        "readingLevel": None,
        "customQuickActionId": None,
        "webSearchEnabled": None,
    }
    
    # Determine routing decision inline to avoid separate conditional function call
    messages = state.get("messages", [])
    artifact = state.get("artifact")
    
    # Count user messages (HumanMessage) to detect first conversation
    from langchain_core.messages import HumanMessage
    user_message_count = sum(1 for msg in messages if isinstance(msg, HumanMessage))
    
    # Determine next route based on same logic as conditionally_generate_title
    # but do it here to avoid extra function call
    if artifact and user_message_count == 1:
        # First user message with artifact - generate title
        cleaned_state["_next_route"] = "generateTitle"
    elif len(messages) <= 4:
        # First conversation - generate title
        cleaned_state["_next_route"] = "generateTitle"
    else:
        # Check if summarization is needed
        _messages = state.get("_messages", state.get("messages", []))
        total_chars = sum(
            len(msg.content) if isinstance(msg.content, str) else len(str(msg.content))
            for msg in _messages
        )
        if total_chars > CHARACTER_MAX:
            cleaned_state["_next_route"] = "summarizer"
        else:
            cleaned_state["_next_route"] = END
    
    return cleaned_state


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
    """Conditionally route to title generation.
    
    Generate title if:
    1. It's the first conversation (messages <= 4, accounting for user message + artifact message + followup message), OR
    2. An artifact exists and it's still early in the conversation (first user interaction)
    
    Otherwise, check if summarization is needed or go to END.
    """
    messages = state.get("messages", [])
    artifact = state.get("artifact")
    
    # Count user messages (HumanMessage) to detect first conversation
    # First conversation has exactly 1 user message
    from langchain_core.messages import HumanMessage
    user_message_count = sum(1 for msg in messages if isinstance(msg, HumanMessage))
    
    # If artifact exists and it's the first user message, always generate title
    # This ensures title is generated when artifact is first created
    if artifact and user_message_count == 1:
        return "generateTitle"
    
    # If it's the first conversation (messages <= 4 to account for artifact + followup), generate title
    # This covers cases without artifact too
    if len(messages) <= 4:
        return "generateTitle"
    
    # Otherwise, check if summarization is needed
    return simple_token_calculator(state)


async def generate_title_node(
    state: OpenCanvasState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Generate title for conversation.
    
    Based on origin implementation, this should:
    1. Try to generate title, but continue even if it fails
    2. Map thread_id to open_canvas_thread_id for thread_title graph
    
    Note: The routing decision is made in cleanState node, so we don't need
    to check message count here.
    """
    messages = state.get("messages", [])
    
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
        # Extract title from result and return it in output
        # StateGraph.ainvoke returns the final state, which should include the title
        title = result.get("title") if isinstance(result, dict) else None
        if title:
            return {"title": title}
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
    artifact_content = current_artifact_content.get("fullMarkdown", "")
    
    # Optionally update artifact meta using LLM
    from open_canvas.rewrite_artifact_utils import (
        build_meta_prompt,
        build_rewrite_prompt
    )
    
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
    from open_canvas.rewrite_artifact_utils import create_new_artifact_content
    
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
    from store.store import store
    
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




# Build graph
builder = StateGraph(OpenCanvasState)
builder.add_node("generatePath", generate_path_node)
builder.add_edge(START, "generatePath")
builder.add_node("replyToGeneralInput", reply_to_general_input_node)
builder.add_node("rewriteArtifact", rewrite_artifact_node)
builder.add_node("rewriteArtifactTheme", rewrite_artifact_theme_node)
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
        "rewriteArtifactTheme": "rewriteArtifactTheme",
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
builder.add_edge("updateHighlightedText", "generateFollowup")
builder.add_edge("rewriteArtifact", "generateFollowup")
builder.add_edge("rewriteArtifactTheme", "generateFollowup")
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
builder.add_edge("replyToGeneralInput", "generateFollowup")
builder.add_conditional_edges(
    "generateFollowup",
    route_after_followup,
    {
        "reflect": "reflect",
        "cleanState": "cleanState",
    }
)
builder.add_edge("reflect", "cleanState")
builder.add_conditional_edges(
    "cleanState",
    lambda state: state.get("_next_route", END),
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

