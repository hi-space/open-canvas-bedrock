"""Strict, bounded inputs shared by the local and AgentCore entry points."""
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api.writing.models import WritingSource
from core.models import get_default_model_name, normalize_model_name


MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_FILE_CHARS = 200000
MAX_FILES = 200
MAX_PATH_DEPTH = 8
MAX_READ_CONTEXT = 400000
MAX_SOURCE_CONTEXT = 100000
MAX_HISTORY_CONTEXT = 64000
MAX_PROPOSALS = 20
MAX_PROPOSAL_CONTEXT = 400000


def valid_path(value: str) -> str:
    parts = value.split("/")
    if (
        not value or len(value) > 500 or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or len(parts) > MAX_PATH_DEPTH
        or any(
            not part or part.startswith(".") or ":" in part or len(part.encode("utf-8")) > 240
            for part in parts
        )
        or PurePosixPath(value).suffix.lower() not in {".md", ".markdown", ".txt", ".html", ".htm"}
    ):
        raise ValueError("Use a relative Markdown, TXT, or HTML path without hidden or parent components.")
    return value


def valid_content(value: str) -> str:
    if "\x00" in value or len(value) > MAX_FILE_CHARS or len(value.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("Files must be plain UTF-8 text within the 200,000 character / 2 MiB limit.")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class HistoryMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=16000)


class Selection(StrictModel):
    path: str
    start: int = Field(ge=0, le=MAX_FILE_CHARS)
    end: int = Field(ge=1, le=MAX_FILE_CHARS)
    text: str = Field(min_length=1, max_length=MAX_FILE_CHARS)
    nodeId: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")

    _valid_path = field_validator("path")(valid_path)

    @model_validator(mode="after")
    def ordered_offsets(self):
        if self.end <= self.start or self.end - self.start != len(self.text):
            raise ValueError("The selection must use exact Python character offsets.")
        return self


class Invocation(StrictModel):
    ownerKey: str = Field(pattern=r"^[a-f0-9]{64}$")
    workspaceId: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    message: str = Field(min_length=1, max_length=4000)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=40)
    sources: list[WritingSource] = Field(default_factory=list, max_length=50)
    sourceSnapshot: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    activePath: str | None = None
    selection: Selection | None = None
    outputFormat: Literal["html"] | None = None

    @field_validator("message")
    @classmethod
    def nonblank_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("An editing request is required.")
        return value

    @field_validator("model")
    @classmethod
    def allowed_model(cls, value: str | None) -> str | None:
        return normalize_model_name(value) if value is not None else None

    @field_validator("activePath")
    @classmethod
    def active_file(cls, value: str | None) -> str | None:
        return valid_path(value) if value is not None else None

    @model_validator(mode="after")
    def bounded_context(self):
        if sum(len(item.content) for item in self.history) > MAX_HISTORY_CONTEXT:
            raise ValueError("Conversation history exceeds the 64,000 character limit.")
        if sum(len(source.excerpt or "") for source in self.sources) > MAX_SOURCE_CONTEXT:
            raise ValueError("Source excerpts exceed the 100,000 character limit.")
        if len({source.id for source in self.sources}) != len(self.sources):
            raise ValueError("Source IDs must be unique.")
        if self.selection is not None and self.selection.path != self.activePath:
            raise ValueError("The selection must belong to the active file.")
        if self.outputFormat is not None and self.selection is not None:
            raise ValueError("HTML generation creates a new file and cannot include a selection.")
        # Reject lone surrogate escapes before serializing requests or responses.
        def check_utf8(value):
            if isinstance(value, str):
                value.encode("utf-8")
            elif isinstance(value, list):
                for item in value:
                    check_utf8(item)
            elif isinstance(value, dict):
                for item in value.values():
                    check_utf8(item)
        check_utf8(self.model_dump())
        return self

    @property
    def model_name(self) -> str:
        return self.model or get_default_model_name()


class NoArguments(StrictModel):
    pass


class FileArguments(StrictModel):
    path: str

    _valid_path = field_validator("path")(valid_path)


class SearchArguments(StrictModel):
    query: str = Field(min_length=1, max_length=200)

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A nonblank literal search query is required.")
        return value


class ReferenceArguments(StrictModel):
    url: str = Field(min_length=1, max_length=2048)


class SourceListArguments(StrictModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=20)


class SourceSearchArguments(SourceListArguments):
    query: str = Field(min_length=1, max_length=500)


class SourceReadArguments(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    offset: int = Field(default=0, ge=0, le=20000)
    limit: int = Field(default=8000, ge=1, le=8000)


class EditArguments(FileArguments):
    replacement: str = Field(max_length=MAX_FILE_CHARS)
    explanation: str = Field(min_length=1, max_length=4000)

    _valid_content = field_validator("replacement")(valid_content)

    @field_validator("explanation")
    @classmethod
    def nonblank_explanation(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A brief explanation is required.")
        value.encode("utf-8")
        return value


class TextEdit(StrictModel):
    find: str = Field(min_length=1, max_length=20000)
    replace: str = Field(max_length=20000)


class TargetedEditArguments(FileArguments):
    edits: list[TextEdit] = Field(min_length=1, max_length=100)
    explanation: str = Field(min_length=1, max_length=4000)

    @field_validator("explanation")
    @classmethod
    def nonblank_explanation(cls, value: str) -> str:
        return EditArguments.nonblank_explanation(value)


class ReviseArguments(FileArguments):
    instruction: str = Field(min_length=1, max_length=4000)
    explanation: str = Field(min_length=1, max_length=4000)

    @field_validator("instruction", "explanation")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        return EditArguments.nonblank_explanation(value)


TOOL_ARGUMENTS = {
    "list_files": NoArguments,
    "read_file": FileArguments,
    "search_files": SearchArguments,
    "fetch_reference": ReferenceArguments,
    "list_sources": SourceListArguments,
    "search_sources": SourceSearchArguments,
    "read_source": SourceReadArguments,
    "propose_edit": EditArguments,
    "apply_edits": TargetedEditArguments,
    "revise_document": ReviseArguments,
}
