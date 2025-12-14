"""
Business logic for store management.
"""
from typing import Dict, Any, List, Optional
from store.store import store


def get_store_item(namespace: List[str], key: str) -> Optional[Dict[str, Any]]:
    """Get an item from the store."""
    return store.get_item(namespace, key)


def put_store_item(namespace: List[str], key: str, value: Any) -> None:
    """Put an item into the store."""
    store.put_item(namespace, key, value)


def delete_store_item(namespace: List[str], key: str) -> bool:
    """Delete an item from the store."""
    return store.delete_item(namespace, key)

