"""
Request/Response models for reflection agent API.
"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class ReflectionRequest(BaseModel):
    """Request model for reflection."""
    messages: List[Dict[str, Any]]
    artifact: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None

