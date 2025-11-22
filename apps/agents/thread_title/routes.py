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
        config = request.config or {}
        
        result = await graph.ainvoke(state, config={"configurable": config})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

