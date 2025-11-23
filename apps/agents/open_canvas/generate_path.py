"""
Generate path node implementation with URL handling, document processing, and dynamic routing.
"""
from typing import Dict, Any, List, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from open_canvas.state import OpenCanvasState
from bedrock_client import get_bedrock_model
from utils import (
    format_messages, get_artifact_content, format_artifact_content_with_template,
    extract_urls, create_context_document_messages, get_string_from_content,
    convert_pdf_to_text, clean_base64, format_artifact_content
)
from open_canvas.prompts import (
    ROUTE_QUERY_PROMPT, ROUTE_QUERY_OPTIONS_HAS_ARTIFACTS,
    ROUTE_QUERY_OPTIONS_NO_ARTIFACTS, CURRENT_ARTIFACT_PROMPT, NO_ARTIFACT_PROMPT
)
import uuid
import base64
import os


class RouteQuerySchema(BaseModel):
    """Schema for route query tool calling."""
    route: str = Field(description="The route to take based on the user's query.")


async def include_url_contents(
    message: HumanMessage,
    urls: List[str],
    config: RunnableConfig
) -> Optional[HumanMessage]:
    """Include URL contents in message if user explicitly requested it.
    
    Uses LLM to determine if user wants URL contents included, then scrapes
    using FireCrawl if available.
    """
    try:
        # Check if FireCrawl API key is available
        firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
        if not firecrawl_api_key:
            # If no FireCrawl, skip URL inclusion
            return None
        
        # Use LLM to determine if user wants URL contents
        model = get_bedrock_model(config)
        
        prompt = f"""You're an advanced AI assistant.
You have been tasked with analyzing the user's message and determining if the user wants the contents of the URL included in their message included in their prompt.
You should ONLY answer 'true' if it is explicitly clear the user included the URL in their message so that its contents would be included in the prompt, otherwise, answer 'false'

Here is the user's message:
<message>
{get_string_from_content(message.content)}
</message>

Now, given their message, determine whether or not they want the contents of that webpage to be included in the prompt.

Respond with only 'true' or 'false'."""
        
        response = await model.ainvoke([
            SystemMessage(content="You are a helpful AI assistant."),
            HumanMessage(content=prompt),
        ])
        
        response_text = get_string_from_content(response.content)
        should_include = "true" in response_text.lower()
        
        if not should_include:
            return None
        
        # Scrape URLs using FireCrawl
        try:
            from langchain_community.document_loaders import FireCrawlLoader
            
            url_contents = []
            for url in urls:
                try:
                    loader = FireCrawlLoader(
                        url=url,
                        mode="scrape",
                        api_key=firecrawl_api_key,
                        params={"formats": ["markdown"]}
                    )
                    docs = loader.load()
                    if docs:
                        url_contents.append({
                            "url": url,
                            "pageContent": docs[0].page_content if docs else ""
                        })
                except Exception as e:
                    print(f"Failed to scrape URL {url}: {e}", flush=True)
                    continue
            
            if not url_contents:
                return None
            
            # Transform message to include URL contents
            original_content = get_string_from_content(message.content)
            transformed_content = original_content
            
            for url_content in url_contents:
                url = url_content["url"]
                page_content = url_content["pageContent"]
                transformed_content = transformed_content.replace(
                    url,
                    f'<page-contents url="{url}">\n{page_content}\n</page-contents>'
                )
            
            return HumanMessage(
                content=transformed_content,
                id=message.id if hasattr(message, 'id') else None,
                additional_kwargs=getattr(message, 'additional_kwargs', {})
            )
        except ImportError:
            print("FireCrawlLoader not available, skipping URL scraping", flush=True)
            return None
        except Exception as e:
            print(f"Error scraping URLs: {e}", flush=True)
            return None
            
    except Exception as e:
        print(f"Failed to handle included URLs: {e}", flush=True)
        return None


