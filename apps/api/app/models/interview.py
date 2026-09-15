"""Repository-specific interview questions, sessions and answers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class InterviewQuestion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "interview_questions"
    __table_args__ = (Index("ix_interview_questions_repo_category", "repository_id", "category"),)

    repository_id: Mapped[str | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=True, index=True
    )
    evaluation_id: Mapped[str | None] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="code_specific")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: The concrete repository artefacts the question is about.
    anchors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    expected_points: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    generated_by: Mapped[str] = mapped_column(String(40), nullable=False, default="deterministic")
    generator_version: Mapped[str] = mapped_column(String(20), nullable=False, default="")


class InterviewSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "interview_sessions"

    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    evaluation_id: Mapped[str | None] = mapped_column(
        ForeignKey("evaluations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True, index=True
    )
    repository_id: Mapped[str | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True
    )
    interviewer_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="Technical verification")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="async")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    dimension_scores: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    answers: Mapped[list["InterviewAnswer"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class InterviewAnswer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "interview_answers"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("interview_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    answer_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Per-dimension assessment: correctness, specificity, repository consistency,
    #: depth, communication. Each is 0-100 with its own rationale.
    assessment: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    assessed_by: Mapped[str] = mapped_column(String(40), nullable=False, default="deterministic")
    reviewer_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    session: Mapped[InterviewSession] = relationship(back_populates="answers")
