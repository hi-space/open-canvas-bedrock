"""
FastAPI routes for store management.
Implements LangGraph SDK compatible store endpoints.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
from store.store import store

router = APIRouter()


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


@router.post("/get")
async def get_store_item(request: StoreGetRequest):
    """Get an item from the store."""
    try:
        item = store.get_item(request.namespace, request.key)
        if item is None:
            return {"item": None}
        return {"item": item}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/put")
async def put_store_item(request: StorePutRequest):
    """Put an item into the store."""
    try:
        store.put_item(request.namespace, request.key, request.value)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delete")
async def delete_store_item(request: StoreDeleteRequest):
    """Delete an item from the store."""
    try:
        deleted = store.delete_item(request.namespace, request.key)
        if not deleted:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

