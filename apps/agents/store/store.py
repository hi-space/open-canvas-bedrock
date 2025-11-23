"""
Store for LangGraph SDK compatibility.
Supports memory and DynamoDB backends via environment configuration.
"""
from typing import Dict, Any, Optional, List
from store.factory import create_storage

class Store:
    """Store compatible with LangGraph SDK.
    
    Uses persistent storage (DynamoDB) or in-memory storage
    based on STORAGE_TYPE environment variable.
    """
    
    def __init__(self, storage=None):
        """Initialize store with storage backend.
        
        Args:
            storage: Optional storage backend instance. If not provided,
                    will be created based on environment configuration.
        """
        self._storage = storage or create_storage()
    
    def get_item(self, namespace: List[str], key: str) -> Optional[Dict[str, Any]]:
        """Get an item from the store."""
        return self._storage.get_item(namespace, key)
    
    def put_item(self, namespace: List[str], key: str, value: Any) -> None:
        """Put an item into the store."""
        self._storage.put_item(namespace, key, value)
    
    def delete_item(self, namespace: List[str], key: str) -> bool:
        """Delete an item from the store."""
        return self._storage.delete_item(namespace, key)

# Global store instance
store = Store()

