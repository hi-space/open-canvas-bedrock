"""
Normalized thread storage for threads, messages, and artifacts.
Separates large data (messages, artifacts) from thread metadata.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List


class BaseThreadStorage(ABC):
    """Base interface for normalized thread storage."""
    
    @abstractmethod
    def create_thread(self, thread_id: str, metadata: Optional[Dict] = None) -> Dict:
        """Create a new thread."""
        pass
    
    @abstractmethod
    def get_thread(self, thread_id: str) -> Optional[Dict]:
        """Get thread metadata."""
        pass
    
    @abstractmethod
    def update_thread_metadata(self, thread_id: str, metadata: Dict) -> Optional[Dict]:
        """Update thread metadata."""
        pass
    
    @abstractmethod
    def delete_thread(self, thread_id: str) -> bool:
        """Delete thread and all associated data."""
        pass
    
    @abstractmethod
    def search_threads(self, limit: int = 100) -> List[Dict]:
        """Search threads sorted by updated_at descending."""
        pass
    
    @abstractmethod
    def get_thread_messages(self, thread_id: str) -> List[Dict]:
        """Get all messages for a thread."""
        pass
    
    @abstractmethod
    def set_thread_messages(self, thread_id: str, messages: List[Dict]) -> None:
        """Set all messages for a thread (replaces existing)."""
        pass
    
    @abstractmethod
    def get_thread_artifact(self, thread_id: str) -> Optional[Dict]:
        """Get artifact for a thread."""
        pass
    
    @abstractmethod
    def set_thread_artifact(self, thread_id: str, artifact: Dict) -> None:
        """Set artifact for a thread."""
        pass
    
    @abstractmethod
    def delete_thread_artifact(self, thread_id: str) -> bool:
        """Delete artifact for a thread."""
        pass

