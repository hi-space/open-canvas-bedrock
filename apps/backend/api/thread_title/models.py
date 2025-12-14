"""
Request/Response models for thread title agent API.
"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class ThreadTitleRequest(BaseModel):
    """Request model for thread title generation."""
    messages: List[Dict[str, Any]]
    artifact: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None

