"""Immutable, project-scoped source snapshots and bounded evidence reads.

The catalog is trusted application data, not model input. Only list/search results
and explicitly read passages cross the model boundary.
"""
from collections import Counter
from bisect import bisect_left
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import unicodedata

from api.writing.models import WritingSource


MAX_CATALOG_BYTES = 64 * 1024 * 1024
MAX_SOURCE_BYTES = 256 * 1024
MAX_EVIDENCE_SOURCES = 50
MAX_EVIDENCE_CHARS = 100000
MAX_READ_CHARS = 8000
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
_HASH = re.compile(r"^[a-f0-9]{64}$")
_WORDS = re.compile(r"[^\W_]+", re.UNICODE)
_KOREAN = re.compile(r"[가-힣]+")
_STOP = {
    "the", "and", "for", "with", "from", "this", "that", "are", "was", "how",
    "what", "why", "into", "about", "please", "https", "http", "com",
    "내용", "문서", "자료", "설명", "추가", "대한", "위한", "해주세요", "해줘",
}


def encoded(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def terms(text: str) -> set[str]:
    words = {word for word in _WORDS.findall(normalized(text)) if 1 < len(word) <= 80}
    result = words - _STOP
    # Korean particles need not match the query's particles. Bigrams also make
    # a query such as "오토스케일" find "오토스케일링".
    for word in tuple(result):
        if _KOREAN.fullmatch(word):
            result.update(word[index:index + 2] for index in range(len(word) - 1))
    return result - _STOP


def source_record(value: dict) -> dict:
    return WritingSource.model_validate(value).model_dump(exclude_none=True)


def entry_for(value: dict) -> tuple[dict, bytes]:
    source = source_record(value)
    body = encoded(source)
    entry = {
        "id": source["id"], "title": source["title"], "url": source["url"],
        "version": hashlib.sha256(body).hexdigest(),
        "excerptCharacters": len(source.get("excerpt") or ""),
        "searchTerms": sorted(terms(" ".join([
            source["title"], source["url"], source.get("excerpt") or "",
        ]))),
    }
    return entry, body


def summary(entry: dict) -> dict:
    return {key: entry[key] for key in ("id", "title", "url", "version", "excerptCharacters")}


def read_project_json(root, owner: str, workspace: str, kind: str, digest: str, maximum: int):
    """Anchor every path component with dir_fd; no model-controlled path exists."""
    if (
        not _HASH.fullmatch(owner) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", workspace)
        or kind not in {"catalogs", "blobs"} or not _HASH.fullmatch(digest)
    ):
        raise ValueError("Invalid project source snapshot.")
    descriptor = None
    file_descriptor = None
    try:
        descriptor = os.open(Path(root), _DIRECTORY_FLAGS)
        for component in (owner, workspace, ".canvas", "source-library", kind):
            child = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        file_descriptor = os.open(digest + ".json", _FILE_FLAGS, dir_fd=descriptor)
        details = os.fstat(file_descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_size > maximum:
            raise ValueError("The source snapshot exceeds its file limit.")
        with os.fdopen(file_descriptor, "rb") as stream:
            file_descriptor = None
            body = stream.read(maximum + 1)
        if len(body) > maximum or hashlib.sha256(body).hexdigest() != digest:
            raise ValueError("Source snapshot version integrity check failed.")
        return json.loads(body)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("The project source snapshot is unavailable.") from error
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if descriptor is not None:
            os.close(descriptor)


class SourceCatalog:
    def __init__(self, root, owner: str, workspace: str, snapshot: str | None = None, sources=()):
        self.root, self.owner, self.workspace = root, owner, workspace
        self.snapshot = snapshot
        self._inline = {}
        if snapshot:
            entries = read_project_json(root, owner, workspace, "catalogs", snapshot, MAX_CATALOG_BYTES)
            if not isinstance(entries, list):
                raise ValueError("Invalid source catalog.")
        else:
            entries = []
            for source in sources:
                entry, _ = entry_for(source)
                entries.append(entry)
                self._inline[entry["id"]] = source_record(source)
        self.entries = {}
        for entry in entries:
            if not isinstance(entry, dict) or not _HASH.fullmatch(str(entry.get("version", ""))):
                raise ValueError("Invalid source catalog entry.")
            source_record(entry)
            if (
                type(entry.get("excerptCharacters")) is not int
                or not 0 <= entry["excerptCharacters"] <= 20000
                or not isinstance(entry.get("searchTerms"), list)
                or any(not isinstance(term, str) for term in entry["searchTerms"])
                or entry["id"] in self.entries
            ):
                raise ValueError("Invalid source catalog entry.")
            self.entries[entry["id"]] = entry
        self._term_sets = {key: set(item["searchTerms"]) for key, item in self.entries.items()}

    def add_inline(self, value: dict):
        entry, _ = entry_for(value)
        previous = self.entries.get(entry["id"])
        if previous and previous["url"] != entry["url"]:
            raise ValueError("Source identity changed.")
        self.entries[entry["id"]] = entry
        self._inline[entry["id"]] = source_record(value)
        self._term_sets[entry["id"]] = set(entry["searchTerms"])

    def list(self, offset=0, limit=20) -> dict:
        values = list(self.entries.values())
        return self._page(values, offset, limit)

    @staticmethod
    def _page(values, offset, limit):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("Use a valid source page and at most 50 results.")
        return {
            "sources": [summary(entry) for entry in values[offset:offset + limit]],
            "total": len(values),
            "nextOffset": offset + limit if offset + limit < len(values) else None,
        }

    def search(self, query: str, offset=0, limit=10) -> dict:
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            raise ValueError("Use a nonblank, bounded source search query.")
        wanted = terms(query)
        counts = Counter(term for values in self._term_sets.values() for term in wanted & values)
        ranked = []
        for key, entry in self.entries.items():
            matched = wanted & self._term_sets[key]
            exact = normalized(query).strip() in normalized(entry["title"] + " " + entry["url"])
            if not matched and not exact:
                continue
            headings = terms(entry["title"] + " " + entry["url"])
            score = sum(
                (1 + math.log(1 + len(self.entries) / counts[term])) * (3 if term in headings else 1)
                for term in matched
            ) + (8 if exact else 0)
            ranked.append((score, key, entry))
        ranked.sort(key=lambda row: (-row[0], row[1]))
        page = self._page([row[2] for row in ranked], offset, limit)
        for entry in page["sources"]:
            entry["readOffset"] = self.passage(entry["id"], query, MAX_READ_CHARS)["offset"]
        return page

    def source(self, source_id: str) -> dict:
        entry = self.entries.get(source_id)
        if entry is None:
            raise ValueError("This source is not in the job's project snapshot.")
        source = self._inline.get(source_id)
        if source is None:
            source = source_record(read_project_json(
                self.root, self.owner, self.workspace, "blobs", entry["version"], MAX_SOURCE_BYTES,
            ))
        if any(source[key] != entry[key] for key in ("id", "title", "url")):
            raise ValueError("Source snapshot identity changed.")
        return source

    def read(self, source_id: str, offset=0, limit=MAX_READ_CHARS) -> dict:
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 20000:
            raise ValueError("Use a valid source passage range.")
        source = self.source(source_id)
        text = source.get("excerpt") or ""
        if offset > len(text):
            raise ValueError("The passage starts beyond the source. Use its excerptCharacters length.")
        end = min(offset + limit, len(text))
        return {
            "source": {**source, "excerpt": text[offset:end]},
            "version": self.entries[source_id]["version"],
            "offset": offset, "end": end, "totalCharacters": len(text),
            "nextOffset": end if end < len(text) else None,
        }

    def passage(self, source_id: str, query: str, limit=4000) -> dict:
        """Choose the window covering the most informative distinct query terms."""
        source = self.source(source_id)
        text = source.get("excerpt") or ""
        wanted = sorted(terms(query), key=lambda word: (-len(word), word))
        # casefold may change string length. Locate on original character slices
        # through regex instead, keeping offsets in the immutable original.
        matches = {
            word: [match.start() for match in re.finditer(re.escape(word), text, re.IGNORECASE)]
            for word in wanted
        }
        matches = {word: positions for word, positions in matches.items() if positions}
        weights = {
            word: (1 + math.log(1 + len(self.entries) / (
                1 + sum(word in values for values in self._term_sets.values())
            ))) * (1 + min(len(word), 20) / 20)
            for word in matches
        }
        candidates = {0}
        for positions in matches.values():
            for position in positions:
                candidates.add(max(0, position - min(500, limit // 4)))

        def score(start):
            coverage = 0
            for word, positions in matches.items():
                index = bisect_left(positions, start)
                if index < len(positions) and positions[index] + len(word) <= start + limit:
                    coverage += weights[word]
            # Repeated generic words get no extra weight. Prefer a short useful
            # tail over padding it with unrelated text, then an earlier tie.
            return coverage, -min(limit, len(text) - start), -start

        offset = max(candidates, key=score)
        return self.read(source_id, offset, limit)


def _intervals(ranges):
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return merged


class SourceEvidence:
    """Keep exact consumed ranges, independently of library size and tool output."""

    def __init__(self, catalog: SourceCatalog, *, max_sources=MAX_EVIDENCE_SOURCES, max_chars=MAX_EVIDENCE_CHARS):
        self.catalog = catalog
        self.max_sources, self.max_chars = max_sources, max_chars
        self._ranges = {}
        self._originals = {}

    def _records(self, ranges):
        return [{
            **self._originals[source_id],
            "excerpt": "\n".join(
                (self._originals[source_id].get("excerpt") or "")[start:end] for start, end in spans
            ),
        } for source_id, spans in ranges.items()]

    @property
    def sources(self):
        return self._records(self._ranges)

    @property
    def characters(self):
        return sum(len(source["excerpt"]) for source in self.sources)

    @property
    def reads(self):
        return [{
            "id": key, "version": self.catalog.entries[key]["version"],
            "ranges": [list(span) for span in spans],
        } for key, spans in self._ranges.items()]

    def read(self, source_id, offset=0, limit=MAX_READ_CHARS):
        result = self.catalog.read(source_id, offset, limit)
        if result["end"] == offset:
            return result
        self._originals.setdefault(source_id, self.catalog.source(source_id))
        candidate = {**self._ranges, source_id: _intervals([
            *self._ranges.get(source_id, []), [offset, result["end"]],
        ])}
        if len(candidate) > self.max_sources or sum(
            len(source["excerpt"]) for source in self._records(candidate)
        ) > self.max_chars:
            raise ValueError(
                "This request's evidence budget is full. Read fewer sources or shorter passages; "
                "stored project sources do not need to be deleted."
            )
        self._ranges = candidate
        return result


def evidence_from_reads(catalog: SourceCatalog, reads) -> SourceEvidence:
    if not isinstance(reads, list) or len(reads) > MAX_EVIDENCE_SOURCES:
        raise ValueError("Invalid source-read manifest.")
    evidence = SourceEvidence(catalog)
    count = 0
    for item in reads:
        if not isinstance(item, dict) or set(item) != {"id", "version", "ranges"}:
            raise ValueError("Invalid source-read manifest.")
        entry = catalog.entries.get(item["id"])
        if entry is None or item["version"] != entry["version"]:
            raise ValueError("Source-read version is not in this job's snapshot.")
        ranges = item["ranges"]
        if not isinstance(ranges, list):
            raise ValueError("Invalid source-read ranges.")
        for span in ranges:
            count += 1
            if (
                count > 200 or not isinstance(span, list) or len(span) != 2
                or any(type(value) is not int for value in span)
                or not 0 <= span[0] < span[1] <= entry["excerptCharacters"]
            ):
                raise ValueError("Invalid source-read ranges.")
            evidence.read(item["id"], span[0], span[1] - span[0])
    return evidence

