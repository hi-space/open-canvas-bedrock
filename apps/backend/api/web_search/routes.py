"""
FastAPI routes for web search agent.
"""
from fastapi import APIRouter
from api.web_search.models import WebSearchRequest
from api.web_search.service import perform_web_search

router = APIRouter()


@router.post("/search")
async def search_endpoint(request: WebSearchRequest):
    """Perform web search based on messages."""
    result = await perform_web_search(
        messages=request.messages,
        config=request.config
    )
    return result
