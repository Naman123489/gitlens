"""Jobs, policies, evaluations, evidence and human overrides."""

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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class EvaluationPolicyRecord(UUIDMixin, TimestampMixin, Base):
    """A versioned scoring policy.

    Rows are immutable. Editing a policy inserts a new row with an incremented
    ``version`` and sets ``is_current`` on the new row only, so an evaluation can
    always be re-explained with the exact rules it used.
    """

    __tablename__ = "evaluation_policies"
    __table_args__ = (
        UniqueConstraint("policy_key", "version", name="uq_policy_key_version"),
        Index("ix_policies_org_current", "organization_id", "is_current"),
    )

    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    policy_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    weights: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False, default=dict)
    thresholds: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class Job(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "jobs"

    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    experience_level: Mapped[str] = mapped_column(String(30), nullable=False, default="unspecified")
    domain: Mapped[str] = mapped_column(String(40), nullable=False, default="general")
    min_years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    responsibilities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    parse_notes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("evaluation_policies.id", ondelete="SET NULL"), nullable=True
    )
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    requirements: Mapped[list["JobRequirement"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="JobRequirement.importance.desc()"
    )


class JobRequirement(UUIDMixin, Base):
    __tablename__ = "job_requirements"
    __table_args__ = (UniqueConstraint("job_id", "skill", name="uq_job_requirement_skill"),)

    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    dimension: Mapped[str] = mapped_column(String(30), nullable=False, default="backend")
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="explicit")
    matched_terms: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    job: Mapped[Job] = relationship(back_populates="requirements")


class Evaluation(UUIDMixin, TimestampMixin, Base):
    """A candidate's repository evaluated against a job with a policy version."""

    __tablename__ = "evaluations"
    __table_args__ = (
        Index("ix_evaluations_job_candidate", "job_id", "candidate_id"),
        Index("ix_evaluations_status", "verification_status"),
    )

    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_id: Mapped[str | None] = mapped_column(
        ForeignKey("repository_analyses.id", ondelete="SET NULL"), nullable=True
    )
    policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("evaluation_policies.id", ondelete="SET NULL"), nullable=True
    )

    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    job_match: Mapped[float | None] = mapped_column(Float, nullable=True)
    ownership_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_likelihood: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_utilization: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_classification: Mapped[str | None] = mapped_column(String(40), nullable=True)
    originality: Mapped[str | None] = mapped_column(String(40), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ANALYSIS_INCOMPLETE"
    )
    verification_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    limitations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    failures: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    skill_matches: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    engineering_dna: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False, default=dict)
    resume_consistency: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    narrative: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    versions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    scores: Mapped[list["EvaluationScore"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    evidence_items: Mapped[list["EvidenceRecord"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    notes: Mapped[list["ReviewerNote"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    overrides: Mapped[list["HumanOverride"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )


class EvaluationScore(UUIDMixin, Base):
    __tablename__ = "evaluation_scores"
    __table_args__ = (UniqueConstraint("evaluation_id", "category", name="uq_evaluation_score"),)

    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    unavailable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    sub_scores: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    evaluation: Mapped[Evaluation] = relationship(back_populates="scores")


class EvidenceRecord(UUIDMixin, Base):
    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_evaluation_category", "evaluation_id", "category"),)

    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    supports: Mapped[str] = mapped_column(String(20), nullable=False, default="neutral")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    details: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    analyzer: Mapped[str] = mapped_column(String(60), nullable=False, default="")

    evaluation: Mapped[Evaluation] = relationship(back_populates="evidence_items")


class ReviewerNote(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "reviewer_notes"

    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    author_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    #: Notes are interviewer-only by default and are never shown to candidates.
    visible_to_candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    evaluation: Mapped[Evaluation] = relationship(back_populates="notes")


class HumanOverride(UUIDMixin, TimestampMixin, Base):
    """A reviewer's correction of a machine finding.

    Overrides never delete the original value: both are kept so the audit trail
    shows what the system said and what the human decided.
    """

    __tablename__ = "human_overrides"

    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    author_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)  # score | verification_status | evidence
    target_key: Mapped[str] = mapped_column(String(80), nullable=False)
    original_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    new_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)

    evaluation: Mapped[Evaluation] = relationship(back_populates="overrides")


class Recommendation(UUIDMixin, TimestampMixin, Base):
    """An improvement suggestion generated for a candidate from their evidence."""

    __tablename__ = "recommendations"

    evaluation_id: Mapped[str | None] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    repository_id: Mapped[str | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    impact: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    effort: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    expected_gain: Mapped[float | None] = mapped_column(Float, nullable=True)
    generated_by: Mapped[str] = mapped_column(String(40), nullable=False, default="deterministic")
