"""
FastAPI routes for thread title agent.
"""
from fastapi import APIRouter
from api.thread_title.models import ThreadTitleRequest
from api.thread_title.service import generate_title

router = APIRouter()


@router.post("/generate")
async def generate_title_endpoint(request: ThreadTitleRequest):
    """Generate title for conversation."""
    result = await generate_title(
        messages=request.messages,
        artifact=request.artifact,
        config=request.config
    )
    return result
