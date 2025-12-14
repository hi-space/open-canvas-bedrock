"""
FastAPI routes for Open Canvas agent.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, AsyncIterator
import json
from open_canvas.graph import graph
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

router = APIRouter()


class OpenCanvasRequest(BaseModel):
    """Request model for Open Canvas agent."""
    messages: List[Dict[str, Any]]
    artifact: Optional[Dict[str, Any]] = None
    language: Optional[str] = None
    artifactLength: Optional[str] = None
    regenerateWithEmojis: Optional[bool] = None
    readingLevel: Optional[str] = None
    highlightedText: Optional[Dict[str, Any]] = None
    portLanguage: Optional[str] = None
    customQuickActionId: Optional[str] = None
    webSearchEnabled: Optional[bool] = None
    webSearchResults: Optional[List[Dict[str, Any]]] = None
    next: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


def convert_messages_to_langchain(messages: List[Dict[str, Any]]) -> List[BaseMessage]:
    """Convert message dicts to LangChain message objects.
    
    Supports both OpenAI format (role: "user"/"assistant"/"system") 
    and LangChain format (type: "human"/"ai"/"system").
    """
    langchain_messages = []
    for msg_dict in messages:
        # Try OpenAI format first (role field)
        role = msg_dict.get("role", "").lower()
        # Fallback to LangChain format (type field)
        if not role:
            msg_type = msg_dict.get("type", "").lower()
            if msg_type == "human":
                role = "user"
            elif msg_type == "ai":
                role = "assistant"
            else:
                role = msg_type
        
        content = msg_dict.get("content", "")
        msg_id = msg_dict.get("id")
        additional_kwargs = msg_dict.get("additional_kwargs", {})
        
        if role == "user" or role == "human":
            msg = HumanMessage(
                content=content,
                id=msg_id,
                additional_kwargs=additional_kwargs
            )
        elif role == "assistant" or role == "ai":
            msg = AIMessage(
                content=content,
                id=msg_id,
                additional_kwargs=additional_kwargs
            )
        elif role == "system":
            msg = SystemMessage(
                content=content,
                id=msg_id,
                additional_kwargs=additional_kwargs
            )
        else:
            # Default to HumanMessage if type is unknown
            msg = HumanMessage(
                content=content,
                id=msg_id,
                additional_kwargs=additional_kwargs
            )
        langchain_messages.append(msg)
    return langchain_messages


def format_event_log(event_type: str, event_name: str, event: Dict[str, Any]) -> Optional[str]:
    """Format event log with type-specific information.
    Returns None if the event should not be logged (e.g., empty chunks)."""
    base_info = f"{event_type} {event_name}"

    if event_type == "on_chat_model_stream":
        # Skip logging for streaming events
        return None

    elif event_type == "on_chain_start":
        # Show input for chain start
        data = event.get("data", {})
        input_data = data.get("input")
        if input_data:
            input_str = str(input_data)
            if len(input_str) > 150:
                input_str = input_str[:150] + "..."
            return f"{base_info} | input: {input_str}"
    
    elif event_type == "on_chain_end":
        # Show output for chain end
        data = event.get("data", {})
        output = data.get("output")
        if output:
            output_str = str(output)
            if len(output_str) > 150:
                output_str = output_str[:150] + "..."
            return f"{base_info} | output: {output_str}"
    
    elif event_type == "on_tool_start":
        # Show tool input
        data = event.get("data", {})
        input_data = data.get("input")
        if input_data:
            input_str = str(input_data)
            if len(input_str) > 150:
                input_str = input_str[:150] + "..."
            return f"{base_info} | input: {input_str}"
    
    elif event_type == "on_tool_end":
        # Show tool output
        data = event.get("data", {})
        output = data.get("output")
        if output:
            output_str = str(output)
            if len(output_str) > 150:
                output_str = output_str[:150] + "..."
            return f"{base_info} | output: {output_str}"
    
    elif event_type == "on_llm_start":
        # Show prompts for LLM start
        data = event.get("data", {})
        prompts = data.get("prompts", [])
        if prompts:
            prompt_preview = str(prompts[0])[:100] if prompts else ""
            if len(prompt_preview) > 100:
                prompt_preview = prompt_preview[:100] + "..."
            return f"{base_info} | prompt: {prompt_preview}"
    
    elif event_type == "on_llm_end":
        # Show response for LLM end
        data = event.get("data", {})
        response = data.get("response")
        if response:
            response_str = str(response)
            if len(response_str) > 150:
                response_str = response_str[:150] + "..."
            return f"{base_info} | response: {response_str}"
    
    # Default: just return base info
    return base_info


def prepare_state(request: OpenCanvasRequest) -> Dict[str, Any]:
    """Prepare state from request."""
    import sys
    # Debug logging for rewrite-related fields
    print("=== prepare_state: Received rewrite fields ===", file=sys.stderr, flush=True)
    print(f"  language: {request.language}", file=sys.stderr, flush=True)
    print(f"  artifactLength: {request.artifactLength}", file=sys.stderr, flush=True)
    print(f"  regenerateWithEmojis: {request.regenerateWithEmojis}", file=sys.stderr, flush=True)
    print(f"  readingLevel: {request.readingLevel}", file=sys.stderr, flush=True)
    print(f"  highlightedText: {'present' if request.highlightedText else None}", file=sys.stderr, flush=True)
    print(f"  portLanguage: {request.portLanguage}", file=sys.stderr, flush=True)
    print(f"  customQuickActionId: {request.customQuickActionId}", file=sys.stderr, flush=True)
    print(f"  webSearchEnabled: {request.webSearchEnabled}", file=sys.stderr, flush=True)
    print("=============================================", file=sys.stderr, flush=True)
    
    # Convert message dicts to LangChain message objects
    langchain_messages = convert_messages_to_langchain(request.messages)
    
    state = {
        "messages": langchain_messages,
        "_messages": langchain_messages,
        "artifact": request.artifact,
        "next": request.next,
        "highlightedText": request.highlightedText,
        "language": request.language,
        "artifactLength": request.artifactLength,
        "regenerateWithEmojis": request.regenerateWithEmojis,
        "readingLevel": request.readingLevel,
        "portLanguage": request.portLanguage,
        "customQuickActionId": request.customQuickActionId,
        "webSearchEnabled": request.webSearchEnabled,
        "webSearchResults": request.webSearchResults,
    }
    
    # Log the state values that will be used for routing
    print("=== prepare_state: State values for routing ===", file=sys.stderr, flush=True)
    print(f"  state['language']: {state['language']}", file=sys.stderr, flush=True)
    print(f"  state['artifactLength']: {state['artifactLength']}", file=sys.stderr, flush=True)
    print(f"  state['regenerateWithEmojis']: {state['regenerateWithEmojis']}", file=sys.stderr, flush=True)
    print(f"  state['readingLevel']: {state['readingLevel']}", file=sys.stderr, flush=True)
    print("=============================================", file=sys.stderr, flush=True)
    
    return state


@router.post("/stream")
async def stream_agent(request: OpenCanvasRequest):
    """Stream Open Canvas agent events."""
    import sys
    print("=== STREAM START ===", file=sys.stderr, flush=True)
    
    async def generate() -> AsyncIterator[str]:
        event_count = 0
        try:
            state = prepare_state(request)
            # Handle config - it may already have configurable nested or be flat
            request_config = request.config or {}
            if "configurable" in request_config:
                # Config already has configurable nested
                config = request_config
            else:
                # Config is flat, wrap it
                config = {"configurable": request_config}
            
            print(f"Starting astream_events with config keys: {list(config.get('configurable', {}).keys())}", file=sys.stderr, flush=True)
            
            def serialize_message(msg):
                """Convert LangChain message to dict for JSON serialization."""
                if isinstance(msg, BaseMessage):
                    # Determine message type explicitly
                    msg_type = "ai"  # default
                    if isinstance(msg, HumanMessage):
                        msg_type = "human"
                    elif isinstance(msg, AIMessage):
                        msg_type = "ai"
                    elif isinstance(msg, SystemMessage):
                        msg_type = "system"
                    elif hasattr(msg, 'getType'):
                        msg_type = msg.getType()
                    
                    # Handle content - ChatBedrockConverse returns content as list of dicts
                    content = msg.content
                    if isinstance(content, str):
                        content_str = content
                    elif isinstance(content, list):
                        # ChatBedrockConverse returns content as list of dicts: [{'type': 'text', 'text': '...', 'index': 0}]
                        content_str = "".join(
                            item.get("text", "") if isinstance(item, dict) else str(item)
                            for item in content
                        )
                    else:
                        content_str = str(content)
                    
                    result = {
                        "type": msg_type,
                        "content": content_str,
                        "id": getattr(msg, 'id', None),
                        "additional_kwargs": getattr(msg, 'additional_kwargs', {}),
                    }
                    if hasattr(msg, 'response_metadata'):
                        result["response_metadata"] = msg.response_metadata
                    if hasattr(msg, 'usage_metadata'):
                        result["usage_metadata"] = msg.usage_metadata
                    return result
                return str(msg)
            
            def convert_messages_in_dict(obj):
                """Recursively convert message objects to dicts."""
                if isinstance(obj, dict):
                    result = {}
                    for key, value in obj.items():
                        if key == "messages" or key == "_messages":
                            # Convert message list
                            if isinstance(value, list):
                                result[key] = [serialize_message(msg) if isinstance(msg, BaseMessage) else msg for msg in value]
                            else:
                                result[key] = value
                        else:
                            result[key] = convert_messages_in_dict(value)
                    return result
                elif isinstance(obj, list):
                    return [convert_messages_in_dict(item) for item in obj]
                elif isinstance(obj, BaseMessage):
                    return serialize_message(obj)
                else:
                    return obj
            
            async for event in graph.astream_events(
                state,
                version="v2",
                config=config
            ):
                event_count += 1
                # Convert LangChain message objects to dicts for JSON serialization
                converted_event = convert_messages_in_dict(event)
                
                # Ensure runId is available (LangGraph uses run_id, but frontend expects runId)
                if "run_id" in converted_event and "runId" not in converted_event:
                    converted_event["runId"] = converted_event["run_id"]
                
                # Convert event to JSON and send as Server-Sent Events format
                event_json = json.dumps(converted_event, default=str)
                event_type = event.get("event", "unknown")
                event_name = event.get("name", "unknown")
                
                # Log event with type-specific information
                log_info = format_event_log(event_type, event_name, event)
                if log_info is not None:
                    print(f"#{event_count}: {log_info}", file=sys.stderr, flush=True)
                
                yield f"data: {event_json}\n\n"
            
            # Send completion signal
            yield "data: [DONE]\n\n"
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"ERROR in stream: {str(e)}\n{error_trace}", file=sys.stderr, flush=True)
            error_event = {
                "event": "error",
                "data": {"message": str(e)}
            }
            yield f"data: {json.dumps(error_event)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

