"""
Post-processing nodes for Open Canvas graph.
"""
from typing import Dict, Any, Literal
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from agents.open_canvas.state import OpenCanvasState
from core.bedrock_client import get_bedrock_model
from core.utils import (
    format_messages, get_artifact_content, get_formatted_reflections,
    estimate_input_size, truncate_content
)
from agents.open_canvas.prompts import FOLLOWUP_ARTIFACT_PROMPT
from agents.reflection.graph import graph as reflection_graph
from agents.summarizer.graph import graph as summarizer_graph
from agents.thread_title.graph import graph as thread_title_graph

# Character limit for summarization (~ 4 chars per token, max tokens of 75000)
CHARACTER_MAX = 300000


async def generate_followup_node(
    state: OpenCanvasState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Generate followup message after artifact generation."""
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
            from langgraph.graph import END
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
    from langgraph.graph import END
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
