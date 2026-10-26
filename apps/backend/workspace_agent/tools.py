"""Owner-scoped file tools. Every filesystem descriptor is opened read-only."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import ipaddress
import os
from pathlib import Path
import socket
import stat
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import ValidationError

from api.writing.models import WritingRequest, WritingResponse, WritingSource, validate_source_url
from api.writing.service import _validate_citations
from core.source_catalog import SourceCatalog, SourceEvidence
from api.workspaces.html_documents import (
    html_citation_text, html_selection, html_source_ids, is_html_path, prepare_html,
    replace_html_selection, validate_html,
)
from workspace_agent.models import (
    Invocation, MAX_FILES, MAX_FILE_BYTES, MAX_PATH_DEPTH, MAX_PROPOSALS,
    MAX_PROPOSAL_CONTEXT, MAX_READ_CONTEXT, TOOL_ARGUMENTS,
    valid_content, valid_path,
)
from workspace_agent.revise import MAX_SECTIONS, split_sections


class ToolError(ValueError):
    """A safe, actionable error that may be returned to the model."""


@dataclass(frozen=True)
class Snapshot:
    content: str
    version: str


_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
_MAX_DIRECTORY_ENTRIES = 2000
_MAX_SEARCH_MATCHES = 50
_MAX_FETCHES = 5


class WorkspaceTools:
    def __init__(self, root: Path | str, request: Invocation):
        self.root = Path(root)
        self.request = request
        self.proposals: list[dict] = []
        self.events: list[dict] = []
        self.fetched_sources: list[dict] = []
        self.catalog = SourceCatalog(
            root, request.ownerKey, request.workspaceId, request.sourceSnapshot,
            [source.model_dump(exclude_none=True) for source in request.sources],
        )
        self.evidence = SourceEvidence(self.catalog)
        self._snapshots: dict[str, Snapshot] = {}
        self._read_chars = 0
        self._fetch_count = 0
        self._files_fd: int | None = None
        # Set by the agent loop: rewrites sections with the model (see revise.py).
        self.revise = None

    @property
    def sources(self):
        return [WritingSource.model_validate(source) for source in self.evidence.sources]

    def _list_sources(self, offset=0, limit=20):
        return self.catalog.list(offset, limit)

    def _search_sources(self, query, offset=0, limit=20):
        return self.catalog.search(query, offset, limit)

    def _read_source(self, id, offset=0, limit=8000):
        result = self.catalog.read(id, offset, limit)
        self._charge_context(len(result["source"].get("excerpt") or ""))
        return self.evidence.read(id, offset, limit)

    def __enter__(self):
        descriptor = None
        try:
            descriptor = os.open(self.root, _DIRECTORY_FLAGS)
            for component in (self.request.ownerKey, self.request.workspaceId, "files"):
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            self._files_fd = descriptor
            descriptor = None
            if self.request.activePath is not None:
                snapshot = self._read_snapshot(self.request.activePath)
                selection = self.request.selection
                if selection is not None and snapshot.content[selection.start:selection.end] != selection.text:
                    raise ToolError("The selection no longer matches this file. Select it again.")
                if selection is not None and is_html_path(selection.path):
                    try:
                        resolved = html_selection(snapshot.content, selection.nodeId)
                    except ValueError as error:
                        raise ToolError(str(error)) from error
                    if any(getattr(selection, key) != resolved[key] for key in ("start", "end", "text", "nodeId")):
                        raise ToolError("The selection must match one complete HTML element.")
                elif selection is not None and selection.nodeId is not None:
                    raise ToolError("HTML node IDs can only select HTML files.")
            return self
        except OSError as error:
            self.__exit__(None, None, None)
            raise ToolError("The workspace mount or requested file is unavailable.") from error
        except Exception:
            self.__exit__(None, None, None)
            raise
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def __exit__(self, *_args):
        if self._files_fd is not None:
            os.close(self._files_fd)
            self._files_fd = None

    @contextmanager
    def _open_file(self, path: str):
        """Walk anchored descriptors so a symlink swap cannot redirect a read."""
        valid_path(path)
        if self._files_fd is None:
            raise ToolError("The workspace is not open.")
        parent = os.dup(self._files_fd)
        descriptor = None
        try:
            components = path.split("/")
            for component in components[:-1]:
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=parent)
                os.close(parent)
                parent = child
            descriptor = os.open(components[-1], _FILE_FLAGS, dir_fd=parent)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ToolError("Only regular Markdown, TXT, and HTML files can be read.")
            yield descriptor
        except FileNotFoundError:
            raise
        except OSError as error:
            raise ToolError("The file path is unavailable or contains a symlink.") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(parent)

    def _charge_context(self, amount: int):
        if self._read_chars + amount > MAX_READ_CONTEXT:
            raise ToolError("The file/source context limit was reached. Use a smaller set of files.")
        self._read_chars += amount

    def _read_snapshot(self, path: str) -> Snapshot:
        if path in self._snapshots:
            return self._snapshots[path]
        try:
            with self._open_file(path) as descriptor:
                if os.fstat(descriptor).st_size > MAX_FILE_BYTES:
                    raise ToolError("File content exceeds the 2 MiB limit.")
                with os.fdopen(os.dup(descriptor), "rb") as stream:
                    data = stream.read(MAX_FILE_BYTES + 1)
        except FileNotFoundError as error:
            raise ToolError("The requested file does not exist.") from error
        try:
            content = valid_content(data.decode("utf-8"))
        except (UnicodeError, ValueError) as error:
            raise ToolError("The file must be UTF-8 and within the 200,000 character / 2 MiB limit.") from error
        self._charge_context(len(content))
        snapshot = Snapshot(content, hashlib.sha256(data).hexdigest())
        self._snapshots[path] = snapshot
        return snapshot

    def _file_exists(self, path: str) -> bool:
        try:
            with self._open_file(path):
                return True
        except FileNotFoundError:
            return False

    def _list_files(self) -> dict:
        files: list[dict] = []
        inspected = 0
        truncated = False

        def walk(descriptor: int, prefix: str, depth: int):
            nonlocal inspected, truncated
            with os.scandir(descriptor) as entries:
                names = []
                for entry in entries:
                    inspected += 1
                    if inspected > _MAX_DIRECTORY_ENTRIES:
                        truncated = True
                        break
                    names.append(entry.name)
            for name in sorted(names):
                if len(files) > MAX_FILES:
                    truncated = True
                    break
                if name.startswith(".") or "\\" in name or any(ord(char) < 32 for char in name):
                    continue
                path = f"{prefix}/{name}" if prefix else name
                try:
                    info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode) and depth < MAX_PATH_DEPTH:
                        if inspected >= _MAX_DIRECTORY_ENTRIES:
                            truncated = True
                            continue
                        child = os.open(name, _DIRECTORY_FLAGS, dir_fd=descriptor)
                        try:
                            walk(child, path, depth + 1)
                        finally:
                            os.close(child)
                    elif stat.S_ISREG(info.st_mode):
                        valid_path(path)
                        files.append({"path": path, "bytes": info.st_size})
                except (OSError, ValueError):
                    # A concurrent delete/symlink replacement must not expose a
                    # different directory or make an entire listing unusable.
                    continue

        walk(self._files_fd, "", 1)
        return {"files": files[:MAX_FILES], "truncated": truncated or len(files) > MAX_FILES}

    def _read_file(self, path: str) -> dict:
        snapshot = self._read_snapshot(path)
        return {"path": path, "content": snapshot.content, "version": snapshot.version}

    def _search_files(self, query: str) -> dict:
        listing = self._list_files()
        matches = []
        truncated = listing["truncated"]
        for item in listing["files"]:
            try:
                content = self._read_snapshot(item["path"]).content
            except ToolError:
                truncated = True
                continue
            for number, line in enumerate(content.splitlines(), start=1):
                if query in line:
                    if len(matches) >= _MAX_SEARCH_MATCHES:
                        return {"matches": matches, "truncated": True}
                    position = line.index(query)
                    start = max(0, position - 100)
                    matches.append({
                        "path": item["path"], "line": number, "text": line[start:start + 500],
                    })
        return {"matches": matches, "truncated": truncated}

    @staticmethod
    def _public_reference_url(url: str, *, resolve: bool = False):
        validate_source_url(url)
        parsed = urlsplit(url)
        host = parsed.hostname.rstrip(".").lower()
        if (
            parsed.port not in {None, 80, 443} or "%" in host
            or host == "localhost" or host.endswith((".localhost", ".local", ".internal"))
        ):
            raise ToolError("References must use a public HTTP(S) URL on port 80 or 443.")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if "." not in host:
                raise ToolError("References must use a public hostname.")
        else:
            if not address.is_global:
                raise ToolError("Private and local network references cannot be fetched.")
        if resolve:
            try:
                addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
                if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
                    raise ToolError("Private and local network references cannot be fetched.")
            except (OSError, ValueError) as error:
                raise ToolError("The reference hostname could not be verified as public.") from error

    def _fetch_reference(self, url: str) -> dict:
        validate_source_url(url)
        for entry in self.catalog.entries.values():
            if entry["url"] == url and entry["excerptCharacters"]:
                return {"source": self._read_source(entry["id"], 0, 20000)["source"]}
        self._public_reference_url(url)
        key = os.getenv("FIRECRAWL_API_KEY")
        if not key:
            raise ToolError("Reference fetching is unavailable. Add this URL and its excerpt as a source.")
        if self._fetch_count >= _MAX_FETCHES:
            raise ToolError("The five-reference fetch limit was reached.")
        existing = next((entry for entry in self.catalog.entries.values() if entry["url"] == url), None)
        if existing is None and len(self.evidence.sources) >= 50:
            raise ToolError("This request's source-read budget is full. Use a smaller set of evidence.")
        self._fetch_count += 1
        self._public_reference_url(url, resolve=True)
        try:
            from firecrawl import Firecrawl
            # Only the fixed external Firecrawl service makes the web request.
            # No document-controlled URL is fetched from this VPC directly.
            client = Firecrawl(
                api_key=key, api_url="https://api.firecrawl.dev", timeout=25, max_retries=0,
            )
            document = client.scrape(url, formats=["markdown"], only_main_content=True, timeout=20000)
            markdown = document.markdown
            if not isinstance(markdown, str) or not markdown.strip():
                raise ToolError("This reference did not provide usable text. Add an excerpt manually.")
            excerpt = markdown[:20000]
            title = getattr(document.metadata, "title", None) if document.metadata else None
            title = title[:500] if isinstance(title, str) and title.strip() else urlsplit(url).hostname
            source = WritingSource(
                id=existing["id"] if existing else "web-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:24],
                title=title, url=url, excerpt=excerpt,
            )
            source.model_dump_json().encode("utf-8")
        except ToolError:
            raise
        except Exception as error:
            raise ToolError("The reference could not be fetched. Add its excerpt as a source.") from error
        self.catalog.add_inline(source.model_dump())
        result = self._read_source(source.id, 0, 20000)
        self.fetched_sources.append(source.model_dump())
        return {"source": result["source"]}

    def _propose_edit(self, path: str, replacement: str, explanation: str) -> dict:
        if self.request.selection is not None and path != self.request.selection.path:
            raise ToolError("A selection request can propose edits only to its selected file.")
        snapshot = self._snapshots.get(path)
        if self.request.outputFormat == "html" and (
            not path.lower().endswith(".html") or snapshot is not None or self._file_exists(path)
        ):
            raise ToolError("HTML generation must propose a NEW .html file; existing files are context only.")
        if snapshot is None and self._file_exists(path):
            raise ToolError("Call read_file for an existing file before proposing its replacement.")
        if snapshot is None:
            listing = self._list_files()
            existing_paths = {item["path"] for item in listing["files"]}
            pending_paths = {
                item["path"] for item in self.proposals
                if item["baseVersion"] is None and item["path"] != path
            }
            if listing["truncated"] or len(existing_paths | pending_paths) >= MAX_FILES:
                raise ToolError("The project's 200-file limit was reached.")
        original = snapshot.content if snapshot is not None else ""
        selection = self.request.selection
        selected = selection if selection is not None and selection.path == path else None
        proposed = (
            original[:selected.start] + replacement + original[selected.end:]
            if selected is not None else replacement
        )
        try:
            if is_html_path(path):
                allowed_sources = {source.id for source in self.sources} | html_source_ids(original)
                if selected is not None:
                    proposed = replace_html_selection(
                        original, selected.model_dump(), replacement, allowed_sources,
                    )
                    replacement = proposed[selected.start:len(proposed) - (len(original) - selected.end)]
                else:
                    proposed = prepare_html(proposed)
                    validate_html(proposed, allowed_sources)
                    replacement = proposed
            valid_content(proposed)
            citation_text = html_citation_text if is_html_path(path) else lambda content: content
            request = WritingRequest(
                document=citation_text(original),
                selectedText=citation_text(selected.text) if selected is not None else None,
                instruction=self.request.message,
                sources=self.sources,
            )
            response = WritingResponse(replacement=citation_text(replacement), explanation=explanation)
            _validate_citations(request, response)
            # A selection may edit a reference definition used by untouched
            # text. Validate the final document as well as the selected passage.
            if selected is not None:
                _validate_citations(
                    request.model_copy(update={"selectedText": None}),
                    WritingResponse(replacement=citation_text(proposed), explanation=explanation),
                )
        except HTTPException as error:
            raise ToolError(str(error.detail)) from error
        except (ValueError, UnicodeError) as error:
            raise ToolError("The proposal exceeds file limits or has invalid content.") from error
        others = [proposal for proposal in self.proposals if proposal["path"] != path]
        if len(others) >= MAX_PROPOSALS:
            raise ToolError("The proposal limit was reached. Request fewer files at a time.")
        if sum(len(item["proposedContent"]) for item in others) + len(proposed) > MAX_PROPOSAL_CONTEXT:
            raise ToolError("The proposed content limit was reached. Request a smaller edit.")
        proposal = {
            "path": path,
            "baseVersion": snapshot.version if snapshot is not None else None,
            "baseContent": original,
            "proposedContent": proposed,
            "explanation": explanation,
        }
        self.proposals = [*others, proposal]
        return {"path": path, "baseVersion": proposal["baseVersion"], "status": "proposed"}

    def _apply_edits(self, path: str, edits: list[dict], explanation: str) -> dict:
        """Resolve find/replace edits into a whole proposal, so output scales with the change."""
        snapshot = self._snapshots.get(path)
        if snapshot is None:
            raise ToolError("Call read_file before apply_edits. Use propose_edit to create a new file.")
        pending = next((item for item in self.proposals if item["path"] == path), None)
        # Repeated calls build on this job's pending proposal instead of discarding it.
        current = pending["proposedContent"] if pending is not None else snapshot.content
        spans = []
        for number, edit in enumerate(edits, start=1):
            find = edit["find"]
            start = current.find(find)
            count = 0
            position = start
            while position != -1 and count < 3:
                count += 1
                position = current.find(find, position + 1)
            if count != 1:
                found = "was not found" if count == 0 else f"appears {'3 or more' if count > 2 else count} times"
                raise ToolError(
                    f"Edit {number}: find text {found}. Copy it exactly from read_file, "
                    "with enough surrounding text to match exactly once."
                )
            spans.append((start, start + len(find), edit["replace"]))
        spans.sort()
        if any(following[0] < previous[1] for previous, following in zip(spans, spans[1:])):
            raise ToolError("Edits overlap. Merge overlapping edits into one.")
        revised = current
        for start, end, replace in reversed(spans):
            revised = revised[:start] + replace + revised[end:]
        selection = self.request.selection
        if selection is not None and selection.path == path:
            suffix = len(snapshot.content) - selection.end
            if any(start < selection.start or end > len(current) - suffix for start, end, _ in spans):
                raise ToolError("A selection request can edit only inside the selected passage.")
            replacement = revised[selection.start:len(revised) - suffix]
        else:
            replacement = revised
        return {**self._propose_edit(path, replacement, explanation), "edits": len(edits)}

    def _revise_document(self, path: str, instruction: str, explanation: str) -> dict:
        """Revise a whole file section by section; only the resulting proposal enters the transcript."""
        if self.request.selection is not None:
            raise ToolError("A selection request revises only the selected passage. Use apply_edits or propose_edit.")
        if is_html_path(path):
            raise ToolError("revise_document supports Markdown and TXT files. Use apply_edits for HTML.")
        if self.revise is None:
            raise ToolError("Section revision is unavailable in this runtime. Use apply_edits.")
        snapshot = self._snapshots.get(path) or self._read_snapshot(path)
        pending = next((item for item in self.proposals if item["path"] == path), None)
        base = pending["proposedContent"] if pending is not None else snapshot.content
        sections = split_sections(base)
        if len(sections) > MAX_SECTIONS:
            raise ToolError("The document has too many sections for one revision. Revise one part at a time.")

        def validate(before: str, after: str):
            _validate_citations(
                WritingRequest(document=base, selectedText=before, instruction=instruction, sources=self.sources),
                WritingResponse(replacement=after, explanation=explanation),
            )

        revised, unchanged = self.revise(sections, instruction, validate)
        if "".join(revised) == base:
            raise ToolError("No section could be revised. Explain to the user what blocked the revision.")
        result = self._propose_edit(path, "".join(revised), explanation)
        # Validation, deadline or shared budget limits can leave sections unchanged.
        return {**result, "sections": len(sections), "unchanged": unchanged}

    def execute(self, name: str, arguments: object) -> dict:
        schema = TOOL_ARGUMENTS.get(name)
        if schema is None:
            raise ToolError("Unknown tool. Use one of the listed workspace tools.")
        try:
            parsed = schema.model_validate(arguments)
        except ValidationError as error:
            raise ToolError("Invalid tool arguments. Use exactly the documented fields and types.") from error
        handler = getattr(self, f"_{name}")
        try:
            result = handler(**parsed.model_dump())
        except (ValidationError, UnicodeError) as error:
            raise ToolError("The tool input or returned content is invalid.") from error
        detail = parsed.path if hasattr(parsed, "path") else "Completed."
        self.events.append({"tool": name, "detail": detail})
        return result
