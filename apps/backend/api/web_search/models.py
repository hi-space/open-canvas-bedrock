"""
Request/Response models for web search agent API.
"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class WebSearchRequest(BaseModel):
    """Request model for web search."""
    messages: List[Dict[str, Any]]
    config: Optional[Dict[str, Any]] = None

