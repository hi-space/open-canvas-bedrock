"""
Simple in-memory store for LangGraph SDK compatibility.
In production, this should be replaced with a database.
"""
from typing import Dict, Any, Optional, List
from datetime import datetime

class Store:
    """In-memory store compatible with LangGraph SDK."""
    
    def __init__(self):
        # Store structure: {namespace_key: {key: {value: ..., updatedAt: ...}}}
        self._store: Dict[str, Dict[str, Dict[str, Any]]] = {}
    
    def _get_namespace_key(self, namespace: List[str]) -> str:
        """Convert namespace list to a string key."""
        return "/".join(str(n) for n in namespace)
    
    def get_item(self, namespace: List[str], key: str) -> Optional[Dict[str, Any]]:
        """Get an item from the store."""
        namespace_key = self._get_namespace_key(namespace)
        if namespace_key not in self._store:
            return None
        if key not in self._store[namespace_key]:
            return None
        item = self._store[namespace_key][key]
        return {
            "value": item.get("value"),
            "updatedAt": item.get("updatedAt"),
        }
    
    def put_item(self, namespace: List[str], key: str, value: Any) -> None:
        """Put an item into the store."""
        namespace_key = self._get_namespace_key(namespace)
        if namespace_key not in self._store:
            self._store[namespace_key] = {}
        
        self._store[namespace_key][key] = {
            "value": value,
            "updatedAt": datetime.utcnow().isoformat(),
        }
    
    def delete_item(self, namespace: List[str], key: str) -> bool:
        """Delete an item from the store."""
        namespace_key = self._get_namespace_key(namespace)
        if namespace_key not in self._store:
            return False
        if key not in self._store[namespace_key]:
            return False
        del self._store[namespace_key][key]
        return True

# Global store instance
store = Store()

