"""
FastAPI routes for summarizer agent.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from summarizer.graph import graph

router = APIRouter()


class SummarizerRequest(BaseModel):
    """Request model for summarizer."""
    messages: List[Dict[str, Any]]
    threadId: str
    config: Optional[Dict[str, Any]] = None


@router.post("/summarize")
async def summarize(request: SummarizerRequest):
    """Summarize conversation messages."""
    try:
        state = {
            "messages": request.messages,
            "threadId": request.threadId,
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

