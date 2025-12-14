"""
FastAPI routes for store management.
Implements LangGraph SDK compatible store endpoints.
"""
from fastapi import APIRouter
from fastapi.exceptions import HTTPException
from api.store.models import (
    StoreGetRequest,
    StorePutRequest,
    StoreDeleteRequest
)
from api.store.service import (
    get_store_item,
    put_store_item,
    delete_store_item,
)
from core.exceptions import NotFoundError

router = APIRouter()


@router.post("/get")
async def get_store_item_endpoint(request: StoreGetRequest):
    """Get an item from the store."""
    item = get_store_item(request.namespace, request.key)
    if item is None:
        return {"item": None}
    return {"item": item}


@router.post("/put")
async def put_store_item_endpoint(request: StorePutRequest):
    """Put an item into the store."""
    put_store_item(request.namespace, request.key, request.value)
    return {"success": True}


@router.post("/delete")
async def delete_store_item_endpoint(request: StoreDeleteRequest):
    """Delete an item from the store."""
    deleted = delete_store_item(request.namespace, request.key)
    if not deleted:
        raise NotFoundError("Store item", f"{request.namespace}/{request.key}")
    return {"success": True}
