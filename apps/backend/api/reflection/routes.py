"""
FastAPI routes for reflection agent.
"""
from fastapi import APIRouter
from api.reflection.models import ReflectionRequest
from api.reflection.service import run_reflection

router = APIRouter()


@router.post("/reflect")
async def reflect(request: ReflectionRequest):
    """Run reflection on conversation and artifact."""
    result = await run_reflection(
        messages=request.messages,
        artifact=request.artifact,
        config=request.config
    )
    return result
