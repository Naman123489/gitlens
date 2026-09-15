"""Shared response primitives."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class Message(BaseModel):
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class EvidenceDetailOut(BaseModel):
    detail: str
    file: str | None = None
    line: int | None = None
    snippet: str | None = None
    metric: float | None = None


class EvidenceOut(ORMModel):
    evidence_id: str
    category: str
    claim: str
    severity: str
    confidence: float
    supports: str
    tags: list[str] = Field(default_factory=list)
    details: list[dict[str, Any]] = Field(default_factory=list)
    analyzer: str = ""


class LimitationOut(BaseModel):
    scope: str
    detail: str
    analyzer: str | None = None


class ScoreOut(ORMModel):
    category: str
    score: float | None
    confidence: float
    weight: float
    available: bool
    unavailable_reason: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    sub_scores: dict[str, Any] = Field(default_factory=dict)


class TimestampedOut(ORMModel):
    id: str
    created_at: datetime
    updated_at: datetime
