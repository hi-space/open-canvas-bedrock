"""Write source bodies before publishing them; retain legacy records for rollback."""
import hashlib
import logging
import re

from fastapi import HTTPException

from api.workspaces.persistence import atomic_bytes
from api.workspaces.files import now
from api.workspaces.jobs import job_is_stale
from core.source_catalog import (
    MAX_CATALOG_BYTES, SourceCatalog, encoded, entry_for, source_record, summary,
)

MAX_STORED_SOURCES = 2000
MAX_STORED_BYTES = 32 * 1024 * 1024
logger = logging.getLogger(__name__)


class SourceCapacityError(HTTPException):
    def __init__(self):
        super().__init__(422, "출처 보관 공간은 2,000개·32MiB까지입니다. 기존 자료 읽기와 문서 수정은 계속할 수 있습니다.")


class SourceLibrary:
    """Call mutations/snapshot under the existing project lock."""

    def __init__(self, files):
        self.files = files
        self.directory = files.internal / "source-library"

    def _write(self, kind, digest, body):
        target = self.files.safe(self.directory / kind / (digest + ".json"))
        if not target.exists():
            atomic_bytes(target, body)

    def _materialize(self, value):
        entry, body = entry_for(value)
        self._write("blobs", entry["version"], body)
        return entry

    def put(self, value):
        source = source_record(value)
        records = {item["id"]: item for item in self.records()}
        previous = records.get(source["id"])
        previous_size = len(encoded(source_record(previous))) if previous else 0
        size = len(encoded(source))
        total = sum(len(encoded(source_record(item))) for item in records.values())
        if (
            previous is None and len(records) >= MAX_STORED_SOURCES
            or total - previous_size + size > MAX_STORED_BYTES and size > previous_size
        ):
            raise SourceCapacityError()
        entry = self._materialize(source)
        # Keep this readable by the previous API image during rollout/rollback.
        # It is never returned in project summaries or sent to a model.
        self.files.metadata.put(self.files.namespace, "source:" + source["id"], {
            **source, "version": entry["version"], "excerptCharacters": entry["excerptCharacters"],
        })
        if previous is not None:
            self.collect_garbage()
        return summary(entry)

    def records(self):
        return list(self.files.metadata.items(self.files.namespace, prefix="source:").values())

    def summaries(self):
        results = []
        for value in self.records():
            source = source_record(value)
            results.append({
                "id": source["id"], "title": source["title"], "url": source["url"],
                "version": hashlib.sha256(encoded(source)).hexdigest(),
                "excerptCharacters": len(source.get("excerpt") or ""),
            })
        return results

    def read(self, source_id):
        source = self.files.metadata.get(self.files.namespace, "source:" + source_id)
        if source is None:
            raise HTTPException(404, "출처를 찾을 수 없습니다.")
        entry = self._materialize(source)
        return {**source_record(source), "version": entry["version"],
                "excerptCharacters": entry["excerptCharacters"]}

    def remove(self, source_id):
        # A new source may be added and deleted while a job fetches the same URL.
        # Keep this separate from ordinary project records and source membership.
        if self.files.metadata.get(self.files.namespace, "source:" + source_id) is None:
            return
        self.files.metadata.put(self.files.namespace + ":source-deletions", source_id, {"deletedAt": now()})
        self.files.metadata.delete(self.files.namespace, "source:" + source_id)
        self.collect_garbage()

    def removed_since(self, source_id, timestamp):
        deletion = self.files.metadata.get(self.files.namespace + ":source-deletions", source_id)
        return deletion is not None and deletion["deletedAt"] >= timestamp

    def snapshot(self, *, base=None, extra=(), sources=None):
        if base is None:
            entries = {}
            for value in self.records() if sources is None else sources:
                entry = self._materialize(value)
                entries[value["id"]] = entry
                if sources is None and value.get("version") != entry["version"]:
                    self.files.metadata.put(self.files.namespace, "source:" + value["id"], {
                        **source_record(value), "version": entry["version"],
                        "excerptCharacters": entry["excerptCharacters"],
                    })
        else:
            catalog = SourceCatalog(self.files.root, self.files.owner, self.files.workspace, base)
            entries = dict(catalog.entries)
        for value in extra:
            previous = entries.get(value["id"])
            if previous and previous["url"] != value["url"]:
                raise ValueError("Source identity changed.")
            entries[value["id"]] = self._materialize(value)
        return self._save_catalog(entries)

    def subset(self, snapshot, source_ids):
        catalog = SourceCatalog(self.files.root, self.files.owner, self.files.workspace, snapshot)
        return self._save_catalog({key: catalog.entries[key] for key in source_ids})

    def _save_catalog(self, entries):
        parts, size = [], 2
        for key in sorted(entries):
            part = encoded(entries[key])
            size += len(part) + bool(parts)
            if size > MAX_CATALOG_BYTES:
                raise HTTPException(422, "출처 검색 목록이 파일 크기 한도를 초과했습니다.")
            parts.append(part)
        body = b"[" + b",".join(parts) + b"]"
        digest = hashlib.sha256(body).hexdigest()
        self._write("catalogs", digest, body)
        return digest

    def collect_garbage(self):
        """Retain current sources, live job snapshots and retained proposal evidence."""
        if not self.directory.exists():
            return 0
        try:
            versions = {hashlib.sha256(encoded(source_record(value))).hexdigest() for value in self.records()}
            catalogs, inspect = set(), set()
            records = self.files.metadata.items(self.files.namespace, exclude_prefix="source:")
            oldest_active = now() + 1
            for key, value in records.items():
                if key.startswith("job:") and value["status"] in {"queued", "running"} and not job_is_stale(value, now()):
                    inspect.update(value.get("sourceSnapshots", []))
                    oldest_active = min(oldest_active, value["createdAt"])
                if key.startswith("proposal:"):
                    proposal = value
                    if "sourceVersions" not in value:
                        proposal = self.files.proposal(value["id"])
                    snapshot = proposal.get("sourceSnapshot")
                    if snapshot:
                        catalogs.add(snapshot)
                        if "sourceVersions" in proposal:
                            versions.update(proposal["sourceVersions"])
                        elif "sourceReads" in proposal:
                            versions.update(item["version"] for item in proposal["sourceReads"])
                        else:
                            inspect.add(snapshot)
            catalogs.update(inspect)
            for snapshot in inspect:
                catalog = SourceCatalog(self.files.root, self.files.owner, self.files.workspace, snapshot)
                versions.update(entry["version"] for entry in catalog.entries.values())
            if any(not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)
                   for value in versions | catalogs):
                raise ValueError("Invalid retained source version")
            removed = 0
            for kind, retained in (("blobs", versions), ("catalogs", catalogs)):
                directory = self.files.safe(self.directory / kind)
                if not directory.exists():
                    continue
                for path in directory.iterdir():
                    if re.fullmatch(r"[a-f0-9]{64}\.json", path.name) and path.stem not in retained:
                        self.files.safe(path).unlink()
                        removed += 1
            deletion_namespace = self.files.namespace + ":source-deletions"
            for key, value in self.files.metadata.items(deletion_namespace).items():
                if value["deletedAt"] < oldest_active:
                    self.files.metadata.delete(deletion_namespace, key)
            return removed
        except (OSError, ValueError, HTTPException, KeyError, TypeError):
            # Missing/corrupt retention information must never authorize deletion.
            logger.warning("Source cleanup deferred because retained references could not be verified.")
            return 0

