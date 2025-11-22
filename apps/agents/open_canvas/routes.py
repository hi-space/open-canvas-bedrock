"""
FastAPI routes for Open Canvas agent.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, AsyncIterator
import json
from open_canvas.graph import graph

router = APIRouter()


class OpenCanvasRequest(BaseModel):
    """Request model for Open Canvas agent."""
    messages: List[Dict[str, Any]]
    artifact: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None


def prepare_state(request: OpenCanvasRequest) -> Dict[str, Any]:
    """Prepare state from request."""
    return {
        "messages": request.messages,
        "_messages": request.messages,
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


@router.post("/run")
async def run_agent(request: OpenCanvasRequest):
    """Run Open Canvas agent (non-streaming)."""
    try:
        state = prepare_state(request)
        config = request.config or {}
        
        result = await graph.ainvoke(state, config={"configurable": config})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def stream_agent(request: OpenCanvasRequest):
    """Stream Open Canvas agent events."""
    async def generate() -> AsyncIterator[str]:
        try:
            state = prepare_state(request)
            config = request.config or {}
            
            async for event in graph.astream_events(
                state,
                version="v2",
                config={"configurable": config}
            ):
                # Convert event to JSON and send as Server-Sent Events format
                event_json = json.dumps(event, default=str)
                yield f"data: {event_json}\n\n"
            
            # Send completion signal
            yield "data: [DONE]\n\n"
        except Exception as e:
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

