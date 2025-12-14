"""
Request/Response models for store API.
"""
from pydantic import BaseModel
from typing import List, Any


class StoreGetRequest(BaseModel):
    """Request model for getting a store item."""
    namespace: List[str]
    key: str


class StorePutRequest(BaseModel):
    """Request model for putting a store item."""
    namespace: List[str]
    key: str
    value: Any


class StoreDeleteRequest(BaseModel):
    """Request model for deleting a store item."""
    namespace: List[str]
    key: str

