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


def prepare_state(request: OpenCanvasRequest) -> Dict[str, Any]:
    """Prepare state from request."""
    # Convert message dicts to LangChain message objects
    langchain_messages = convert_messages_to_langchain(request.messages)
    
    return {
        "messages": langchain_messages,
        "_messages": langchain_messages,
        "artifact": request.artifact,
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
        "webSearchResults": None,
    }


def serialize_message_for_response(msg):
    """Convert LangChain message to dict for JSON serialization (for /run endpoint)."""
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


def convert_messages_in_result(obj):
    """Recursively convert message objects to dicts in result."""
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key == "messages" or key == "_messages":
                # Convert message list
                if isinstance(value, list):
                    result[key] = [serialize_message_for_response(msg) if isinstance(msg, BaseMessage) else msg for msg in value]
                else:
                    result[key] = value
            else:
                result[key] = convert_messages_in_result(value)
        return result
    elif isinstance(obj, list):
        return [convert_messages_in_result(item) for item in obj]
    elif isinstance(obj, BaseMessage):
        return serialize_message_for_response(obj)
    else:
        return obj


@router.post("/run")
async def run_agent(request: OpenCanvasRequest):
    """Run Open Canvas agent (non-streaming)."""
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
        
        result = await graph.ainvoke(state, config=config)
        # Convert LangChain message objects to dicts for JSON serialization
        converted_result = convert_messages_in_result(result)
        return converted_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
                
                # Convert event to JSON and send as Server-Sent Events format
                event_json = json.dumps(converted_event, default=str)
                event_type = event.get("event", "unknown")
                event_name = event.get("name", "unknown")
                print(f"Yielding event #{event_count}: {event_type} from {event_name}", file=sys.stderr, flush=True)
                yield f"data: {event_json}\n\n"
            
            print(f"=== STREAM END: {event_count} events sent ===", file=sys.stderr, flush=True)
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

