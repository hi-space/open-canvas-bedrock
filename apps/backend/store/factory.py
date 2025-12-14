"""
Factory function to create storage instances based on environment configuration.
"""
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from store.base import BaseStorage, BaseEntityStorage
from store.memory_storage import MemoryStorage, MemoryEntityStorage, MemoryThreadStorage
from store.dynamodb_storage import DynamoDBStorage, DynamoDBEntityStorage, DynamoDBThreadStorage
from store.thread_storage import BaseThreadStorage


def create_storage() -> BaseStorage:
    """Create a storage instance based on environment configuration.
    
    Environment variables:
        STORAGE_TYPE: "memory" or "dynamodb" (default: "memory")
        STORAGE_TABLE_NAME: DynamoDB table name (default: "open_canvas_store")
        AWS_DEFAULT_REGION: AWS region for DynamoDB (default: "us-east-1")
    
    Returns:
        BaseStorage instance
    """
    storage_type = os.getenv("STORAGE_TYPE", "memory").lower()
    
    if storage_type == "dynamodb":
        table_name = os.getenv("STORAGE_TABLE_NAME", "open_canvas_store")
        region_name = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        return DynamoDBStorage(table_name=table_name, region_name=region_name)
    else:
        # Default to memory storage
        return MemoryStorage()


def create_entity_storage() -> BaseEntityStorage:
    """Create an entity storage instance based on environment configuration.
    
    Environment variables:
        STORAGE_TYPE: "memory" or "dynamodb" (default: "memory")
        STORAGE_ENTITY_TABLE_NAME: DynamoDB table name for entities (default: "open_canvas_entities")
        AWS_DEFAULT_REGION: AWS region for DynamoDB (default: "us-east-1")
    
    Returns:
        BaseEntityStorage instance
    """
    storage_type = os.getenv("STORAGE_TYPE", "memory").lower()
    
    if storage_type == "dynamodb":
        table_name = os.getenv("STORAGE_ENTITY_TABLE_NAME", "open_canvas_entities")
        region_name = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        return DynamoDBEntityStorage(table_name=table_name, region_name=region_name)
    else:
        # Default to memory storage
        return MemoryEntityStorage()


def create_thread_storage() -> BaseThreadStorage:
    """Create a thread storage instance based on environment configuration.
    
    Environment variables:
        STORAGE_TYPE: "memory" or "dynamodb" (default: "memory")
        STORAGE_THREADS_TABLE_NAME: DynamoDB table name for threads (default: "open_canvas_threads")
        STORAGE_ARTIFACTS_TABLE_NAME: DynamoDB table name for artifacts (default: "open_canvas_thread_artifacts")
        AWS_DEFAULT_REGION: AWS region for DynamoDB (default: "us-east-1")
    
    Returns:
        BaseThreadStorage instance
    """
    storage_type = os.getenv("STORAGE_TYPE", "memory").lower()
    
    if storage_type == "dynamodb":
        threads_table = os.getenv("STORAGE_THREADS_TABLE_NAME", "open_canvas_threads")
        artifacts_table = os.getenv("STORAGE_ARTIFACTS_TABLE_NAME", "open_canvas_thread_artifacts")
        region_name = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        return DynamoDBThreadStorage(
            threads_table_name=threads_table,
            artifacts_table_name=artifacts_table,
            region_name=region_name
        )
    else:
        # Default to memory storage
        return MemoryThreadStorage()

