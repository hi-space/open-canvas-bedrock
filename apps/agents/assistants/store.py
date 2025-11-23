"""
Assistant store with support for persistent storage backends.
Supports memory and DynamoDB via environment configuration.
"""
from typing import Dict, Optional, List
from datetime import datetime
import uuid
from store.factory import create_entity_storage

class AssistantStore:
    """Assistant store with persistent storage support."""
    
    def __init__(self, entity_storage=None):
        """Initialize assistant store with storage backend.
        
        Args:
            entity_storage: Optional entity storage backend instance. If not provided,
                          will be created based on environment configuration.
        """
        self._storage = entity_storage or create_entity_storage()
        self._entity_type = "assistant"
    
    def create(self, graph_id: str, name: str, config: Optional[Dict] = None, metadata: Optional[Dict] = None, if_exists: str = "do_nothing") -> Dict:
        """Create a new assistant."""
        assistant_id = str(uuid.uuid4())
        assistant = {
            "assistant_id": assistant_id,
            "graph_id": graph_id,
            "name": name,
            "config": config or {},
            "metadata": metadata or {},
        }
        return self._storage.create(self._entity_type, assistant_id, assistant)
    
    def get(self, assistant_id: str) -> Optional[Dict]:
        """Get an assistant by ID."""
        return self._storage.get(self._entity_type, assistant_id)
    
    def update(self, assistant_id: str, updates: Dict) -> Optional[Dict]:
        """Update an assistant."""
        return self._storage.update(self._entity_type, assistant_id, updates)
    
    def delete(self, assistant_id: str) -> bool:
        """Delete an assistant."""
        return self._storage.delete(self._entity_type, assistant_id)
    
    def search(self, graph_id: Optional[str] = None, metadata: Optional[Dict] = None, limit: int = 100) -> List[Dict]:
        """Search assistants."""
        filters = {}
        if graph_id:
            filters["graph_id"] = graph_id
        if metadata:
            filters["metadata"] = metadata
        
        return self._storage.search(self._entity_type, filters if filters else None, limit)

# Global assistant store instance
assistant_store = AssistantStore()

