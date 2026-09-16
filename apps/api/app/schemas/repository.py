"""Repository and analysis payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class RepositoryOut(ORMModel):
    id: str
    name: str
    full_name: str
    description: str | None = None
    html_url: str | None = None
    primary_language: str | None = None
    languages: dict[str, int] = Field(default_factory=dict)
    topics: list[str] = Field(default_factory=list)
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    size_kb: int = 0
    is_private: bool = False
    is_fork: bool = False
    is_archived: bool = False
    default_branch: str = "main"
    license_name: str | None = None
    analysis_status: str = "NOT_ANALYZED"
    last_analyzed_at: datetime | None = None
    pushed_at: datetime | None = None
    is_demo: bool = False


class GitHubRepositoryOut(BaseModel):
    """A repository on GitHub that has not necessarily been imported yet."""

    external_id: str
    name: str
    full_name: str
    description: str | None = None
    html_url: str
    clone_url: str
    default_branch: str
    language: str | None = None
    stars: int = 0
    forks: int = 0
    size_kb: int = 0
    private: bool = False
    fork: bool = False
    archived: bool = False
    topics: list[str] = Field(default_factory=list)
    pushed_at: datetime | None = None
    imported: bool = False
    repository_id: str | None = None


class ImportRepositoryRequest(BaseModel):
    full_name: str = Field(min_length=3, max_length=300)
    candidate_id: str | None = None


class AnalyzeRequest(BaseModel):
    force: bool = False
    compare_against_corpus: bool = True


class StageOut(BaseModel):
    key: str
    label: str
    status: str
    progress: float = 0.0


class AnalysisJobOut(ORMModel):
    id: str
    repository_id: str
    status: str
    progress: float
    current_stage: str | None = None
    stages: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    analysis_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None


class AnalysisOut(ORMModel):
    id: str
    repository_id: str
    head_sha: str | None = None
    analyzer_version: str
    repository_score: float | None = None
    ownership_confidence: float | None = None
    ai_likelihood: float | None = None
    ai_classification: str | None = None
    ai_utilization: float | None = None
    originality: str | None = None
    is_partial: bool
    duration_seconds: float
    category_scores: dict[str, Any] = Field(default_factory=dict)
    stats: dict[str, Any] = Field(default_factory=dict)
    failures: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class AnalysisDetailOut(AnalysisOut):
    results: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class SecurityFindingOut(ORMModel):
    id: str
    kind: str
    rule_id: str
    title: str
    category: str | None = None
    severity: str
    confidence: float
    file_path: str
    line: int
    masked_value: str | None = None
    snippet: str | None = None
    remediation: str | None = None
    cwe: str | None = None
    note: str | None = None


class SimilarityOut(ORMModel):
    id: str
    scope: str
    mechanism: str
    similarity: float
    source_file: str
    source_symbol: str
    matched_repository_name: str | None = None
    matched_file: str | None = None
    matched_symbol: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class CommitOut(ORMModel):
    sha: str
    author_name: str
    author_email: str
    committed_at: datetime
    subject: str
    intent: str
    insertions: int
    deletions: int
    files_changed: int
    is_merge: bool
