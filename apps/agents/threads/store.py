"""
Simple in-memory thread store.
In production, this should be replaced with a database.
"""
from typing import Dict, Optional, List
from datetime import datetime
import uuid

class ThreadStore:
    """In-memory thread store."""
    
    def __init__(self):
        self._threads: Dict[str, Dict] = {}
    
    def create(self, metadata: Optional[Dict] = None) -> Dict:
        """Create a new thread."""
        thread_id = str(uuid.uuid4())
        thread = {
            "thread_id": thread_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
            "values": {},
        }
        self._threads[thread_id] = thread
        return thread
    
    def get(self, thread_id: str) -> Optional[Dict]:
        """Get a thread by ID."""
        return self._threads.get(thread_id)
    
    def update(self, thread_id: str, updates: Dict) -> Optional[Dict]:
        """Update a thread."""
        if thread_id not in self._threads:
            return None
        thread = self._threads[thread_id]
        thread.update(updates)
        thread["updated_at"] = datetime.utcnow().isoformat()
        return thread
    
    def delete(self, thread_id: str) -> bool:
        """Delete a thread."""
        if thread_id in self._threads:
            del self._threads[thread_id]
            return True
        return False
    
    def search(self, limit: int = 100) -> List[Dict]:
        """Search threads (returns all threads sorted by updated_at descending)."""
        threads = list(self._threads.values())
        # Sort by updated_at descending
        threads.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return threads[:limit]

# Global thread store instance
thread_store = ThreadStore()

