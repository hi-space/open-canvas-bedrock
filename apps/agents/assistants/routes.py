"""
FastAPI routes for assistant management.
Implements LangGraph SDK compatible assistant endpoints.
"""
import sys
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from assistants.store import assistant_store

router = APIRouter()


class AssistantCreateRequest(BaseModel):
    """Request model for assistant creation."""
    graph_id: str
    name: str
    config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    if_exists: Optional[str] = "do_nothing"


class AssistantUpdateRequest(BaseModel):
    """Request model for assistant update."""
    name: Optional[str] = None
    graph_id: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class AssistantSearchRequest(BaseModel):
    """Request model for assistant search."""
    graph_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    limit: Optional[int] = 100


@router.post("")
async def create_assistant(request: AssistantCreateRequest):
    """Create a new assistant."""
    try:
        assistant = assistant_store.create(
            graph_id=request.graph_id,
            name=request.name,
            config=request.config,
            metadata=request.metadata,
            if_exists=request.if_exists or "do_nothing"
        )
        return assistant
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{assistant_id}")
async def get_assistant(assistant_id: str):
    """Get an assistant by ID."""
    try:
        assistant = assistant_store.get(assistant_id)
        if not assistant:
            raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")
        return assistant
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{assistant_id}")
async def update_assistant_put(assistant_id: str, request: AssistantUpdateRequest):
    """Update an assistant (PUT method)."""
    return await update_assistant(assistant_id, request)


@router.patch("/{assistant_id}")
async def update_assistant_patch(assistant_id: str, request: AssistantUpdateRequest):
    """Update an assistant (PATCH method)."""
    return await update_assistant(assistant_id, request)


async def update_assistant(assistant_id: str, request: AssistantUpdateRequest):
    """Update an assistant (shared implementation)."""
    try:
        assistant = assistant_store.get(assistant_id)
        if not assistant:
            raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")
        
        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.graph_id is not None:
            updates["graph_id"] = request.graph_id
        if request.config is not None:
            updates["config"] = request.config
        if request.metadata is not None:
            updates["metadata"] = request.metadata
        
        updated_assistant = assistant_store.update(assistant_id, updates)
        if not updated_assistant:
            raise HTTPException(status_code=500, detail="Failed to update assistant")
        
        return updated_assistant
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{assistant_id}")
async def delete_assistant(assistant_id: str):
    """Delete an assistant."""
    try:
        deleted = assistant_store.delete(assistant_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")
        return {"status": "deleted", "assistant_id": assistant_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
async def search_assistants(request: AssistantSearchRequest):
    """Search assistants."""
    try:
        limit = request.limit or 100
        print(f"Assistant search request: graph_id={request.graph_id}, metadata={request.metadata}, limit={limit}", file=sys.stderr, flush=True)
        assistants = assistant_store.search(
            graph_id=request.graph_id,
            metadata=request.metadata,
            limit=limit
        )
        print(f"Assistant search result: found {len(assistants)} assistants", file=sys.stderr, flush=True)
        return assistants
    except Exception as e:
        print(f"Assistant search error: {str(e)}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=500, detail=str(e))

