"""Bounded public request and response contracts for writing proposals."""
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.models import normalize_model_name


def validate_source_url(value: str) -> str:
    """Validate without fetching or changing the original citation URL."""
    if any(character.isspace() or ord(character) < 32 for character in value) or "\\" in value:
        raise ValueError("참고자료 URL에는 공백이나 제어 문자를 사용할 수 없습니다.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError("올바른 참고자료 URL을 입력해 주세요.") from error
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port == 0
    ):
        raise ValueError("참고자료에는 인증 정보가 없는 HTTP(S) URL을 입력해 주세요.")
    return value


class WritingSource(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)

    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=2048)
    excerpt: str | None = Field(default=None, max_length=20000)

    _valid_url = field_validator("url")(validate_source_url)

    @field_validator("id", "title")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("참고자료 ID와 제목을 입력해 주세요.")
        return value


class WritingRequest(BaseModel):
    # The same-origin proxy injects a graph `config`; it must have no influence
    # on a stateless proposal or on the server's credentials.
    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)

    document: str = Field(max_length=200000)
    selectedText: str | None = Field(default=None, min_length=1, max_length=200000)
    instruction: str = Field(min_length=1, max_length=4000)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    sources: list[WritingSource] = Field(max_length=50)

    @field_validator("instruction")
    @classmethod
    def nonblank_instruction(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("수정 요청을 입력해 주세요.")
        return value.strip()

    @field_validator("model")
    @classmethod
    def allowed_model(cls, value: str | None) -> str | None:
        return normalize_model_name(value) if value is not None else None

    @model_validator(mode="after")
    def validate_context(self):
        if self.selectedText is not None and self.selectedText not in self.document:
            raise ValueError("선택한 내용이 현재 문서에 없습니다. 다시 선택해 주세요.")
        if len({source.id for source in self.sources}) != len(self.sources):
            raise ValueError("참고자료 ID가 중복되었습니다.")
        if sum(len(source.excerpt or "") for source in self.sources) > 100000:
            raise ValueError("참고자료 발췌문은 합계 100,000자 이내로 줄여 주세요.")
        return self


class WritingResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    replacement: str = Field(max_length=200000)
    explanation: str = Field(min_length=1, max_length=4000)

    @field_validator("explanation")
    @classmethod
    def nonblank_explanation(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("The model returned an empty explanation.")
        return value
