"""
Request/Response models for assistant API.
"""
from pydantic import BaseModel
from typing import Dict, Any, Optional


class AssistantCreateRequest(BaseModel):
    """Request model for assistant creation."""
    graph_id: str
    name: str
    config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    if_exists: Optional[str] = "do_nothing"


class AssistantUpdateRequest(BaseModel):
    """Request model for assistant update."""
    name: Optional[str] = None
    graph_id: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class AssistantSearchRequest(BaseModel):
    """Request model for assistant search."""
    graph_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    limit: Optional[int] = 100

