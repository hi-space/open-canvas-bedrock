"""
Thread store with normalized storage backends.
Supports memory, SQLite, and DynamoDB via environment configuration.
Uses normalized structure: threads, messages, and artifacts are stored separately.
"""
from typing import Dict, Optional, List
from datetime import datetime
import uuid
from store.factory import create_thread_storage

class ThreadStore:
    """Thread store with normalized persistent storage support."""
    
    def __init__(self, thread_storage=None):
        """Initialize thread store with storage backend.
        
        Args:
            thread_storage: Optional thread storage backend instance. If not provided,
                              will be created based on environment configuration.
        """
        self._storage = thread_storage or create_thread_storage()
    
    def create(self, metadata: Optional[Dict] = None) -> Dict:
        """Create a new thread."""
        thread_id = str(uuid.uuid4())
        return self._storage.create_thread(thread_id, metadata)
    
    def get(self, thread_id: str) -> Optional[Dict]:
        """Get a thread by ID (includes messages and artifact in values)."""
        thread = self._storage.get_thread(thread_id)
        if thread is None:
            return None
        
        # Get messages and artifact
        messages = self._storage.get_thread_messages(thread_id)
        artifact = self._storage.get_thread_artifact(thread_id)
        
        # Return in LangGraph SDK compatible format
        return {
            "thread_id": thread["thread_id"],
            "metadata": thread.get("metadata", {}),
            "values": {
                "messages": messages,
                **({"artifact": artifact} if artifact else {}),
            },
            "created_at": thread.get("created_at"),
            "updated_at": thread.get("updated_at"),
        }
    
    def update(self, thread_id: str, updates: Dict) -> Optional[Dict]:
        """Update a thread.
        
        Updates can include:
        - metadata: Updates thread metadata
        - values: Updates messages and/or artifact
        """
        # Update metadata if provided
        if "metadata" in updates:
            self._storage.update_thread_metadata(thread_id, updates["metadata"])
        
        # Update values if provided
        if "values" in updates:
            values = updates["values"]
            
            # Update messages if provided
            if "messages" in values:
                self._storage.set_thread_messages(thread_id, values["messages"])
            
            # Update artifact if provided
            if "artifact" in values:
                self._storage.set_thread_artifact(thread_id, values["artifact"])
            elif "artifact" in values and values["artifact"] is None:
                # Delete artifact if explicitly set to None
                self._storage.delete_thread_artifact(thread_id)
        
        # Return updated thread
        return self.get(thread_id)
    
    def delete(self, thread_id: str) -> bool:
        """Delete a thread and all associated data."""
        return self._storage.delete_thread(thread_id)
    
    def search(self, limit: int = 100) -> List[Dict]:
        """Search threads (returns all threads sorted by updated_at descending).
        
        Includes first message for each thread to enable title display in UI.
        Use get() to retrieve full thread with all messages and artifact.
        """
        threads = self._storage.search_threads(limit)
        # Convert to LangGraph SDK compatible format
        result = []
        for t in threads:
            thread_id = t["thread_id"]
            # Get first message for title display
            messages = self._storage.get_thread_messages(thread_id)
            first_message = messages[0] if messages else None
            
            thread_dict = {
                "thread_id": thread_id,
                "metadata": t.get("metadata", {}),
                "values": {
                    "messages": [first_message] if first_message else []
                },
                "created_at": t.get("created_at"),
                "updated_at": t.get("updated_at"),
            }
            result.append(thread_dict)
        
        return result

# Global thread store instance
thread_store = ThreadStore()

