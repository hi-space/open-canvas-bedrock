"""
Request/Response models for thread API.
"""
from pydantic import BaseModel
from typing import Dict, Any, Optional


class ThreadCreateRequest(BaseModel):
    """Request model for thread creation."""
    metadata: Optional[Dict[str, Any]] = None


class ThreadSearchRequest(BaseModel):
    """Request model for thread search."""
    limit: Optional[int] = 100
    filter: Optional[Dict[str, Any]] = None


class ThreadUpdateRequest(BaseModel):
    """Request model for thread update."""
    values: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

