"""The public workspace contract and its resource limits."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api.writing.models import WritingSource
from core.models import normalize_model_name


class Input(BaseModel):
    # The legacy Next.js proxy may attach its graph config; it has no authority.
    model_config = ConfigDict(strict=True, extra="ignore")


class CreateWorkspace(Input):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("프로젝트 이름을 입력해 주세요.")
        return value.strip()


class SaveFile(Input):
    path: str = Field(min_length=1, max_length=500)
    content: str = Field(max_length=200000)
    baseVersion: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class Selection(Input):
    from_: int = Field(alias="from", ge=0)
    to: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=200000)
    nodeId: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")


class ChatRequest(Input):
    message: str = Field(min_length=1, max_length=4000)
    requestId: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    activePath: str | None = Field(default=None, max_length=500)
    activeVersion: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    selection: Selection | None = None
    model: str | None = Field(default=None, max_length=200)
    # Deep research: research the request and propose the result as a new file in this genre.
    researchGenre: Literal["paper", "blog", "linkedin"] | None = None
    outputFormat: Literal["html"] | None = None
    contextPaths: list[str] | None = Field(default=None, max_length=5)

    @model_validator(mode="after")
    def exclusive_output_mode(self):
        if self.outputFormat is not None and self.selection is not None:
            raise ValueError("HTML 생성은 새 문서를 만듭니다. 선택 영역을 해제해 주세요.")
        if self.contextPaths is not None and self.researchGenre is None:
            raise ValueError("프로젝트 자료 선택은 딥 리서치에서 사용할 수 있습니다.")
        return self

    @field_validator("message")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("메시지를 입력해 주세요.")
        return value.strip()

    @field_validator("model")
    @classmethod
    def known_model(cls, value):
        return normalize_model_name(value) if value is not None else None


class Decisions(Input):
    decisions: dict[str, str] = Field(max_length=1000)

    @field_validator("decisions")
    @classmethod
    def valid(cls, value):
        if not value or any(decision not in {"accepted", "rejected"} for decision in value.values()):
            raise ValueError("승인하거나 거절할 변경을 선택해 주세요.")
        return value


SourceInput = WritingSource
