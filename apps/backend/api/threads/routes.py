"""
FastAPI routes for thread management.
Implements LangGraph SDK compatible thread endpoints.
"""
from typing import Optional
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


@router.get("/{thread_id}/artifact")
async def get_artifact_endpoint(thread_id: str, version: Optional[int] = None):
    """Get artifact for a thread.
    
    Args:
        thread_id: Thread ID
        version: Optional version index. If not provided, returns the latest version.
    
    Returns:
        Artifact dict with the specified version, or latest if version is not provided.
    """
    if version is not None:
        # Validate version exists before fetching
        metadata = get_artifact_metadata(thread_id)
        if metadata is None:
            raise NotFoundError("Artifact", f"for thread {thread_id}")
        
        # Check if requested version exists
        version_indices = metadata.get("version_indices", [])
        if version not in version_indices:
            # Provide helpful error message with available versions
            available_versions = ", ".join(map(str, version_indices)) if version_indices else "none"
            raise NotFoundError(
                "Artifact version",
                f"{version} for thread {thread_id}. Available versions: {available_versions}"
            )
        
        # Get specific version
        artifact = get_artifact_version(thread_id, version)
        if artifact is None:
            # This shouldn't happen if metadata is correct, but handle it gracefully
            raise NotFoundError(
                "Artifact version",
                f"{version} for thread {thread_id}"
            )
        return artifact
    else:
        # Get latest version
        thread = get_thread(thread_id)
        if not thread:
            raise NotFoundError("Thread", thread_id)
        artifact = thread.get("values", {}).get("artifact")
        if artifact is None:
            raise NotFoundError("Artifact", f"for thread {thread_id}")
        return artifact


@router.get("/{thread_id}/artifact/versions")
async def get_artifact_versions_endpoint(thread_id: str):
    """Get artifact version metadata (version list, current_index, etc.) without full content."""
    metadata = get_artifact_metadata(thread_id)
    if metadata is None:
        raise NotFoundError("Artifact", f"for thread {thread_id}")
    return metadata
