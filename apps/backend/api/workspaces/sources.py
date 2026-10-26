"""Write source bodies before publishing them; retain legacy records for rollback."""
import hashlib

from fastapi import HTTPException

from api.workspaces.persistence import atomic_bytes
from api.workspaces.files import now
from core.source_catalog import (
    MAX_CATALOG_BYTES, SourceCatalog, encoded, entry_for, source_record, summary,
)


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
        entry = self._materialize(source)
        # Keep this readable by the previous API image during rollout/rollback.
        # It is never returned in project summaries or sent to a model.
        self.files.metadata.put(self.files.namespace, "source:" + source["id"], {
            **source, "version": entry["version"], "excerptCharacters": entry["excerptCharacters"],
        })
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
        self.files.metadata.put(self.files.namespace + ":source-deletions", source_id, {"deletedAt": now()})
        self.files.metadata.delete(self.files.namespace, "source:" + source_id)

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
        body = encoded([entries[key] for key in sorted(entries)])
        if len(body) > MAX_CATALOG_BYTES:
            raise HTTPException(422, "출처 검색 목록이 파일 크기 한도를 초과했습니다.")
        digest = hashlib.sha256(body).hexdigest()
        self._write("catalogs", digest, body)
        return digest

