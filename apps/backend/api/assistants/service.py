"""
Business logic for assistant management.
"""
from typing import Dict, Any, Optional, List
from api.assistants.store import assistant_store


def create_assistant(
    graph_id: str,
    name: str,
    config: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    if_exists: str = "do_nothing"
) -> Dict[str, Any]:
    """Create a new assistant."""
    return assistant_store.create(
        graph_id=graph_id,
        name=name,
        config=config,
        metadata=metadata,
        if_exists=if_exists
    )


def get_assistant(assistant_id: str) -> Optional[Dict[str, Any]]:
    """Get an assistant by ID."""
    return assistant_store.get(assistant_id)


def update_assistant(
    assistant_id: str,
    name: Optional[str] = None,
    graph_id: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """Update an assistant."""
    updates = {}
    if name is not None:
        updates["name"] = name
    if graph_id is not None:
        updates["graph_id"] = graph_id
    if config is not None:
        updates["config"] = config
    if metadata is not None:
        updates["metadata"] = metadata
    
    return assistant_store.update(assistant_id, updates)


def delete_assistant(assistant_id: str) -> bool:
    """Delete an assistant."""
    return assistant_store.delete(assistant_id)


def search_assistants(
    graph_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Search assistants."""
    return assistant_store.search(
        graph_id=graph_id,
        metadata=metadata,
        limit=limit
    )

