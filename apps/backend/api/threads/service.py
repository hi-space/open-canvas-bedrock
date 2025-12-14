"""
Business logic for thread management.
"""
from typing import Dict, Any, Optional, List
from api.threads.store import thread_store


def create_thread(metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create a new thread."""
    return thread_store.create(metadata=metadata)


def get_thread(thread_id: str) -> Optional[Dict[str, Any]]:
    """Get a thread by ID."""
    return thread_store.get(thread_id)


def search_threads(limit: int = 100, filter_dict: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Search threads with optional filtering."""
    threads = thread_store.search(limit=limit)
    
    # Apply filter if provided
    if filter_dict:
        filtered_threads = []
        for thread in threads:
            match = True
            for key, value in filter_dict.items():
                if key in thread.get("metadata", {}) and thread["metadata"][key] != value:
                    match = False
                    break
            if match:
                filtered_threads.append(thread)
        threads = filtered_threads
    
    return threads


def delete_thread(thread_id: str) -> bool:
    """Delete a thread."""
    return thread_store.delete(thread_id)


def update_thread_state(
    thread_id: str,
    values: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """Update thread state (values and/or metadata)."""
    thread = thread_store.get(thread_id)
    if not thread:
        return None
    
    # Prepare updates dictionary
    updates = {}
    
    # Update values if provided - merge with existing values
    if values is not None:
        existing_values = thread.get("values", {})
        merged_values = {**existing_values, **values}
        updates["values"] = merged_values
    
    # Update metadata if provided - merge with existing metadata
    if metadata is not None:
        existing_metadata = thread.get("metadata", {})
        merged_metadata = {**existing_metadata, **metadata}
        updates["metadata"] = merged_metadata
    
    # Update the thread in store
    return thread_store.update(thread_id, updates)


def get_artifact_metadata(thread_id: str) -> Optional[Dict[str, Any]]:
    """Get artifact version metadata."""
    return thread_store.get_artifact_metadata(thread_id)


def get_artifact_version(thread_id: str, version_index: int) -> Optional[Dict[str, Any]]:
    """Get a specific artifact version for a thread."""
    return thread_store.get_artifact_version(thread_id, version_index)

