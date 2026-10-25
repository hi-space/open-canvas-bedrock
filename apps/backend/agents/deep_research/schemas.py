"""Structured outputs the model returns at each step."""
from typing import Literal

from pydantic import BaseModel, Field


class ResearchQuestion(BaseModel):
    id: str = Field(description="Q1, Q2, ...")
    question: str
    queries: list[str] = Field(min_length=1, max_length=4)


class ResearchBrief(BaseModel):
    title: str
    language: str = Field(description="ISO code, e.g. ko or en")
    audience: str
    thesis: str
    questions: list[ResearchQuestion] = Field(min_length=1, max_length=10)


class Finding(BaseModel):
    claim: str
    detail: str = ""
    quote: str = ""
    source_ids: list[str] = Field(min_length=1)
    strength: Literal["strong", "moderate", "weak"] = "moderate"


class Extraction(BaseModel):
    findings: list[Finding] = Field(default_factory=list, max_length=14)
    gaps: list[str] = Field(default_factory=list, max_length=5)
    follow_up_queries: list[str] = Field(default_factory=list, max_length=3)


class FigurePlan(BaseModel):
    kind: Literal["aws_architecture", "concept"]
    request: str
    caption: str
    renderer: Literal["auto", "native", "skill"] = "auto"
    reason: str = Field(default="", max_length=400)


class SectionPlan(BaseModel):
    id: str
    heading: str
    goal: str
    key_points: list[str] = Field(default_factory=list)
    finding_ids: list[str] = Field(default_factory=list)
    words: int = Field(default=400, ge=50, le=3000)
    figure: FigurePlan | None = None


class Outline(BaseModel):
    title: str
    sections: list[SectionPlan] = Field(min_length=1, max_length=12)


class SectionReview(BaseModel):
    id: str
    score: int = Field(ge=1, le=5)
    notes: list[str] = Field(default_factory=list)


class Review(BaseModel):
    global_notes: list[str] = Field(default_factory=list)
    sections: list[SectionReview] = Field(default_factory=list)
