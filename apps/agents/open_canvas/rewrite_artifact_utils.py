"""
Utility functions for rewrite-artifact node.
"""
from typing import Dict, Any, Optional
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from open_canvas.state import OpenCanvasState
from bedrock_client import get_bedrock_model
from utils import (
    get_artifact_content, is_artifact_code_content, is_artifact_markdown_content,
    format_artifact_content, get_formatted_reflections, get_string_from_content
)
from open_canvas.prompts import (
    GET_TITLE_TYPE_REWRITE_ARTIFACT, OPTIONALLY_UPDATE_META_PROMPT,
    UPDATE_ENTIRE_ARTIFACT_PROMPT
)
from langchain_core.messages import SystemMessage
import json
import re


# Programming languages list (from shared constants)
PROGRAMMING_LANGUAGES = [
    "typescript", "javascript", "python", "java", "cpp", "c", "csharp",
    "php", "ruby", "go", "rust", "swift", "kotlin", "scala", "r",
    "sql", "html", "css", "scss", "less", "json", "xml", "yaml",
    "markdown", "shell", "bash", "powershell", "other"
]


async def optionally_update_artifact_meta(
    state: OpenCanvasState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Optionally update artifact meta (type, title, language) using LLM.
    
    Returns a dict with:
    - type: "text" or "code"
    - title: Optional string
    - language: Programming language (if type is "code")
    """
    from utils import get_formatted_reflections
    
    model = get_bedrock_model(config)
    reflections = get_formatted_reflections(config)
    
    artifact = state.get("artifact")
    current_artifact_content = get_artifact_content(artifact) if artifact else None
    
    if not current_artifact_content:
        raise ValueError("No artifact found")
    
    # Format artifact for prompt (first 500 chars)
    artifact_str = format_artifact_content(current_artifact_content, shorten_content=True)
    
    # Build prompt
    prompt = GET_TITLE_TYPE_REWRITE_ARTIFACT.format(
        artifact=artifact_str
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
    
    # Use structured output prompt
    structured_prompt = f"""{prompt}

You must respond with a JSON object in the following format:
{{
  "type": "text" or "code",
  "title": "optional title string (only if subject/topic changed)",
  "language": "programming language if type is code, otherwise 'other'"
}}

Available programming languages: {', '.join(PROGRAMMING_LANGUAGES)}

Respond with ONLY the JSON object, no other text."""
    
    try:
        response = await model.ainvoke([
            SystemMessage(content="You are a helpful AI assistant that responds with JSON."),
            HumanMessage(content=structured_prompt),
            recent_human_message,
        ])
        
        response_text = get_string_from_content(response.content)
        
        # Extract JSON from response
        json_match = re.search(r'\{[^}]+\}', response_text, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
                
                # Validate and set defaults
                artifact_type = parsed.get("type", current_artifact_content.get("type", "text"))
                if artifact_type not in ["text", "code"]:
                    artifact_type = current_artifact_content.get("type", "text")
                
                artifact_title = parsed.get("title")
                if not artifact_title:
                    # Keep current title if not specified
                    artifact_title = current_artifact_content.get("title", "Untitled")
                
                language = parsed.get("language", "other")
                if language not in PROGRAMMING_LANGUAGES:
                    if is_artifact_code_content(current_artifact_content):
                        language = current_artifact_content.get("language", "other")
                    else:
                        language = "other"
                
                return {
                    "type": artifact_type,
                    "title": artifact_title,
                    "language": language
                }
            except json.JSONDecodeError:
                pass
        
        # Fallback: use current artifact meta
        return {
            "type": current_artifact_content.get("type", "text"),
            "title": current_artifact_content.get("title", "Untitled"),
            "language": (
                current_artifact_content.get("language", "other")
                if is_artifact_code_content(current_artifact_content)
                else "other"
            )
        }
        
    except Exception as e:
        print(f"Error in artifact meta update: {e}", flush=True)
        # Fallback to current values
        return {
            "type": current_artifact_content.get("type", "text"),
            "title": current_artifact_content.get("title", "Untitled"),
            "language": (
                current_artifact_content.get("language", "other")
                if is_artifact_code_content(current_artifact_content)
                else "other"
            )
        }


def build_meta_prompt(artifact_meta: Dict[str, Any]) -> str:
    """Build meta prompt from artifact meta dict."""
    artifact_type = artifact_meta.get("type", "text")
    artifact_title = artifact_meta.get("title", "")
    
    title_section = ""
    if artifact_title and artifact_type != "code":
        title_section = f"And its title is (do NOT include this in your response):\n{artifact_title}"
    
    return OPTIONALLY_UPDATE_META_PROMPT.format(
        artifactType=artifact_type,
        artifactTitle=title_section
    )


def build_rewrite_prompt(
    artifact_content: str,
    reflections: str,
    meta_prompt: str
) -> str:
    """Build the full rewrite prompt."""
    return UPDATE_ENTIRE_ARTIFACT_PROMPT.format(
        artifactContent=artifact_content,
        reflections=reflections,
        updateMetaPrompt=meta_prompt
    )


def create_new_artifact_content(
    artifact_type: str,
    state: OpenCanvasState,
    current_artifact_content: Dict[str, Any],
    artifact_meta: Dict[str, Any],
    new_content: str
) -> Dict[str, Any]:
    """Create new artifact content from meta and new content."""
    artifact = state.get("artifact")
    contents = artifact.get("contents", []) if artifact else []
    new_index = len(contents) + 1
    
    base_content = {
        "index": new_index,
        "title": artifact_meta.get("title") or current_artifact_content.get("title", "Untitled"),
    }
    
    if artifact_type == "code":
        language = artifact_meta.get("language", "other")
        if language not in PROGRAMMING_LANGUAGES:
            language = current_artifact_content.get("language", "other") if is_artifact_code_content(current_artifact_content) else "other"
        
        return {
            **base_content,
            "type": "code",
            "language": language,
            "code": new_content,
        }
    else:
        return {
            **base_content,
            "type": "text",
            "fullMarkdown": new_content,
        }

