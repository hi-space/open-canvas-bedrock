"""
DynamoDB storage backend for persistent storage.
"""
import json
import os
import sys
from typing import Dict, Any, Optional, List
from datetime import datetime
from store.base import BaseStorage, BaseEntityStorage

try:
    import boto3
    from boto3.dynamodb.conditions import Key, Attr
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


class DynamoDBStorage(BaseStorage):
    """DynamoDB storage backend for key-value store."""
    
    def __init__(self, table_name: str = "open_canvas_store", region_name: Optional[str] = None):
        """Initialize DynamoDB storage.
        
        Args:
            table_name: Name of the DynamoDB table
            region_name: AWS region name (defaults to AWS_DEFAULT_REGION env var)
        """
        if not BOTO3_AVAILABLE:
            raise ImportError("boto3 is required for DynamoDB storage. Install it with: pip install boto3")
        
        self.table_name = table_name
        self.region_name = region_name or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        
        # Initialize DynamoDB client
        self.dynamodb = boto3.resource("dynamodb", region_name=self.region_name)
        self.table = self.dynamodb.Table(table_name)
        
        self._init_table()
    
    def _init_table(self):
        """Initialize DynamoDB table if it doesn't exist."""
        try:
            # Check if table exists
            self.table.meta.client.describe_table(TableName=self.table_name)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                # Table doesn't exist, create it
                self._create_table()
            elif error_code in ["UnrecognizedClientException", "InvalidClientTokenId", "AccessDeniedException"]:
                # AWS credentials issue - log warning but don't fail
                import warnings
                warnings.warn(
                    f"DynamoDB credentials issue: {error_code}. "
                    "Table operations may fail. Please check AWS credentials.",
                    UserWarning
                )
            else:
                raise
    
    def _create_table(self):
        """Create DynamoDB table."""
        try:
            self.dynamodb.create_table(
                TableName=self.table_name,
                KeySchema=[
                    {"AttributeName": "namespace", "KeyType": "HASH"},
                    {"AttributeName": "key", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "namespace", "AttributeType": "S"},
                    {"AttributeName": "key", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            # Wait for table to be created
            self.table.wait_until_exists()
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceInUseException":
                raise
    
    def _get_namespace_key(self, namespace: List[str]) -> str:
        """Convert namespace list to a string key."""
        return "/".join(str(n) for n in namespace)
    
    def get_item(self, namespace: List[str], key: str) -> Optional[Dict[str, Any]]:
        """Get an item from the store."""
        namespace_key = self._get_namespace_key(namespace)
        
        try:
            response = self.table.get_item(
                Key={
                    "namespace": namespace_key,
                    "key": key,
                }
            )
            
            if "Item" not in response:
                return None
            
            item = response["Item"]
            value_str = item.get("value")
            
            try:
                value = json.loads(value_str) if isinstance(value_str, str) else value_str
            except (json.JSONDecodeError, TypeError):
                value = value_str
            
            return {
                "value": value,
                "updatedAt": item.get("updated_at"),
            }
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
    
    def put_item(self, namespace: List[str], key: str, value: Any) -> None:
        """Put an item into the store."""
        namespace_key = self._get_namespace_key(namespace)
        updated_at = datetime.utcnow().isoformat()
        
        value_str = json.dumps(value) if not isinstance(value, str) else value
        
        try:
            self.table.put_item(
                Item={
                    "namespace": namespace_key,
                    "key": key,
                    "value": value_str,
                    "updated_at": updated_at,
                }
            )
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
    
    def delete_item(self, namespace: List[str], key: str) -> bool:
        """Delete an item from the store."""
        namespace_key = self._get_namespace_key(namespace)
        
        try:
            response = self.table.delete_item(
                Key={
                    "namespace": namespace_key,
                    "key": key,
                },
                ReturnValues="ALL_OLD",
            )
            
            return "Attributes" in response
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
    
    def list_items(self, namespace: List[str], prefix: Optional[str] = None) -> List[str]:
        """List all keys in a namespace, optionally filtered by prefix."""
        namespace_key = self._get_namespace_key(namespace)
        
        try:
            if prefix:
                response = self.table.query(
                    KeyConditionExpression=Key("namespace").eq(namespace_key),
                    FilterExpression=Attr("key").begins_with(prefix),
                )
            else:
                response = self.table.query(
                    KeyConditionExpression=Key("namespace").eq(namespace_key),
                )
            
            return [item["key"] for item in response.get("Items", [])]
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")


class DynamoDBEntityStorage(BaseEntityStorage):
    """DynamoDB storage backend for entity storage."""
    
    def __init__(self, table_name: str = "open_canvas_entities", region_name: Optional[str] = None):
        """Initialize DynamoDB entity storage.
        
        Args:
            table_name: Name of the DynamoDB table
            region_name: AWS region name (defaults to AWS_DEFAULT_REGION env var)
        """
        if not BOTO3_AVAILABLE:
            raise ImportError("boto3 is required for DynamoDB storage. Install it with: pip install boto3")
        
        self.table_name = table_name
        self.region_name = region_name or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        
        # Initialize DynamoDB client
        self.dynamodb = boto3.resource("dynamodb", region_name=self.region_name)
        self.table = self.dynamodb.Table(table_name)
        
        self._init_table()
    
    def _init_table(self):
        """Initialize DynamoDB table if it doesn't exist."""
        try:
            # Check if table exists
            self.table.meta.client.describe_table(TableName=self.table_name)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                # Table doesn't exist, create it
                self._create_table()
            elif error_code in ["UnrecognizedClientException", "InvalidClientTokenId", "AccessDeniedException"]:
                # AWS credentials issue - log warning but don't fail
                import warnings
                warnings.warn(
                    f"DynamoDB credentials issue: {error_code}. "
                    "Table operations may fail. Please check AWS credentials.",
                    UserWarning
                )
            else:
                raise
    
    def _create_table(self):
        """Create DynamoDB table."""
        try:
            self.dynamodb.create_table(
                TableName=self.table_name,
                KeySchema=[
                    {"AttributeName": "entity_type", "KeyType": "HASH"},
                    {"AttributeName": "entity_id", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "entity_type", "AttributeType": "S"},
                    {"AttributeName": "entity_id", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            # Wait for table to be created
            self.table.wait_until_exists()
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceInUseException":
                raise
    
    def create(self, entity_type: str, entity_id: str, data: Dict) -> Dict:
        """Create a new entity."""
        now = datetime.utcnow().isoformat()
        data_with_timestamps = {**data, "created_at": now, "updated_at": now}
        data_str = json.dumps(data_with_timestamps)
        
        try:
            self.table.put_item(
                Item={
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "data": data_str,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
        
        return data_with_timestamps
    
    def get(self, entity_type: str, entity_id: str) -> Optional[Dict]:
        """Get an entity by ID."""
        try:
            response = self.table.get_item(
                Key={
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                }
            )
            
            if "Item" not in response:
                return None
            
            item = response["Item"]
            data_str = item.get("data")
            data = json.loads(data_str) if isinstance(data_str, str) else data_str
            data["created_at"] = item.get("created_at")
            data["updated_at"] = item.get("updated_at")
            
            return data
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
    
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
        data_str = json.dumps(updated_data)
        
        try:
            self.table.put_item(
                Item={
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "data": data_str,
                    "created_at": existing.get("created_at"),
                    "updated_at": updated_data["updated_at"],
                }
            )
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
        
        return updated_data
    
    def delete(self, entity_type: str, entity_id: str) -> bool:
        """Delete an entity."""
        try:
            response = self.table.delete_item(
                Key={
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                },
                ReturnValues="ALL_OLD",
            )
            
            return "Attributes" in response
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
    
    def search(self, entity_type: str, filters: Optional[Dict] = None, limit: int = 100) -> List[Dict]:
        """Search entities with optional filters."""
        try:
            # Query all entities of this type with pagination
            entities = []
            last_evaluated_key = None
            
            # Fetch all items (with pagination) before filtering
            # This ensures we get all matching items even after filtering
            while True:
                query_params = {
                    "KeyConditionExpression": Key("entity_type").eq(entity_type),
                }
                
                if last_evaluated_key:
                    query_params["ExclusiveStartKey"] = last_evaluated_key
                
                response = self.table.query(**query_params)
                
                items_count = len(response.get("Items", []))
                print(f"DynamoDB search: entity_type={entity_type}, fetched {items_count} items", file=sys.stderr, flush=True)
                
                for item in response.get("Items", []):
                    data_str = item.get("data")
                    data = json.loads(data_str) if isinstance(data_str, str) else data_str
                    data["created_at"] = item.get("created_at")
                    data["updated_at"] = item.get("updated_at")
                    
                    # Apply filters if provided
                    if filters:
                        match = True
                        for key, value in filters.items():
                            if key == "graph_id" and data.get("graph_id") != value:
                                print(f"  Filter mismatch: graph_id - expected {value}, got {data.get('graph_id')}", file=sys.stderr, flush=True)
                                match = False
                                break
                            elif key == "metadata":
                                if not isinstance(value, dict):
                                    match = False
                                    break
                                entity_metadata = data.get("metadata", {})
                                print(f"  Checking metadata filter: filter={value}, entity_metadata={entity_metadata}", file=sys.stderr, flush=True)
                                for meta_key, meta_value in value.items():
                                    entity_meta_value = entity_metadata.get(meta_key)
                                    # If metadata key doesn't exist in entity, treat as match (for backward compatibility)
                                    # This allows existing data without user_id to be matched
                                    if meta_key not in entity_metadata:
                                        print(f"  Metadata key '{meta_key}' not found in entity, treating as match (backward compatibility)", file=sys.stderr, flush=True)
                                        continue
                                    if entity_meta_value != meta_value:
                                        print(f"  Filter mismatch: metadata.{meta_key} - expected {meta_value}, got {entity_meta_value}", file=sys.stderr, flush=True)
                                        match = False
                                        break
                                if not match:
                                    break
                            else:
                                if data.get(key) != value:
                                    print(f"  Filter mismatch: {key} - expected {value}, got {data.get(key)}", file=sys.stderr, flush=True)
                                    match = False
                                    break
                        
                        if not match:
                            continue
                        else:
                            print(f"  Entity passed filters: assistant_id={data.get('assistant_id')}, name={data.get('name')}", file=sys.stderr, flush=True)
                    
                    entities.append(data)
                
                # Check if there are more items to fetch
                last_evaluated_key = response.get("LastEvaluatedKey")
                if not last_evaluated_key:
                    break
                
                # Stop if we have enough items (after filtering)
                if len(entities) >= limit:
                    break
            
            # Sort by updated_at descending
            entities.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            
            print(f"DynamoDB search: entity_type={entity_type}, filters={filters}, returning {len(entities)} entities", file=sys.stderr, flush=True)
            
            return entities[:limit]
        except ClientError as e:
            print(f"DynamoDB search error: {str(e)}", file=sys.stderr, flush=True)
            raise Exception(f"DynamoDB error: {str(e)}")
        except Exception as e:
            print(f"DynamoDB search unexpected error: {str(e)}", file=sys.stderr, flush=True)
            raise


class DynamoDBThreadStorage:
    """DynamoDB storage backend for normalized thread storage."""
    
    def __init__(self, threads_table_name: str = "open_canvas_threads", 
                 messages_table_name: str = "open_canvas_thread_messages",
                 artifacts_table_name: str = "open_canvas_thread_artifacts",
                 region_name: Optional[str] = None):
        """Initialize DynamoDB thread storage.
        
        Args:
            threads_table_name: Name of the threads table
            messages_table_name: Name of the messages table
            artifacts_table_name: Name of the artifacts table
            region_name: AWS region name (defaults to AWS_DEFAULT_REGION env var)
        """
        if not BOTO3_AVAILABLE:
            raise ImportError("boto3 is required for DynamoDB storage. Install it with: pip install boto3")
        
        self.threads_table_name = threads_table_name
        self.messages_table_name = messages_table_name
        self.artifacts_table_name = artifacts_table_name
        self.region_name = region_name or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        
        # Initialize DynamoDB client
        self.dynamodb = boto3.resource("dynamodb", region_name=self.region_name)
        self.threads_table = self.dynamodb.Table(threads_table_name)
        self.messages_table = self.dynamodb.Table(messages_table_name)
        self.artifacts_table = self.dynamodb.Table(artifacts_table_name)
        
        self._init_tables()
    
    def _init_tables(self):
        """Initialize DynamoDB tables if they don't exist."""
        for table_name, table in [
            (self.threads_table_name, self.threads_table),
            (self.messages_table_name, self.messages_table),
            (self.artifacts_table_name, self.artifacts_table),
        ]:
            try:
                table.meta.client.describe_table(TableName=table_name)
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code == "ResourceNotFoundException":
                    self._create_table(table_name, table)
                elif error_code in ["UnrecognizedClientException", "InvalidClientTokenId", "AccessDeniedException"]:
                    import warnings
                    warnings.warn(
                        f"DynamoDB credentials issue: {error_code}. "
                        "Table operations may fail. Please check AWS credentials.",
                        UserWarning
                    )
                else:
                    raise
    
    def _create_table(self, table_name: str, table):
        """Create DynamoDB table."""
        try:
            if table_name == self.threads_table_name:
                # Threads table: thread_id as partition key
                self.dynamodb.create_table(
                    TableName=table_name,
                    KeySchema=[{"AttributeName": "thread_id", "KeyType": "HASH"}],
                    AttributeDefinitions=[{"AttributeName": "thread_id", "AttributeType": "S"}],
                    BillingMode="PAY_PER_REQUEST",
                )
            elif table_name == self.messages_table_name:
                # Messages table: thread_id as partition key, message_index as sort key
                self.dynamodb.create_table(
                    TableName=table_name,
                    KeySchema=[
                        {"AttributeName": "thread_id", "KeyType": "HASH"},
                        {"AttributeName": "message_index", "KeyType": "RANGE"},
                    ],
                    AttributeDefinitions=[
                        {"AttributeName": "thread_id", "AttributeType": "S"},
                        {"AttributeName": "message_index", "AttributeType": "N"},
                    ],
                    BillingMode="PAY_PER_REQUEST",
                )
            elif table_name == self.artifacts_table_name:
                # Artifacts table: thread_id as partition key, version_index as sort key
                self.dynamodb.create_table(
                    TableName=table_name,
                    KeySchema=[
                        {"AttributeName": "thread_id", "KeyType": "HASH"},
                        {"AttributeName": "version_index", "KeyType": "RANGE"},
                    ],
                    AttributeDefinitions=[
                        {"AttributeName": "thread_id", "AttributeType": "S"},
                        {"AttributeName": "version_index", "AttributeType": "N"},
                    ],
                    BillingMode="PAY_PER_REQUEST",
                )
            
            table.wait_until_exists()
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceInUseException":
                raise
    
    def create_thread(self, thread_id: str, metadata: Optional[Dict] = None) -> Dict:
        """Create a new thread."""
        now = datetime.utcnow().isoformat()
        metadata_str = json.dumps(metadata or {})
        
        try:
            self.threads_table.put_item(
                Item={
                    "thread_id": thread_id,
                    "metadata": metadata_str,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
        
        return {
            "thread_id": thread_id,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }
    
    def get_thread(self, thread_id: str) -> Optional[Dict]:
        """Get thread metadata."""
        try:
            response = self.threads_table.get_item(
                Key={"thread_id": thread_id}
            )
            
            if "Item" not in response:
                return None
            
            item = response["Item"]
            metadata_str = item.get("metadata", "{}")
            metadata = json.loads(metadata_str) if isinstance(metadata_str, str) else metadata_str
            
            return {
                "thread_id": thread_id,
                "metadata": metadata,
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
            }
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
    
    def update_thread_metadata(self, thread_id: str, metadata: Dict) -> Optional[Dict]:
        """Update thread metadata."""
        existing = self.get_thread(thread_id)
        if existing is None:
            return None
        
        updated_metadata = {**existing.get("metadata", {}), **metadata}
        updated_at = datetime.utcnow().isoformat()
        metadata_str = json.dumps(updated_metadata)
        
        try:
            self.threads_table.put_item(
                Item={
                    "thread_id": thread_id,
                    "metadata": metadata_str,
                    "created_at": existing.get("created_at"),
                    "updated_at": updated_at,
                }
            )
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
        
        return {
            "thread_id": thread_id,
            "metadata": updated_metadata,
            "created_at": existing.get("created_at"),
            "updated_at": updated_at,
        }
    
    def delete_thread(self, thread_id: str) -> bool:
        """Delete thread and all associated data."""
        try:
            # Delete messages
            messages = self.get_thread_messages(thread_id)
            for msg in messages:
                # Messages are deleted by querying and deleting individually
                # For efficiency, we'll delete all messages in batch
                pass
            
            # Delete all messages
            response = self.messages_table.query(
                KeyConditionExpression=Key("thread_id").eq(thread_id)
            )
            for item in response.get("Items", []):
                self.messages_table.delete_item(
                    Key={
                        "thread_id": thread_id,
                        "message_index": item["message_index"],
                    }
                )
            
            # Delete artifact
            self.artifacts_table.delete_item(
                Key={"thread_id": thread_id}
            )
            
            # Delete thread
            response = self.threads_table.delete_item(
                Key={"thread_id": thread_id},
                ReturnValues="ALL_OLD",
            )
            
            return "Attributes" in response
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
    
    def search_threads(self, limit: int = 100) -> List[Dict]:
        """Search threads sorted by updated_at descending."""
        try:
            # Scan all threads (DynamoDB doesn't support sorting in query)
            response = self.threads_table.scan(Limit=limit * 2)  # Get more to sort
            
            threads = []
            for item in response.get("Items", []):
                metadata_str = item.get("metadata", "{}")
                metadata = json.loads(metadata_str) if isinstance(metadata_str, str) else metadata_str
                threads.append({
                    "thread_id": item["thread_id"],
                    "metadata": metadata,
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                })
            
            # Sort by updated_at descending
            threads.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return threads[:limit]
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
    
    def get_thread_messages(self, thread_id: str) -> List[Dict]:
        """Get all messages for a thread."""
        try:
            response = self.messages_table.query(
                KeyConditionExpression=Key("thread_id").eq(thread_id),
                ScanIndexForward=True,  # Sort by message_index ascending
            )
            
            messages = []
            for item in response.get("Items", []):
                message = {
                    "role": item.get("role"),  # Standard format: user/assistant/system
                    "content": item.get("content"),
                }
                message_data_str = item.get("message_data")
                if message_data_str:
                    try:
                        message_data = json.loads(message_data_str) if isinstance(message_data_str, str) else message_data_str
                        message.update(message_data)
                    except (json.JSONDecodeError, TypeError):
                        pass
                messages.append(message)
            
            return messages
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
    
    def set_thread_messages(self, thread_id: str, messages: List[Dict]) -> None:
        """Set all messages for a thread (replaces existing)."""
        try:
            # Delete existing messages
            existing = self.messages_table.query(
                KeyConditionExpression=Key("thread_id").eq(thread_id)
            )
            for item in existing.get("Items", []):
                self.messages_table.delete_item(
                    Key={
                        "thread_id": thread_id,
                        "message_index": item["message_index"],
                    }
                )
            
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
                message_data = {k: v for k, v in msg.items() if k not in ["role", "type", "content"]}
                message_data_str = json.dumps(message_data) if message_data else None
                
                self.messages_table.put_item(
                    Item={
                        "thread_id": thread_id,
                        "message_index": index,
                        "role": role,
                        "content": content,
                        "message_data": message_data_str,
                        "created_at": now,
                    }
                )
            
            # Update thread updated_at
            self.update_thread_metadata(thread_id, {})
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
    
    def get_thread_artifact(self, thread_id: str) -> Optional[Dict]:
        """Get artifact for a thread (backward compatibility - returns latest version only)."""
        return self.get_thread_artifact_latest(thread_id)
    
    def get_thread_artifact_latest(self, thread_id: str) -> Optional[Dict]:
        """Get the latest artifact version for a thread."""
        try:
            # Query all versions and get the latest one
            response = self.artifacts_table.query(
                KeyConditionExpression=Key("thread_id").eq(thread_id),
                ScanIndexForward=False,  # Sort descending by version_index
                Limit=1,
            )
            
            if not response.get("Items"):
                return None
            
            item = response["Items"][0]
            artifact_str = item.get("artifact_data")
            try:
                artifact = json.loads(artifact_str) if isinstance(artifact_str, str) else artifact_str
                # Return in the old format for backward compatibility
                # If it's already in the old format (with contents array), return as is
                if isinstance(artifact, dict) and "contents" in artifact:
                    return artifact
                # Otherwise, wrap it in the expected format
                return artifact
            except (json.JSONDecodeError, TypeError):
                return None
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
    
    def get_thread_artifact_version(self, thread_id: str, version_index: int) -> Optional[Dict]:
        """Get a specific artifact version for a thread."""
        try:
            response = self.artifacts_table.get_item(
                Key={
                    "thread_id": thread_id,
                    "version_index": version_index,
                }
            )
            
            if "Item" not in response:
                return None
            
            item = response["Item"]
            artifact_str = item.get("artifact_data")
            try:
                artifact = json.loads(artifact_str) if isinstance(artifact_str, str) else artifact_str
                return artifact
            except (json.JSONDecodeError, TypeError):
                return None
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
    
    def get_thread_artifact_metadata(self, thread_id: str) -> Optional[Dict]:
        """Get artifact metadata (version list, current_index, etc.) without full content."""
        try:
            # Query all versions
            response = self.artifacts_table.query(
                KeyConditionExpression=Key("thread_id").eq(thread_id),
                ScanIndexForward=True,  # Sort ascending by version_index
                ProjectionExpression="version_index, updated_at",
            )
            
            if not response.get("Items"):
                return None
            
            version_indices = sorted([item["version_index"] for item in response["Items"]])
            latest_index = max(version_indices) if version_indices else None
            
            return {
                "version_indices": version_indices,
                "current_index": latest_index,
                "total_versions": len(version_indices),
            }
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
    
    def set_thread_artifact(self, thread_id: str, artifact: Dict) -> None:
        """Set artifact for a thread (saves each version separately)."""
        try:
            # Extract contents array and currentIndex
            contents = artifact.get("contents", [])
            current_index = artifact.get("currentIndex")
            
            if not contents:
                # If no contents, save as a single version (backward compatibility)
                artifact_str = json.dumps(artifact)
                updated_at = datetime.utcnow().isoformat()
                
                self.artifacts_table.put_item(
                    Item={
                        "thread_id": thread_id,
                        "version_index": 1,
                        "artifact_data": artifact_str,
                        "updated_at": updated_at,
                    }
                )
            else:
                # Save each version separately
                updated_at = datetime.utcnow().isoformat()
                
                for content in contents:
                    version_index = content.get("index", 1)
                    # Create a single-version artifact for this version
                    version_artifact = {
                        "currentIndex": version_index,
                        "contents": [content],
                    }
                    artifact_str = json.dumps(version_artifact)
                    
                    self.artifacts_table.put_item(
                        Item={
                            "thread_id": thread_id,
                            "version_index": version_index,
                            "artifact_data": artifact_str,
                            "updated_at": updated_at,
                        }
                    )
            
            # Update thread updated_at
            self.update_thread_metadata(thread_id, {})
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")
    
    def delete_thread_artifact(self, thread_id: str) -> bool:
        """Delete artifact for a thread (all versions)."""
        try:
            # Query all versions
            response = self.artifacts_table.query(
                KeyConditionExpression=Key("thread_id").eq(thread_id)
            )
            
            deleted_count = 0
            for item in response.get("Items", []):
                self.artifacts_table.delete_item(
                    Key={
                        "thread_id": thread_id,
                        "version_index": item["version_index"],
                    }
                )
                deleted_count += 1
            
            return deleted_count > 0
        except ClientError as e:
            raise Exception(f"DynamoDB error: {str(e)}")

