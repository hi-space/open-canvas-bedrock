"""
FastAPI routes for assistant management.
Implements LangGraph SDK compatible assistant endpoints.
"""
import sys
from fastapi import APIRouter
from api.assistants.models import (
    AssistantCreateRequest,
    AssistantUpdateRequest,
    AssistantSearchRequest
)
from api.assistants.service import (
    create_assistant,
    get_assistant,
    update_assistant,
    delete_assistant,
    search_assistants,
)
from core.exceptions import NotFoundError

router = APIRouter()


@router.post("")
async def create_assistant_endpoint(request: AssistantCreateRequest):
    """Create a new assistant."""
    assistant = create_assistant(
        graph_id=request.graph_id,
        name=request.name,
        config=request.config,
        metadata=request.metadata,
        if_exists=request.if_exists or "do_nothing"
    )
    return assistant


@router.get("/{assistant_id}")
async def get_assistant_endpoint(assistant_id: str):
    """Get an assistant by ID."""
    assistant = get_assistant(assistant_id)
    if not assistant:
        raise NotFoundError("Assistant", assistant_id)
    return assistant


@router.put("/{assistant_id}")
async def update_assistant_put_endpoint(assistant_id: str, request: AssistantUpdateRequest):
    """Update an assistant (PUT method)."""
    return await update_assistant_endpoint(assistant_id, request)


@router.patch("/{assistant_id}")
async def update_assistant_patch_endpoint(assistant_id: str, request: AssistantUpdateRequest):
    """Update an assistant (PATCH method)."""
    return await update_assistant_endpoint(assistant_id, request)


async def update_assistant_endpoint(assistant_id: str, request: AssistantUpdateRequest):
    """Update an assistant (shared implementation)."""
    updated_assistant = update_assistant(
        assistant_id,
        name=request.name,
        graph_id=request.graph_id,
        config=request.config,
        metadata=request.metadata
    )
    if not updated_assistant:
        raise NotFoundError("Assistant", assistant_id)
    return updated_assistant


@router.delete("/{assistant_id}")
async def delete_assistant_endpoint(assistant_id: str):
    """Delete an assistant."""
    deleted = delete_assistant(assistant_id)
    if not deleted:
        raise NotFoundError("Assistant", assistant_id)
    return {"status": "deleted", "assistant_id": assistant_id}


@router.post("/search")
async def search_assistants_endpoint(request: AssistantSearchRequest):
    """Search assistants."""
    limit = request.limit or 100
    print(f"Assistant search request: graph_id={request.graph_id}, metadata={request.metadata}, limit={limit}", file=sys.stderr, flush=True)
    assistants = search_assistants(
        graph_id=request.graph_id,
        metadata=request.metadata,
        limit=limit
    )
    print(f"Assistant search result: found {len(assistants)} assistants", file=sys.stderr, flush=True)
    return assistants
