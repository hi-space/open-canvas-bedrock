"""
Base storage interface for persistent storage backends.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List


class BaseStorage(ABC):
    """Base interface for storage backends."""
    
    @abstractmethod
    def get_item(self, namespace: List[str], key: str) -> Optional[Dict[str, Any]]:
        """Get an item from the store."""
        pass
    
    @abstractmethod
    def put_item(self, namespace: List[str], key: str, value: Any) -> None:
        """Put an item into the store."""
        pass
    
    @abstractmethod
    def delete_item(self, namespace: List[str], key: str) -> bool:
        """Delete an item from the store."""
        pass
    
    @abstractmethod
    def list_items(self, namespace: List[str], prefix: Optional[str] = None) -> List[str]:
        """List all keys in a namespace, optionally filtered by prefix."""
        pass


class BaseEntityStorage(ABC):
    """Base interface for entity storage (assistants, threads, etc.)."""
    
    @abstractmethod
    def create(self, entity_type: str, entity_id: str, data: Dict) -> Dict:
        """Create a new entity."""
        pass
    
    @abstractmethod
    def get(self, entity_type: str, entity_id: str) -> Optional[Dict]:
        """Get an entity by ID."""
        pass
    
    @abstractmethod
    def update(self, entity_type: str, entity_id: str, updates: Dict) -> Optional[Dict]:
        """Update an entity."""
        pass
    
    @abstractmethod
    def delete(self, entity_type: str, entity_id: str) -> bool:
        """Delete an entity."""
        pass
    
    @abstractmethod
    def search(self, entity_type: str, filters: Optional[Dict] = None, limit: int = 100) -> List[Dict]:
        """Search entities with optional filters."""
        pass

