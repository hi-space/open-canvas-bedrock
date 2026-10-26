"""Small metadata records in DynamoDB; exact document bytes remain on the mount."""
import hashlib
import json
import os
from pathlib import Path
from functools import lru_cache
import tempfile

import boto3
from fastapi import HTTPException


def atomic_bytes(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".canvas-write-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path: Path, value):
    atomic_bytes(path, json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


@lru_cache(maxsize=4)
def dynamodb(region):
    return boto3.client("dynamodb", region_name=region)


class Metadata:
    def __init__(self, root: Path):
        self.root = root
        self.local = os.environ.get("WORKSPACE_METADATA", "dynamodb") == "file"
        self.table = os.environ.get("WORKSPACE_TABLE_NAME", "canvas-writing-workspaces")

    def _path(self, namespace):
        return self.root / ".metadata" / (hashlib.sha256(namespace.encode()).hexdigest() + ".json")

    def _client(self):
        return dynamodb(os.environ.get("AWS_REGION", "ap-northeast-2"))

    def items(self, namespace, *, prefix=None, exclude_prefix=None):
        if self.local:
            path = self._path(namespace)
            values = json.loads(path.read_bytes()) if path.exists() else {}
            return {
                key: value for key, value in values.items()
                if (prefix is None or key.startswith(prefix))
                and (exclude_prefix is None or not key.startswith(exclude_prefix))
            }
        result = {}
        options = dict(
            TableName=self.table, KeyConditionExpression="#ns = :ns",
            ExpressionAttributeNames={"#ns": "namespace"},
            ExpressionAttributeValues={":ns": {"S": namespace}}, ConsistentRead=True,
        )
        if prefix is not None:
            options["ExpressionAttributeNames"]["#key"] = "key"
            options["KeyConditionExpression"] += " AND begins_with(#key, :prefix)"
            options["ExpressionAttributeValues"][":prefix"] = {"S": prefix}
        while True:
            page = self._client().query(**options)
            for item in page.get("Items", []):
                key = item["key"]["S"]
                # DynamoDB does not allow partition/sort keys in a query's
                # FilterExpression. Filter after querying and keep paginating
                # even when a whole page contains excluded source records.
                if exclude_prefix is None or not key.startswith(exclude_prefix):
                    result[key] = json.loads(item["workspaceData"]["S"])
            if not page.get("LastEvaluatedKey"):
                return result
            if prefix != "source:" and len(result) > 5000:
                raise HTTPException(503, "프로젝트 기록이 너무 많습니다. 관리자에게 문의해 주세요.")
            options["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def get(self, namespace, key):
        if self.local:
            return self.items(namespace).get(key)
        item = self._client().get_item(
            TableName=self.table, Key={"namespace": {"S": namespace}, "key": {"S": key}},
            ConsistentRead=True,
        ).get("Item")
        return json.loads(item["workspaceData"]["S"]) if item else None

    def put(self, namespace, key, value):
        if self.local:
            records = self.items(namespace)
            records[key] = value
            write_json(self._path(namespace), records)
        else:
            self._client().put_item(TableName=self.table, Item={
                "namespace": {"S": namespace}, "key": {"S": key},
                "workspaceData": {"S": json.dumps(value, ensure_ascii=False, separators=(",", ":"))},
            })

    def delete(self, namespace, key):
        if self.local:
            records = self.items(namespace)
            records.pop(key, None)
            write_json(self._path(namespace), records)
        else:
            self._client().delete_item(
                TableName=self.table, Key={"namespace": {"S": namespace}, "key": {"S": key}},
            )
