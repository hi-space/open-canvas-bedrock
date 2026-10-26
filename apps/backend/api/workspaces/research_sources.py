"""Question-based retrieval; selection does not consume evidence until extraction."""
from collections import defaultdict

from core.research_sources import source_key
from core.source_catalog import SourceCatalog, SourceEvidence


MAX_REGISTERED_SOURCES = 12
MAX_REGISTERED_CHARS = 32000
PASSAGE_CHARS = 4000


class ResearchSources:
    def __init__(self, catalog: SourceCatalog, priority_urls=()):
        self.catalog = catalog
        self.priority = {source_key(url) for url in priority_urls}
        self.evidence = SourceEvidence(
            catalog, max_sources=MAX_REGISTERED_SOURCES, max_chars=MAX_REGISTERED_CHARS,
        )
        self.groups = defaultdict(list)
        for entry in catalog.entries.values():
            if entry["excerptCharacters"]:
                self.groups[source_key(entry["url"])].append(entry["id"])
        self.queries = {}
        self.passage_queries = {}
        self._seen = set()
        self.web_evidence = {}
        self.source_limit = MAX_REGISTERED_SOURCES
        self.char_limit = MAX_REGISTERED_CHARS

    def select(self, state: dict, max_rounds=2) -> dict:
        sources = {key: dict(value) for key, value in (state.get("sources") or {}).items()}
        first = state.get("round", 0) == 0 and max_rounds > 1
        self.source_limit = 8 if first else MAX_REGISTERED_SOURCES
        self.char_limit = 22000 if first else MAX_REGISTERED_CHARS
        self.evidence.max_sources, self.evidence.max_chars = self.source_limit, self.char_limit
        pending = defaultdict(list)
        for item in state.get("pendingQueries") or []:
            pending[item["question_id"]].append(item["query"])
        queues = []
        for question in state["brief"]["questions"]:
            query = " ".join([question["question"], *pending[question["id"]], *question.get("queries", [])])[:4000]
            self.queries[question["id"]] = query
            self.passage_queries[question["id"]] = (
                " ".join(pending[question["id"]])
                if state.get("round", 0) > 0 and pending[question["id"]] else query
            )
            hits = self.catalog.search(query, 0, 20)["sources"]
            matching = defaultdict(list)
            for hit in hits:
                if hit["excerptCharacters"]:
                    matching[source_key(hit["url"])].append(hit["id"])
            keys = list(matching)
            keys.sort(key=lambda key: key not in self.priority)
            if not keys:
                keys = [key for key in self.groups if key in self.priority][:2]
                matching = {key: self.groups[key] for key in keys}
            queues.append((question["id"], keys[:3], matching))

        by_url = {source_key(value["url"]): sid for sid, value in sources.items()}
        selected_ids = {read["id"] for read in self.evidence.reads}
        # Give every question its first candidate before taking second choices.
        for position in range(3):
            for question_id, keys, matching in queues:
                if position >= len(keys):
                    continue
                key = keys[position]
                ids = matching[key]
                if len(selected_ids | set(ids)) > self.source_limit:
                    ids = [item for item in ids if item in selected_ids] + [
                        item for item in ids if item not in selected_ids
                    ][:max(0, self.source_limit - len(selected_ids))]
                if not ids:
                    continue
                selected_ids.update(ids)
                sid = by_url.get(key)
                if sid is None:
                    number = max((int(s[1:]) for s in sources if s[1:].isdigit()), default=0) + 1
                    sid = f"S{number}"
                    by_url[key] = sid
                    entry = self.catalog.entries[ids[0]]
                    sources[sid] = {
                        "id": sid, "title": entry["title"], "url": entry["url"],
                        "content": "", "origin": "supplied", "score": 1.0,
                        "question_ids": [], "_registeredIds": [],
                    }
                value = sources[sid]
                value["_registeredIds"] = list(dict.fromkeys([*value.get("_registeredIds", []), *ids]))
                value["_registeredByQuestion"] = {
                    **value.get("_registeredByQuestion", {}), question_id: ids,
                }
                value["origin"] = "supplied"
                value["question_ids"] = list(dict.fromkeys([*value.get("question_ids", []), question_id]))
        return sources

    def _read_key(self, source, question):
        return (
            question["id"], source["id"],
            self.passage_queries.get(question["id"], question["question"]),
            tuple(source.get("_registeredByQuestion", {}).get(question["id"], source["_registeredIds"])),
        )

    def needs_read(self, source, question):
        return self._read_key(source, question) not in self._seen

    def hydrate(self, source: dict, question: dict, limit: int) -> dict | None:
        remaining = limit
        parts, used = [], []
        ids = source.get("_registeredByQuestion", {}).get(question["id"], source["_registeredIds"])
        for source_id in ids:
            if remaining <= 0:
                break
            query = self.passage_queries.get(question["id"], question["question"])
            passage = self.catalog.passage(source_id, query, min(PASSAGE_CHARS, remaining))
            try:
                read = self.evidence.read(
                    source_id, passage["offset"], max(1, passage["end"] - passage["offset"]),
                )
            except ValueError as error:
                if str(error).startswith("This request's evidence budget"):
                    available = self.char_limit - self.evidence.characters
                    already_read = any(item["id"] == source_id for item in self.evidence.reads)
                    if (len(self.evidence.reads) >= self.source_limit and not already_read) or available <= 2:
                        continue
                    passage = self.catalog.passage(source_id, query, min(remaining, available - 2))
                    read = self.evidence.read(source_id, passage["offset"], passage["end"] - passage["offset"])
                else:
                    raise
            text = read["source"]["excerpt"]
            if text:
                parts.append(text)
                used.append(source_id)
                remaining -= len(text) + 2
        if not parts:
            return None
        self._seen.add(self._read_key(source, question))
        return {**source, "content": "\n\n".join(parts), "suppliedSourceIds": used, "_consumed": True}

    def record_web(self, source: dict, limit: int):
        """Keep prompt-visible web evidence even if a later URL alias replaces it."""
        key = source_key(source["url"])
        text = source["content"][:limit]
        previous = self.web_evidence.get(key)
        if previous is None:
            self.web_evidence[key] = {
                "id": source["id"], "url": source["url"], "title": source["title"],
                "content": text,
            }
        elif text and text not in previous["content"]:
            previous["content"] += "\n\n" + text
