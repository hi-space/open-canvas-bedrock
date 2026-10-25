"""
FastAPI routes for model configuration.
"""
from fastapi import APIRouter
from core.models import get_model_catalog

router = APIRouter()


@router.get("/list")
async def get_models():
    """Get list of available models."""
    return get_model_catalog()

