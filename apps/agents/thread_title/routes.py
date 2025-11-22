"""
FastAPI routes for thread title agent.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from thread_title.graph import graph

router = APIRouter()


class ThreadTitleRequest(BaseModel):
    """Request model for thread title generation."""
    messages: List[Dict[str, Any]]
    artifact: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None


@router.post("/generate")
async def generate_title(request: ThreadTitleRequest):
    """Generate title for conversation."""
    try:
        state = {
            "messages": request.messages,
            "artifact": request.artifact,
        }
        # Handle config - it may already have configurable nested or be flat
        request_config = request.config or {}
        if "configurable" in request_config:
            # Config already has configurable nested
            config = request_config
        else:
            # Config is flat, wrap it
            config = {"configurable": request_config}
        
        result = await graph.ainvoke(state, config=config)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

