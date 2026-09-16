"""Audit logging, background jobs and analyzer health."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class AuditLog(UUIDMixin, Base):
    """Append-only record of consequential actions.

    Written for: evaluation creation, score generation, reviewer overrides,
    candidate data access, report generation and repository access.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_time", "actor_id", "created_at"),
        Index("ix_audit_logs_target", "target_type", "target_id"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    actor_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    actor_role: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    organization_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class AnalysisJob(UUIDMixin, TimestampMixin, Base):
    """An asynchronous repository analysis with per-stage progress."""

    __tablename__ = "analysis_jobs"
    __table_args__ = (Index("ix_analysis_jobs_status_created", "status", "created_at"),)

    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUEUED", index=True)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_stage: Mapped[str | None] = mapped_column(String(60), nullable=True)
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    worker: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    options: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class AnalyzerFailureRecord(UUIDMixin, Base):
    """A single analyzer that failed inside an otherwise successful run."""

    __tablename__ = "analyzer_failures"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    analysis_job_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    repository_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    analyzer: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    traceback_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)


class OAuthState(UUIDMixin, Base):
    """Short-lived CSRF state for the GitHub OAuth handshake."""

    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    redirect_to: Mapped[str | None] = mapped_column(String(500), nullable=True)
    intent: Mapped[str] = mapped_column(String(20), nullable=False, default="login")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
