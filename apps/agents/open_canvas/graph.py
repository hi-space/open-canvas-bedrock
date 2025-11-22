"""
Open Canvas main graph implementation.
"""
from typing import Dict, Any, Literal
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from open_canvas.state import OpenCanvasState
from bedrock_client import get_bedrock_model
from utils import format_messages, format_reflections
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
    # Simplified routing logic
    if state.get("highlightedCode"):
        return {"next": "updateArtifact"}
    if state.get("highlightedText"):
        return {"next": "updateHighlightedText"}
    if state.get("language") or state.get("artifactLength") or state.get("regenerateWithEmojis") or state.get("readingLevel"):
        return {"next": "rewriteArtifactTheme"}
    if state.get("addComments") or state.get("addLogs") or state.get("portLanguage") or state.get("fixBugs"):
        return {"next": "rewriteCodeArtifactTheme"}
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
    model = get_bedrock_model(config)
    
    artifact = state.get("artifact")
    artifact_content = ""
    if artifact and isinstance(artifact, dict):
        if "contents" in artifact and artifact["contents"]:
            content = artifact["contents"][0]
            if isinstance(content, dict):
                artifact_content = content.get("fullMarkdown", content.get("code", ""))
    
    prompt = f"""You are an AI assistant tasked with generating a followup to the artifact the user just generated.
The context is you're having a conversation with the user, and you've just generated an artifact for them. Now you should follow up with a message that notifies them you're done. Make this message creative!

Here is the artifact you generated:
{artifact_content}

This message should be very short. Never generate more than 2-3 short sentences. Your tone should be somewhat formal, but still friendly. Remember, you're an AI assistant.

Do NOT include any tags, or extra text before or after your response."""
    
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
    """Generate title for conversation."""
    title_state = {
        "messages": state.get("messages", []),
        "artifact": state.get("artifact"),
    }
    # Map thread_id to open_canvas_thread_id for thread_title graph
    configurable = config.get("configurable", {}) if config else {}
    thread_id = configurable.get("thread_id")
    title_config = {
        "configurable": {
            **configurable,
            "open_canvas_thread_id": thread_id,
        }
    }
    result = await thread_title_graph.ainvoke(title_state, config=title_config)
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


# Placeholder nodes (simplified implementations)
async def update_artifact_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Update artifact."""
    return {}


async def update_highlighted_text_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Update highlighted text."""
    return {}


async def rewrite_artifact_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Rewrite artifact."""
    return {}


async def rewrite_artifact_theme_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Rewrite artifact theme."""
    return {}


async def rewrite_code_artifact_theme_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Rewrite code artifact theme."""
    return {}


async def reply_to_general_input_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Reply to general input."""
    return {}


async def custom_action_node(state: OpenCanvasState, config: RunnableConfig) -> Dict[str, Any]:
    """Handle custom action."""
    return {}


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

