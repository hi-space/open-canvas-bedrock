"""
In-memory storage backend (for backward compatibility and testing).
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
from store.base import BaseStorage, BaseEntityStorage


class MemoryStorage(BaseStorage):
    """In-memory storage backend for key-value store."""
    
    def __init__(self):
        """Initialize in-memory storage."""
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
    
    def list_items(self, namespace: List[str], prefix: Optional[str] = None) -> List[str]:
        """List all keys in a namespace, optionally filtered by prefix."""
        namespace_key = self._get_namespace_key(namespace)
        if namespace_key not in self._store:
            return []
        
        keys = list(self._store[namespace_key].keys())
        if prefix:
            keys = [k for k in keys if k.startswith(prefix)]
        
        return keys


class MemoryEntityStorage(BaseEntityStorage):
    """In-memory storage backend for entity storage."""
    
    def __init__(self):
        """Initialize in-memory entity storage."""
        # Store structure: {entity_type: {entity_id: entity_data}}
        self._entities: Dict[str, Dict[str, Dict]] = {}
    
    def create(self, entity_type: str, entity_id: str, data: Dict) -> Dict:
        """Create a new entity."""
        now = datetime.utcnow().isoformat()
        entity = {**data, "created_at": now, "updated_at": now}
        
        if entity_type not in self._entities:
            self._entities[entity_type] = {}
        
        self._entities[entity_type][entity_id] = entity
        return entity
    
    def get(self, entity_type: str, entity_id: str) -> Optional[Dict]:
        """Get an entity by ID."""
        if entity_type not in self._entities:
            return None
        return self._entities[entity_type].get(entity_id)
    
    def update(self, entity_type: str, entity_id: str, updates: Dict) -> Optional[Dict]:
        """Update an entity."""
        if entity_type not in self._entities:
            return None
        if entity_id not in self._entities[entity_type]:
            return None
        
        entity = self._entities[entity_type][entity_id]
        
        # Merge updates (entities table is now only for assistants, not threads)
        for key, value in updates.items():
            if key == "config" and isinstance(value, dict) and isinstance(entity.get("config"), dict):
                entity["config"] = {**entity.get("config", {}), **value}
            elif key == "metadata" and isinstance(value, dict) and isinstance(entity.get("metadata"), dict):
                entity["metadata"] = {**entity.get("metadata", {}), **value}
            else:
                entity[key] = value
        
        entity["updated_at"] = datetime.utcnow().isoformat()
        return entity
    
    def delete(self, entity_type: str, entity_id: str) -> bool:
        """Delete an entity."""
        if entity_type not in self._entities:
            return False
        if entity_id not in self._entities[entity_type]:
            return False
        del self._entities[entity_type][entity_id]
        return True
    
    def search(self, entity_type: str, filters: Optional[Dict] = None, limit: int = 100) -> List[Dict]:
        """Search entities with optional filters."""
        if entity_type not in self._entities:
            return []
        
        entities = list(self._entities[entity_type].values())
        
        # Apply filters if provided
        if filters:
            filtered_entities = []
            for entity in entities:
                match = True
                for key, value in filters.items():
                    if key == "graph_id" and entity.get("graph_id") != value:
                        match = False
                        break
                    elif key == "metadata":
                        if not isinstance(value, dict):
                            match = False
                            break
                        entity_metadata = entity.get("metadata", {})
                        for meta_key, meta_value in value.items():
                            if entity_metadata.get(meta_key) != meta_value:
                                match = False
                                break
                        if not match:
                            break
                    else:
                        if entity.get(key) != value:
                            match = False
                            break
                
                if match:
                    filtered_entities.append(entity)
            entities = filtered_entities
        
        # Sort by updated_at descending
        entities.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return entities[:limit]


class MemoryThreadStorage:
    """In-memory storage backend for normalized thread storage."""
    
    def __init__(self):
        """Initialize in-memory thread storage."""
        # threads: {thread_id: {metadata, created_at, updated_at}}
        self._threads: Dict[str, Dict] = {}
        # messages: {thread_id: [message1, message2, ...]}
        self._messages: Dict[str, List[Dict]] = {}
        # artifacts: {thread_id: {version_index: artifact_data}}
        self._artifacts: Dict[str, Dict[int, Dict]] = {}
    
    def create_thread(self, thread_id: str, metadata: Optional[Dict] = None) -> Dict:
        """Create a new thread."""
        now = datetime.utcnow().isoformat()
        thread = {
            "thread_id": thread_id,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }
        self._threads[thread_id] = thread
        self._messages[thread_id] = []
        return thread
    
    def get_thread(self, thread_id: str) -> Optional[Dict]:
        """Get thread metadata."""
        return self._threads.get(thread_id)
    
    def update_thread_metadata(self, thread_id: str, metadata: Dict) -> Optional[Dict]:
        """Update thread metadata."""
        if thread_id not in self._threads:
            return None
        
        thread = self._threads[thread_id]
        thread["metadata"] = {**thread.get("metadata", {}), **metadata}
        thread["updated_at"] = datetime.utcnow().isoformat()
        return thread
    
    def delete_thread(self, thread_id: str) -> bool:
        """Delete thread and all associated data."""
        if thread_id in self._threads:
            del self._threads[thread_id]
        if thread_id in self._messages:
            del self._messages[thread_id]
        if thread_id in self._artifacts:
            del self._artifacts[thread_id]
        return True
    
    def search_threads(self, limit: int = 100) -> List[Dict]:
        """Search threads sorted by updated_at descending."""
        threads = list(self._threads.values())
        threads.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return threads[:limit]
    
    def get_thread_messages(self, thread_id: str) -> List[Dict]:
        """Get all messages for a thread."""
        messages = self._messages.get(thread_id, [])
        # Return messages with role field only (standard format: user/assistant/system)
        return messages
    
    def set_thread_messages(self, thread_id: str, messages: List[Dict]) -> None:
        """Set all messages for a thread (replaces existing)."""
        # Use role field (standard format: user/assistant/system)
        # If role is not present, convert from type for backward compatibility
        normalized_messages = []
        for msg in messages:
            normalized_msg = {**msg}
            
            role = msg.get("role")
            if not role:
                # Backward compatibility: convert type to role
                type_to_role = {
                    "human": "user",
                    "ai": "assistant",
                    "assistant": "assistant",
                    "system": "system",
                    "tool": "tool",
                    "user": "user",
                }
                msg_type = msg.get("type", "user")
                normalized_msg["role"] = type_to_role.get(msg_type, "user")
            
            # Ensure role is in standard format
            if normalized_msg.get("role") not in ["user", "assistant", "system", "tool"]:
                role_mapping = {
                    "human": "user",
                    "ai": "assistant",
                }
                normalized_msg["role"] = role_mapping.get(normalized_msg.get("role"), "user")
            
            # Remove type field to avoid duplication
            if "type" in normalized_msg:
                del normalized_msg["type"]
            
            normalized_messages.append(normalized_msg)
        
        self._messages[thread_id] = normalized_messages
        if thread_id in self._threads:
            self._threads[thread_id]["updated_at"] = datetime.utcnow().isoformat()
    
    def get_thread_artifact(self, thread_id: str) -> Optional[Dict]:
        """Get artifact for a thread (backward compatibility - returns latest version only)."""
        return self.get_thread_artifact_latest(thread_id)
    
    def get_thread_artifact_latest(self, thread_id: str) -> Optional[Dict]:
        """Get the latest artifact version for a thread."""
        if thread_id not in self._artifacts or not self._artifacts[thread_id]:
            return None
        
        versions = self._artifacts[thread_id]
        if not versions:
            return None
        
        # Get the latest version (highest version_index)
        latest_index = max(versions.keys())
        return versions[latest_index]
    
    def get_thread_artifact_version(self, thread_id: str, version_index: int) -> Optional[Dict]:
        """Get a specific artifact version for a thread."""
        if thread_id not in self._artifacts:
            return None
        return self._artifacts[thread_id].get(version_index)
    
    def get_thread_artifact_metadata(self, thread_id: str) -> Optional[Dict]:
        """Get artifact metadata (version list, current_index, etc.) without full content."""
        if thread_id not in self._artifacts or not self._artifacts[thread_id]:
            return None
        
        version_indices = sorted(self._artifacts[thread_id].keys())
        latest_index = max(version_indices) if version_indices else None
        
        return {
            "version_indices": version_indices,
            "current_index": latest_index,
            "total_versions": len(version_indices),
        }
    
    def set_thread_artifact(self, thread_id: str, artifact: Dict) -> None:
        """Set artifact for a thread (saves each version separately)."""
        if thread_id not in self._artifacts:
            self._artifacts[thread_id] = {}
        
        # Extract contents array and currentIndex
        contents = artifact.get("contents", [])
        
        if not contents:
            # If no contents, save as a single version (backward compatibility)
            self._artifacts[thread_id][1] = artifact
        else:
            # Save each version separately
            for content in contents:
                version_index = content.get("index", 1)
                # Create a single-version artifact for this version
                version_artifact = {
                    "currentIndex": version_index,
                    "contents": [content],
                }
                self._artifacts[thread_id][version_index] = version_artifact
        
        if thread_id in self._threads:
            self._threads[thread_id]["updated_at"] = datetime.utcnow().isoformat()
    
    def delete_thread_artifact(self, thread_id: str) -> bool:
        """Delete artifact for a thread (all versions)."""
        if thread_id in self._artifacts:
            del self._artifacts[thread_id]
            return True
        return False