async def convert_context_document_to_human_message(
    messages: List[BaseMessage],
    config: RunnableConfig
) -> Optional[HumanMessage]:
    """Convert context documents in last message to HumanMessage."""
    if not messages:
        return None
    
    last_message = messages[-1]
    if not isinstance(last_message, HumanMessage):
        return None
    
    # Check for documents in additional_kwargs
    additional_kwargs = getattr(last_message, 'additional_kwargs', {})
    documents = additional_kwargs.get("documents", [])
    
    if not documents:
        return None
    
    # Create context document messages
    context_messages = create_context_document_messages(config, documents)
    
    if not context_messages:
        return None
    
    # Convert to HumanMessage format
    content_parts = []
    for msg in context_messages:
        if isinstance(msg, dict) and "content" in msg:
            content_parts.extend(msg["content"])
    
    if not content_parts:
        return None
    
    return HumanMessage(
        id=str(uuid.uuid4()),
        content=content_parts,
        additional_kwargs={"OC_HIDE_FROM_UI": True}
    )


async def fix_misformatted_context_doc_message(
    message: HumanMessage,
    config: RunnableConfig
) -> Optional[List[BaseMessage]]:
    """Fix misformatted context document messages for different model providers."""
    from langchain_core.messages import RemoveMessage
    
    if isinstance(message.content, str):
        return None
    
    # For Bedrock, we'll convert all documents to text format
    if not isinstance(message.content, list):
        return None
    
    new_content = []
    changes_made = False
    
    for item in message.content:
        if isinstance(item, dict):
            # Handle different document formats
            if item.get("type") == "document" and "source" in item:
                # Anthropic format - convert to text
                source = item.get("source", {})
                if source.get("type") == "base64" and source.get("data"):
                    try:
                        text = convert_pdf_to_text(source["data"])
                        new_content.append({"type": "text", "text": text})
                        changes_made = True
                    except Exception as e:
                        print(f"Failed to convert PDF: {e}", flush=True)
                        new_content.append(item)
                else:
                    new_content.append(item)
            elif item.get("type") == "application/pdf":
                # Gemini format - convert to text
                try:
                    text = convert_pdf_to_text(item.get("data", ""))
                    new_content.append({"type": "text", "text": text})
                    changes_made = True
                except Exception as e:
                    print(f"Failed to convert PDF: {e}", flush=True)
                    new_content.append(item)
            else:
                new_content.append(item)
        else:
            new_content.append(item)
    
    if not changes_made:
        return None
    
    # Return RemoveMessage and new HumanMessage
    return [
        RemoveMessage(id=message.id or ""),
        HumanMessage(
            id=str(uuid.uuid4()),
            content=new_content,
            additional_kwargs=getattr(message, 'additional_kwargs', {})
        )
    ]


