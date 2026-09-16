"""Repositories and their ingested artefacts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Repository(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "full_name", name="uq_repository_owner_full_name"),
        Index("ix_repositories_candidate", "candidate_id"),
    )

    owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True
    )
    github_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("github_accounts.id", ondelete="SET NULL"), nullable=True
    )

    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="github")
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    full_name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    clone_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(100), nullable=False, default="main")
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_fork: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    primary_language: Mapped[str | None] = mapped_column(String(60), nullable=True)
    languages: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)
    topics: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    forks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_issues: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    size_kb: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    license_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    readme: Mapped[str | None] = mapped_column(Text, nullable=True)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    repo_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    repo_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_analyzed_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analysis_status: Mapped[str] = mapped_column(String(20), nullable=False, default="NOT_ANALYZED")
    github_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    files: Mapped[list["RepositoryFile"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    analyses: Mapped[list["RepositoryAnalysis"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan",
        order_by="RepositoryAnalysis.created_at.desc()",
    )


class RepositoryFile(UUIDMixin, Base):
    """One file from the most recent ingestion, with its content hash.

    The hash is what makes incremental analysis possible: unchanged files reuse
    the previous run's per-file results.
    """

    __tablename__ = "repository_files"
    __table_args__ = (
        UniqueConstraint("repository_id", "path", name="uq_repository_file_path"),
        Index("ix_repository_files_hash", "content_hash"),
    )

    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    language: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    analysis: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    skipped_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)

    repository: Mapped[Repository] = relationship(back_populates="files")


class RepositoryCommit(UUIDMixin, Base):
    __tablename__ = "repository_commits"
    __table_args__ = (
        UniqueConstraint("repository_id", "sha", name="uq_repository_commit_sha"),
        Index("ix_repository_commits_date", "repository_id", "committed_at"),
    )

    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sha: Mapped[str] = mapped_column(String(64), nullable=False)
    author_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    author_email: Mapped[str] = mapped_column(String(320), nullable=False, default="", index=True)
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    intent: Mapped[str] = mapped_column(String(30), nullable=False, default="other", index=True)
    insertions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deletions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_merge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RepositoryBranch(UUIDMixin, Base):
    __tablename__ = "repository_branches"
    __table_args__ = (UniqueConstraint("repository_id", "name", name="uq_repository_branch"),)

    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RepositoryDependency(UUIDMixin, Base):
    __tablename__ = "repository_dependencies"
    __table_args__ = (
        Index("ix_repository_dependencies_name", "repository_id", "name"),
    )

    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version_spec: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    ecosystem: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    manifest: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    is_dev: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)


class CodeChunk(UUIDMixin, Base):
    """A function-level chunk with its fingerprints and embedding.

    ``embedding`` is stored as JSON so the schema works on any PostgreSQL. When
    the ``vector`` extension is available a companion ``code_chunk_vectors``
    table is used for ANN search (see ``app/services/vectors.py``).
    """

    __tablename__ = "code_chunks"
    __table_args__ = (
        Index("ix_code_chunks_repo_file", "repository_id", "file_path"),
        Index("ix_code_chunks_signature", "structure_signature"),
    )

    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    symbol: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    language: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    start_line: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    structure_signature: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    fingerprints: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False, default=list)
    embedder: Mapped[str] = mapped_column(String(60), nullable=False, default="")


class RepositoryAnalysis(UUIDMixin, TimestampMixin, Base):
    """One completed analysis run over a repository.

    Immutable: a re-analysis creates a new row so historic evaluations keep
    pointing at the data they were computed from.
    """

    __tablename__ = "repository_analyses"

    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_job_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    head_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analyzer_version: Mapped[str] = mapped_column(String(20), nullable=False, default="")

    #: Per-analyzer results, keyed by analyzer name.
    results: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    #: Scores for the analysis-only categories (job relevance needs a job).
    category_scores: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    limitations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    failures: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    repository_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ownership_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_likelihood: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_classification: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ai_utilization: Mapped[float | None] = mapped_column(Float, nullable=True)
    originality: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_partial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    repository: Mapped[Repository] = relationship(back_populates="analyses")


class SecurityFinding(UUIDMixin, Base):
    """A security finding. Secret values are stored masked, never in plaintext."""

    __tablename__ = "security_findings"
    __table_args__ = (Index("ix_security_findings_analysis", "analysis_id", "severity"),)

    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("repository_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="pattern")
    rule_id: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    line: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    masked_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    cwe: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SimilarityResult(UUIDMixin, Base):
    __tablename__ = "similarity_results"
    __table_args__ = (Index("ix_similarity_results_analysis", "analysis_id", "similarity"),)

    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("repository_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="internal")
    mechanism: Mapped[str] = mapped_column(String(30), nullable=False, default="fingerprint")
    similarity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_file: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    source_symbol: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    matched_repository_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    matched_repository_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    matched_file: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    matched_symbol: Mapped[str | None] = mapped_column(String(300), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
