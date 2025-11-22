"""
FastAPI routes for reflection agent.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from reflection.graph import graph

router = APIRouter()


class ReflectionRequest(BaseModel):
    """Request model for reflection."""
    messages: List[Dict[str, Any]]
    artifact: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None


@router.post("/reflect")
async def reflect(request: ReflectionRequest):
    """Run reflection on conversation and artifact."""
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

