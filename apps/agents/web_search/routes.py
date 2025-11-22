"""
FastAPI routes for web search agent.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from web_search.graph import graph

router = APIRouter()


class WebSearchRequest(BaseModel):
    """Request model for web search."""
    messages: List[Dict[str, Any]]
    config: Optional[Dict[str, Any]] = None


@router.post("/search")
async def search(request: WebSearchRequest):
    """Perform web search based on messages."""
    try:
        state = {
            "messages": request.messages,
            "query": None,
            "webSearchResults": None,
            "shouldSearch": False,
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

