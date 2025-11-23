"""
Simple in-memory assistant store.
In production, this should be replaced with a database.
"""
from typing import Dict, Optional, List
from datetime import datetime
import uuid

class AssistantStore:
    """In-memory assistant store."""
    
    def __init__(self):
        self._assistants: Dict[str, Dict] = {}
    
    def create(self, graph_id: str, name: str, config: Optional[Dict] = None, metadata: Optional[Dict] = None, if_exists: str = "do_nothing") -> Dict:
        """Create a new assistant."""
        assistant_id = str(uuid.uuid4())
        assistant = {
            "assistant_id": assistant_id,
            "graph_id": graph_id,
            "name": name,
            "config": config or {},
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._assistants[assistant_id] = assistant
        return assistant
    
    def get(self, assistant_id: str) -> Optional[Dict]:
        """Get an assistant by ID."""
        return self._assistants.get(assistant_id)
    
    def update(self, assistant_id: str, updates: Dict) -> Optional[Dict]:
        """Update an assistant."""
        if assistant_id not in self._assistants:
            return None
        assistant = self._assistants[assistant_id]
        # Merge updates
        for key, value in updates.items():
            if key == "config" and isinstance(value, dict) and isinstance(assistant.get("config"), dict):
                # Deep merge config
                assistant["config"] = {**assistant.get("config", {}), **value}
            elif key == "metadata" and isinstance(value, dict) and isinstance(assistant.get("metadata"), dict):
                # Deep merge metadata
                assistant["metadata"] = {**assistant.get("metadata", {}), **value}
            else:
                assistant[key] = value
        assistant["updated_at"] = datetime.utcnow().isoformat()
        return assistant
    
    def delete(self, assistant_id: str) -> bool:
        """Delete an assistant."""
        if assistant_id in self._assistants:
            del self._assistants[assistant_id]
            return True
        return False
    
    def search(self, graph_id: Optional[str] = None, metadata: Optional[Dict] = None, limit: int = 100) -> List[Dict]:
        """Search assistants."""
        assistants = list(self._assistants.values())
        
        # Filter by graph_id if provided
        if graph_id:
            assistants = [a for a in assistants if a.get("graph_id") == graph_id]
        
        # Filter by metadata if provided
        if metadata:
            filtered_assistants = []
            for assistant in assistants:
                match = True
                assistant_metadata = assistant.get("metadata", {})
                for key, value in metadata.items():
                    if key not in assistant_metadata or assistant_metadata[key] != value:
                        match = False
                        break
                if match:
                    filtered_assistants.append(assistant)
            assistants = filtered_assistants
        
        # Sort by created_at descending
        assistants.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return assistants[:limit]

# Global assistant store instance
assistant_store = AssistantStore()

