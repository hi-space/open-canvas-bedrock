"""
FastAPI routes for thread management.
Implements LangGraph SDK compatible thread endpoints.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from threads.store import thread_store

router = APIRouter()


class ThreadCreateRequest(BaseModel):
    """Request model for thread creation."""
    metadata: Optional[Dict[str, Any]] = None


class ThreadSearchRequest(BaseModel):
    """Request model for thread search."""
    limit: Optional[int] = 100
    filter: Optional[Dict[str, Any]] = None


@router.post("")
async def create_thread(request: ThreadCreateRequest):
    """Create a new thread."""
    try:
        thread = thread_store.create(metadata=request.metadata)
        return thread
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{thread_id}")
async def get_thread(thread_id: str):
    """Get a thread by ID."""
    try:
        thread = thread_store.get(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
        return thread
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
async def search_threads(request: ThreadSearchRequest):
    """Search threads."""
    try:
        limit = request.limit or 100
        threads = thread_store.search(limit=limit)
        
        # Apply filter if provided
        if request.filter:
            # Simple filtering - in production, implement more sophisticated filtering
            filtered_threads = []
            for thread in threads:
                match = True
                for key, value in request.filter.items():
                    if key in thread.get("metadata", {}) and thread["metadata"][key] != value:
                        match = False
                        break
                if match:
                    filtered_threads.append(thread)
            threads = filtered_threads
        
        return threads
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{thread_id}")
async def delete_thread(thread_id: str):
    """Delete a thread."""
    try:
        deleted = thread_store.delete(thread_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
        return {"status": "deleted", "thread_id": thread_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

