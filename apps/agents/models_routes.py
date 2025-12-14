"""
FastAPI routes for model configuration.
"""
from fastapi import APIRouter
from models import ALL_MODELS, DEFAULT_MODEL_NAME, DEFAULT_MODEL_CONFIG

router = APIRouter()


@router.get("/list")
async def get_models():
    """Get list of available models."""
    return {
        "models": ALL_MODELS,
        "defaultModelName": DEFAULT_MODEL_NAME,
        "defaultModelConfig": DEFAULT_MODEL_CONFIG,
    }