async def dynamic_determine_path(
    state: OpenCanvasState,
    new_messages: List[BaseMessage],
    config: RunnableConfig
) -> Optional[Dict[str, str]]:
    """Dynamically determine path using LLM tool calling."""
    from utils import get_formatted_reflections, format_artifact_content
    
    current_artifact_content = None
    if state.get("artifact"):
        current_artifact_content = get_artifact_content(state.get("artifact"))
    
    # Build prompt
    artifact_options = (
        ROUTE_QUERY_OPTIONS_HAS_ARTIFACTS
        if current_artifact_content
        else ROUTE_QUERY_OPTIONS_NO_ARTIFACTS
    )
    
    artifact_route = "rewriteArtifact" if current_artifact_content else "generateArtifact"
    
    recent_messages = state.get("_messages", state.get("messages", []))[-3:]
    recent_messages_str = "\n\n".join([
        f"{msg.__class__.__name__}: {get_string_from_content(msg.content)}"
        for msg in recent_messages
    ])
    
    current_artifact_prompt = (
        format_artifact_content_with_template(
            CURRENT_ARTIFACT_PROMPT,
            current_artifact_content
        )
        if current_artifact_content
        else NO_ARTIFACT_PROMPT
    )
    
    formatted_prompt = ROUTE_QUERY_PROMPT.format(
        app_context="",  # APP_CONTEXT is already in the prompt
        artifact_options=artifact_options,
        recent_messages=recent_messages_str,
        current_artifact_prompt=current_artifact_prompt
    )
    
    # Get model with tool calling support
    model = get_bedrock_model(config)
    
    # For Bedrock, we'll use structured output if available
    # Otherwise, use a simple prompt and parse response
    try:
        # Try structured output (if supported by model)
        from langchain_core.output_parsers import PydanticOutputParser
        
        parser = PydanticOutputParser(pydantic_object=RouteQuerySchema)
        format_instructions = parser.get_format_instructions()
        
        full_prompt = f"{formatted_prompt}\n\n{format_instructions}"
        
        response = await model.ainvoke([
            SystemMessage(content="You are a routing assistant."),
            HumanMessage(content=full_prompt),
        ])
        
        response_text = get_string_from_content(response.content)
        
        # Try to parse JSON from response
        import json
        import re
        
        # Look for JSON in response
        json_match = re.search(r'\{[^}]+\}', response_text, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
                route = parsed.get("route", artifact_route)
                # Validate route
                if current_artifact_content:
                    valid_routes = ["rewriteArtifact", "replyToGeneralInput"]
                else:
                    valid_routes = ["generateArtifact", "replyToGeneralInput"]
                
                if route not in valid_routes:
                    route = artifact_route
                
                return {"route": route}
            except json.JSONDecodeError:
                pass
        
        # Fallback: look for route name in response
        if "replyToGeneralInput" in response_text:
            return {"route": "replyToGeneralInput"}
        else:
            return {"route": artifact_route}
            
    except Exception as e:
        print(f"Error in dynamic path determination: {e}", flush=True)
        # Fallback to default route
        return {"route": artifact_route}


async def generate_path(
    state: OpenCanvasState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Generate path/routing node with URL handling, document processing, and dynamic routing."""
    _messages = state.get("_messages", state.get("messages", []))
    new_messages: List[BaseMessage] = []
    
    # Handle context documents
    doc_message = await convert_context_document_to_human_message(_messages, config)
    if doc_message:
        new_messages.append(doc_message)
    else:
        # Check for existing document message and fix formatting if needed
        for msg in _messages:
            if isinstance(msg, HumanMessage) and not isinstance(msg.content, str):
                fixed = await fix_misformatted_context_doc_message(msg, config)
                if fixed:
                    # Remove old message and add fixed ones
                    # Note: In practice, we'd need to handle this in the state update
                    break
    
    # Check for explicit routing conditions first
    if state.get("highlightedCode"):
        result = {"next": "updateArtifact"}
        if new_messages:
            result["messages"] = new_messages
            result["_messages"] = new_messages
        return result
    
    if state.get("highlightedText"):
        result = {"next": "updateHighlightedText"}
        if new_messages:
            result["messages"] = new_messages
            result["_messages"] = new_messages
        return result
    
    if (state.get("language") or state.get("artifactLength") or 
        state.get("regenerateWithEmojis") or state.get("readingLevel")):
        result = {"next": "rewriteArtifactTheme"}
        if new_messages:
            result["messages"] = new_messages
            result["_messages"] = new_messages
        return result
    
    if (state.get("addComments") or state.get("addLogs") or 
        state.get("portLanguage") or state.get("fixBugs")):
        result = {"next": "rewriteCodeArtifactTheme"}
        if new_messages:
            result["messages"] = new_messages
            result["_messages"] = new_messages
        return result
    
    if state.get("customQuickActionId"):
        result = {"next": "customAction"}
        if new_messages:
            result["messages"] = new_messages
            result["_messages"] = new_messages
        return result
    
    if state.get("webSearchEnabled"):
        result = {"next": "webSearch"}
        if new_messages:
            result["messages"] = new_messages
            result["_messages"] = new_messages
        return result
    
    # Check for URLs in last message and include contents if needed
    message_urls = []
    updated_message_with_contents = None
    
    if _messages:
        last_message = _messages[-1]
        if isinstance(last_message, HumanMessage):
            message_content = get_string_from_content(last_message.content)
            message_urls = extract_urls(message_content)
            
            if message_urls:
                updated_message_with_contents = await include_url_contents(
                    last_message,
                    message_urls,
                    config
                )
    
    # Update internal message list if URL contents were added
    new_internal_message_list = _messages
    if updated_message_with_contents and _messages:
        new_internal_message_list = [
            updated_message_with_contents if msg.id == updated_message_with_contents.id else msg
            for msg in _messages
        ]
    
    # Dynamic path determination
    routing_result = await dynamic_determine_path(
        {
            **state,
            "_messages": new_internal_message_list
        },
        new_messages,
        config
    )
    
    route = routing_result.get("route") if routing_result else None
    if not route:
        # Fallback to default
        route = "rewriteArtifact" if state.get("artifact") else "generateArtifact"
    
    # Build result
    result = {"next": route}
    
    if new_messages:
        result["messages"] = new_messages
        result["_messages"] = new_internal_message_list + new_messages
    elif updated_message_with_contents:
        result["_messages"] = new_internal_message_list
    
    return result

