"""
FastAPI routes for thread management.
Implements LangGraph SDK compatible thread endpoints.
"""
from fastapi import APIRouter
from fastapi.exceptions import HTTPException
from api.threads.models import (
    ThreadCreateRequest,
    ThreadSearchRequest,
    ThreadUpdateRequest
)
from api.threads.service import (
    create_thread,
    get_thread,
    search_threads,
    delete_thread,
    update_thread_state,
    get_artifact_metadata,
    get_artifact_version,
)
from core.exceptions import NotFoundError

router = APIRouter()


@router.post("")
async def create_thread_endpoint(request: ThreadCreateRequest):
    """Create a new thread."""
    thread = create_thread(metadata=request.metadata)
    return thread


@router.get("/{thread_id}")
async def get_thread_endpoint(thread_id: str):
    """Get a thread by ID."""
    thread = get_thread(thread_id)
    if not thread:
        raise NotFoundError("Thread", thread_id)
    return thread


@router.post("/search")
async def search_threads_endpoint(request: ThreadSearchRequest):
    """Search threads."""
    limit = request.limit or 100
    threads = search_threads(limit=limit, filter_dict=request.filter)
    return threads


@router.delete("/{thread_id}")
async def delete_thread_endpoint(thread_id: str):
    """Delete a thread."""
    deleted = delete_thread(thread_id)
    if not deleted:
        raise NotFoundError("Thread", thread_id)
    return {"status": "deleted", "thread_id": thread_id}


@router.post("/{thread_id}/state")
async def update_thread_state_endpoint(thread_id: str, request: ThreadUpdateRequest):
    """Update thread state (values and/or metadata).
    
    This endpoint is compatible with LangGraph SDK's updateState method.
    """
    updated_thread = update_thread_state(
        thread_id,
        values=request.values,
        metadata=request.metadata
    )
    if not updated_thread:
        raise NotFoundError("Thread", thread_id)
    return updated_thread


@router.get("/{thread_id}/artifact/versions")
async def get_artifact_versions_endpoint(thread_id: str):
    """Get artifact version metadata (version list, current_index, etc.) without full content."""
    metadata = get_artifact_metadata(thread_id)
    if metadata is None:
        raise NotFoundError("Artifact", f"for thread {thread_id}")
    return metadata


@router.get("/{thread_id}/artifact/versions/{version_index}")
async def get_artifact_version_endpoint(thread_id: str, version_index: int):
    """Get a specific artifact version for a thread."""
    artifact = get_artifact_version(thread_id, version_index)
    if artifact is None:
        raise NotFoundError(
            "Artifact version",
            f"{version_index} for thread {thread_id}"
        )
    return artifact
