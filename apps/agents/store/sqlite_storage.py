"""
SQLite storage backend for persistent storage.
"""
import sqlite3
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
from store.base import BaseStorage, BaseEntityStorage


class SQLiteStorage(BaseStorage):
    """SQLite storage backend for key-value store."""
    
    def __init__(self, db_path: str = "store.db"):
        """Initialize SQLite storage.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        # Ensure directory exists
        db_file = Path(db_path)
        if db_file.parent != Path("."):
            db_file.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create store_items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS store_items (
                namespace TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (namespace, key)
            )
        """)
        
        # Create index for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_namespace_key 
            ON store_items(namespace, key)
        """)
        
        conn.commit()
        conn.close()
    
    def _get_namespace_key(self, namespace: List[str]) -> str:
        """Convert namespace list to a string key."""
        return "/".join(str(n) for n in namespace)
    
    def get_item(self, namespace: List[str], key: str) -> Optional[Dict[str, Any]]:
        """Get an item from the store."""
        namespace_key = self._get_namespace_key(namespace)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT value, updated_at 
            FROM store_items 
            WHERE namespace = ? AND key = ?
        """, (namespace_key, key))
        
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return None
        
        value_str, updated_at = row
        try:
            value = json.loads(value_str)
        except json.JSONDecodeError:
            value = value_str
        
        return {
            "value": value,
            "updatedAt": updated_at,
        }
    
    def put_item(self, namespace: List[str], key: str, value: Any) -> None:
        """Put an item into the store."""
        namespace_key = self._get_namespace_key(namespace)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        value_str = json.dumps(value) if not isinstance(value, str) else value
        updated_at = datetime.utcnow().isoformat()
        
        cursor.execute("""
            INSERT OR REPLACE INTO store_items (namespace, key, value, updated_at)
            VALUES (?, ?, ?, ?)
        """, (namespace_key, key, value_str, updated_at))
        
        conn.commit()
        conn.close()
    
    def delete_item(self, namespace: List[str], key: str) -> bool:
        """Delete an item from the store."""
        namespace_key = self._get_namespace_key(namespace)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM store_items 
            WHERE namespace = ? AND key = ?
        """, (namespace_key, key))
        
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return deleted
    
    def list_items(self, namespace: List[str], prefix: Optional[str] = None) -> List[str]:
        """List all keys in a namespace, optionally filtered by prefix."""
        namespace_key = self._get_namespace_key(namespace)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if prefix:
            cursor.execute("""
                SELECT key FROM store_items 
                WHERE namespace = ? AND key LIKE ?
            """, (namespace_key, f"{prefix}%"))
        else:
            cursor.execute("""
                SELECT key FROM store_items 
                WHERE namespace = ?
            """, (namespace_key,))
        
        keys = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        return keys


class SQLiteEntityStorage(BaseEntityStorage):
    """SQLite storage backend for entity storage."""
    
    def __init__(self, db_path: str = "store.db"):
        """Initialize SQLite entity storage.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create entities table (for assistants only, threads are normalized)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (entity_type, entity_id)
            )
        """)
        
        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_entity_type 
            ON entities(entity_type)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_updated_at 
            ON entities(updated_at)
        """)
        
        # Create normalized thread tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                thread_id TEXT PRIMARY KEY,
                metadata TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS thread_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                message_index INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                message_data TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES threads(thread_id) ON DELETE CASCADE,
                UNIQUE(thread_id, message_index)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS thread_artifacts (
                thread_id TEXT PRIMARY KEY,
                artifact_data TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES threads(thread_id) ON DELETE CASCADE
            )
        """)
        
        # Create indexes for threads
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_threads_updated_at 
            ON threads(updated_at)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_thread_messages_thread_id 
            ON thread_messages(thread_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_thread_messages_index 
            ON thread_messages(thread_id, message_index)
        """)
        
        conn.commit()
        conn.close()
    
    def create(self, entity_type: str, entity_id: str, data: Dict) -> Dict:
        """Create a new entity."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.utcnow().isoformat()
        data_str = json.dumps(data)
        
        cursor.execute("""
            INSERT INTO entities (entity_type, entity_id, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (entity_type, entity_id, data_str, now, now))
        
        conn.commit()
        conn.close()
        
        return {**data, "created_at": now, "updated_at": now}
    
    def get(self, entity_type: str, entity_id: str) -> Optional[Dict]:
        """Get an entity by ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT data, created_at, updated_at 
            FROM entities 
            WHERE entity_type = ? AND entity_id = ?
        """, (entity_type, entity_id))
        
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return None
        
        data_str, created_at, updated_at = row
        data = json.loads(data_str)
        data["created_at"] = created_at
        data["updated_at"] = updated_at
        
        return data
    
    def update(self, entity_type: str, entity_id: str, updates: Dict) -> Optional[Dict]:
        """Update an entity."""
        existing = self.get(entity_type, entity_id)
        if existing is None:
            return None
        
        # Merge updates (entities table is now only for assistants, not threads)
        updated_data = {**existing}
        for key, value in updates.items():
            if key == "config" and isinstance(value, dict) and isinstance(updated_data.get("config"), dict):
                updated_data["config"] = {**updated_data.get("config", {}), **value}
            elif key == "metadata" and isinstance(value, dict) and isinstance(updated_data.get("metadata"), dict):
                updated_data["metadata"] = {**updated_data.get("metadata", {}), **value}
            else:
                updated_data[key] = value
        
        updated_data["updated_at"] = datetime.utcnow().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        data_str = json.dumps(updated_data)
        cursor.execute("""
            UPDATE entities 
            SET data = ?, updated_at = ?
            WHERE entity_type = ? AND entity_id = ?
        """, (data_str, updated_data["updated_at"], entity_type, entity_id))
        
        conn.commit()
        conn.close()
        
        return updated_data
    
    def delete(self, entity_type: str, entity_id: str) -> bool:
        """Delete an entity."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM entities 
            WHERE entity_type = ? AND entity_id = ?
        """, (entity_type, entity_id))
        
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return deleted
    
    def search(self, entity_type: str, filters: Optional[Dict] = None, limit: int = 100) -> List[Dict]:
        """Search entities with optional filters."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT data, created_at, updated_at 
            FROM entities 
            WHERE entity_type = ?
            ORDER BY updated_at DESC
            LIMIT ?
        """, (entity_type, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        entities = []
        for row in rows:
            data_str, created_at, updated_at = row
            data = json.loads(data_str)
            data["created_at"] = created_at
            data["updated_at"] = updated_at
            
            # Apply filters if provided
            if filters:
                match = True
                for key, value in filters.items():
                    if key == "graph_id" and data.get("graph_id") != value:
                        match = False
                        break
                    elif key == "metadata":
                        if not isinstance(value, dict):
                            match = False
                            break
                        entity_metadata = data.get("metadata", {})
                        for meta_key, meta_value in value.items():
                            if entity_metadata.get(meta_key) != meta_value:
                                match = False
                                break
                        if not match:
                            break
                    else:
                        if data.get(key) != value:
                            match = False
                            break
                
                if not match:
                    continue
            
            entities.append(data)
        
        return entities


class SQLiteThreadStorage:
    """SQLite storage backend for normalized thread storage."""
    
    def __init__(self, db_path: str = "store.db"):
        """Initialize SQLite thread storage.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create normalized thread tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                thread_id TEXT PRIMARY KEY,
                metadata TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS thread_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                message_index INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                message_data TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES threads(thread_id) ON DELETE CASCADE,
                UNIQUE(thread_id, message_index)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS thread_artifacts (
                thread_id TEXT PRIMARY KEY,
                artifact_data TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES threads(thread_id) ON DELETE CASCADE
            )
        """)
        
        # Create indexes for threads
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_threads_updated_at 
            ON threads(updated_at)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_thread_messages_thread_id 
            ON thread_messages(thread_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_thread_messages_index 
            ON thread_messages(thread_id, message_index)
        """)
        
        conn.commit()
        conn.close()
    
    def create_thread(self, thread_id: str, metadata: Optional[Dict] = None) -> Dict:
        """Create a new thread."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.utcnow().isoformat()
        metadata_str = json.dumps(metadata or {})
        
        cursor.execute("""
            INSERT INTO threads (thread_id, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?)
        """, (thread_id, metadata_str, now, now))
        
        conn.commit()
        conn.close()
        
        return {
            "thread_id": thread_id,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }
    
    def get_thread(self, thread_id: str) -> Optional[Dict]:
        """Get thread metadata."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT metadata, created_at, updated_at 
            FROM threads 
            WHERE thread_id = ?
        """, (thread_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return None
        
        metadata_str, created_at, updated_at = row
        metadata = json.loads(metadata_str) if metadata_str else {}
        
        return {
            "thread_id": thread_id,
            "metadata": metadata,
            "created_at": created_at,
            "updated_at": updated_at,
        }
    
    def update_thread_metadata(self, thread_id: str, metadata: Dict) -> Optional[Dict]:
        """Update thread metadata."""
        existing = self.get_thread(thread_id)
        if existing is None:
            return None
        
        # Merge metadata
        updated_metadata = {**existing.get("metadata", {}), **metadata}
        updated_at = datetime.utcnow().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        metadata_str = json.dumps(updated_metadata)
        cursor.execute("""
            UPDATE threads 
            SET metadata = ?, updated_at = ?
            WHERE thread_id = ?
        """, (metadata_str, updated_at, thread_id))
        
        conn.commit()
        conn.close()
        
        return {
            "thread_id": thread_id,
            "metadata": updated_metadata,
            "created_at": existing.get("created_at"),
            "updated_at": updated_at,
        }
    
    def delete_thread(self, thread_id: str) -> bool:
        """Delete thread and all associated data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # CASCADE will delete messages and artifacts
        cursor.execute("""
            DELETE FROM threads 
            WHERE thread_id = ?
        """, (thread_id,))
        
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return deleted
    
    def search_threads(self, limit: int = 100) -> List[Dict]:
        """Search threads sorted by updated_at descending."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT thread_id, metadata, created_at, updated_at 
            FROM threads 
            ORDER BY updated_at DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        threads = []
        for row in rows:
            thread_id, metadata_str, created_at, updated_at = row
            metadata = json.loads(metadata_str) if metadata_str else {}
            threads.append({
                "thread_id": thread_id,
                "metadata": metadata,
                "created_at": created_at,
                "updated_at": updated_at,
            })
        
        return threads
    
    def get_thread_messages(self, thread_id: str) -> List[Dict]:
        """Get all messages for a thread."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT message_index, role, content, message_data 
            FROM thread_messages 
            WHERE thread_id = ?
            ORDER BY message_index ASC
        """, (thread_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        messages = []
        for row in rows:
            message_index, role, content, message_data_str = row
            
            message = {
                "role": role,  # Standard format: user/assistant/system
                "content": content,
            }
            if message_data_str:
                try:
                    message_data = json.loads(message_data_str)
                    message.update(message_data)
                except json.JSONDecodeError:
                    pass
            messages.append(message)
        
        return messages
    
    def set_thread_messages(self, thread_id: str, messages: List[Dict]) -> None:
        """Set all messages for a thread (replaces existing)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Delete existing messages
        cursor.execute("""
            DELETE FROM thread_messages 
            WHERE thread_id = ?
        """, (thread_id,))
        
        # Insert new messages
        now = datetime.utcnow().isoformat()
        for index, msg in enumerate(messages):
            # Use role field (standard format: user/assistant/system)
            # If role is not present, convert from type for backward compatibility
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
                role = type_to_role.get(msg_type, "user")
            
            # Ensure role is in standard format
            if role not in ["user", "assistant", "system", "tool"]:
                # Normalize role
                role_mapping = {
                    "human": "user",
                    "ai": "assistant",
                }
                role = role_mapping.get(role, "user")
            
            content = msg.get("content", "")
            
            # Store additional fields in message_data (excluding role and type)
            message_data = {k: v for k, v in msg.items() if k not in ["role", "type", "content"]}
            message_data_str = json.dumps(message_data) if message_data else None
            
            cursor.execute("""
                INSERT INTO thread_messages (thread_id, message_index, role, content, message_data, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (thread_id, index, role, content, message_data_str, now))
        
        # Update thread updated_at
        cursor.execute("""
            UPDATE threads 
            SET updated_at = ?
            WHERE thread_id = ?
        """, (now, thread_id))
        
        conn.commit()
        conn.close()
    
    def get_thread_artifact(self, thread_id: str) -> Optional[Dict]:
        """Get artifact for a thread."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT artifact_data 
            FROM thread_artifacts 
            WHERE thread_id = ?
        """, (thread_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return None
        
        artifact_str = row[0]
        try:
            return json.loads(artifact_str)
        except json.JSONDecodeError:
            return None
    
    def set_thread_artifact(self, thread_id: str, artifact: Dict) -> None:
        """Set artifact for a thread."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        artifact_str = json.dumps(artifact)
        updated_at = datetime.utcnow().isoformat()
        
        cursor.execute("""
            INSERT OR REPLACE INTO thread_artifacts (thread_id, artifact_data, updated_at)
            VALUES (?, ?, ?)
        """, (thread_id, artifact_str, updated_at))
        
        # Update thread updated_at
        cursor.execute("""
            UPDATE threads 
            SET updated_at = ?
            WHERE thread_id = ?
        """, (updated_at, thread_id))
        
        conn.commit()
        conn.close()
    
    def delete_thread_artifact(self, thread_id: str) -> bool:
        """Delete artifact for a thread."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM thread_artifacts 
            WHERE thread_id = ?
        """, (thread_id,))
        
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return deleted

