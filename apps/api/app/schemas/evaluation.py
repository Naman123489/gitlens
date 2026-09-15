"""Job, policy, evaluation and interview payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel

SCORE_CATEGORIES = (
    "technical_quality", "architecture", "job_relevance", "ownership", "testing",
    "documentation", "git_engineering", "security", "ai_utilization",
)


# -- policies ---------------------------------------------------------------

class PolicyWeights(BaseModel):
    technical_quality: float = Field(ge=0, le=1, default=0.20)
    architecture: float = Field(ge=0, le=1, default=0.15)
    job_relevance: float = Field(ge=0, le=1, default=0.20)
    ownership: float = Field(ge=0, le=1, default=0.15)
    testing: float = Field(ge=0, le=1, default=0.10)
    documentation: float = Field(ge=0, le=1, default=0.05)
    git_engineering: float = Field(ge=0, le=1, default=0.05)
    security: float = Field(ge=0, le=1, default=0.05)
    ai_utilization: float = Field(ge=0, le=1, default=0.05)

    @field_validator("*")
    @classmethod
    def _finite(cls, value: float) -> float:
        if value != value:  # NaN
            raise ValueError("weights must be numbers")
        return value

    def as_dict(self) -> dict[str, float]:
        return self.model_dump()


class PolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    weights: PolicyWeights = Field(default_factory=PolicyWeights)
    thresholds: dict[str, float] = Field(default_factory=dict)
    organization_id: str | None = None


class PolicyOut(ORMModel):
    id: str
    policy_key: str
    name: str
    description: str
    version: int
    is_current: bool
    organization_id: str | None = None
    weights: dict[str, float]
    thresholds: dict[str, Any]
    created_at: datetime


# -- jobs -------------------------------------------------------------------

class JobRequirementIn(BaseModel):
    skill: str = Field(min_length=1, max_length=60)
    required: bool = True
    importance: float | None = Field(default=None, ge=0, le=1)


class JobCreate(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    description: str = Field(min_length=10, max_length=40000)
    location: str | None = Field(default=None, max_length=200)
    organization_id: str | None = None
    policy_id: str | None = None
    is_public: bool = False
    #: Optional manual overrides applied after automatic parsing.
    requirements: list[JobRequirementIn] = Field(default_factory=list)


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=40000)
    location: str | None = None
    is_open: bool | None = None
    is_public: bool | None = None
    policy_id: str | None = None
    reparse: bool = False
    requirements: list[JobRequirementIn] | None = None


class JobRequirementOut(ORMModel):
    skill: str
    label: str
    dimension: str
    required: bool
    importance: float
    source: str
    matched_terms: list[str] = Field(default_factory=list)


class JobOut(ORMModel):
    id: str
    title: str
    description: str
    location: str | None = None
    experience_level: str
    domain: str
    min_years_experience: int | None = None
    responsibilities: list[str] = Field(default_factory=list)
    parse_notes: list[str] = Field(default_factory=list)
    organization_id: str | None = None
    policy_id: str | None = None
    is_open: bool
    is_public: bool
    is_demo: bool
    created_at: datetime
    requirements: list[JobRequirementOut] = Field(default_factory=list)


class JobParsePreview(BaseModel):
    requirements: list[dict[str, Any]]
    responsibilities: list[str]
    experience_level: str
    min_years_experience: int | None
    domain: str
    technologies: list[str]
    notes: list[str]


# -- evaluations ------------------------------------------------------------

class EvaluateRequest(BaseModel):
    repository_id: str
    job_id: str | None = None
    candidate_id: str | None = None
    policy_id: str | None = None
    organization_id: str | None = None


class EvaluationSummaryOut(ORMModel):
    id: str
    repository_id: str
    job_id: str | None = None
    candidate_id: str | None = None
    overall_score: float | None
    confidence: float
    job_match: float | None
    ownership_confidence: float | None
    ai_likelihood: float | None
    ai_utilization: float | None
    ai_classification: str | None
    originality: str | None
    verification_status: str
    created_at: datetime
    is_demo: bool


class EvaluationOut(EvaluationSummaryOut):
    verification_reasons: list[str] = Field(default_factory=list)
    limitations: list[dict[str, Any]] = Field(default_factory=list)
    failures: list[dict[str, Any]] = Field(default_factory=list)
    skill_matches: list[dict[str, Any]] = Field(default_factory=list)
    engineering_dna: dict[str, float] = Field(default_factory=dict)
    resume_consistency: dict[str, Any] | None = None
    narrative: dict[str, Any] | None = None
    versions: dict[str, Any] = Field(default_factory=dict)
    scores: list[dict[str, Any]] = Field(default_factory=list)
    policy: dict[str, Any] | None = None
    repository: dict[str, Any] | None = None
    job: dict[str, Any] | None = None
    candidate: dict[str, Any] | None = None
    recommendations: list[dict[str, Any]] = Field(default_factory=list)


class ReviewerNoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    category: str | None = Field(default=None, max_length=40)
    visible_to_candidate: bool = False


class ReviewerNoteOut(ORMModel):
    id: str
    author_name: str
    body: str
    category: str | None
    visible_to_candidate: bool
    created_at: datetime


class OverrideIn(BaseModel):
    target_type: Literal["score", "verification_status", "evidence"]
    target_key: str = Field(min_length=1, max_length=80)
    new_value: dict[str, Any]
    rationale: str = Field(min_length=10, max_length=4000)


class OverrideOut(ORMModel):
    id: str
    author_name: str
    target_type: str
    target_key: str
    original_value: dict[str, Any]
    new_value: dict[str, Any]
    rationale: str
    created_at: datetime


class CompareRequest(BaseModel):
    evaluation_ids: list[str] = Field(min_length=2, max_length=6)


# -- candidates -------------------------------------------------------------

class CandidateCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    github_login: str | None = Field(default=None, max_length=100)
    headline: str | None = Field(default=None, max_length=300)
    organization_id: str | None = None


class CandidateOut(ORMModel):
    id: str
    full_name: str
    email: str | None
    github_login: str | None
    headline: str | None
    organization_id: str | None
    user_id: str | None
    resume_filename: str | None
    has_resume: bool = False
    has_disclosure: bool = False
    is_demo: bool
    created_at: datetime


class DisclosureIn(BaseModel):
    """A candidate's voluntary statement about AI use.

    Stored separately from inferred signals; the two are compared, never
    conflated, and a disagreement is not treated as dishonesty.
    """

    used_ai: bool
    purposes: list[
        Literal["debugging", "documentation", "boilerplate", "testing", "architecture",
                "core_algorithms", "learning", "code_review", "refactoring"]
    ] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list, max_length=10)
    notes: str = Field(default="", max_length=4000)


class DisclosureOut(BaseModel):
    used_ai: bool | None = None
    purposes: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    notes: str = ""
    updated_at: datetime | None = None
    comparison: dict[str, Any] | None = None


# -- interviews -------------------------------------------------------------

class InterviewCreate(BaseModel):
    evaluation_id: str | None = None
    repository_id: str | None = None
    candidate_id: str | None = None
    title: str = Field(default="Technical verification", max_length=300)
    question_count: int = Field(default=8, ge=1, le=20)
    categories: list[str] = Field(default_factory=list)


class QuestionOut(ORMModel):
    id: str
    category: str
    question: str
    difficulty: str
    rationale: str
    anchors: list[dict[str, Any]] = Field(default_factory=list)
    expected_points: list[str] = Field(default_factory=list)
    generated_by: str


class AnswerIn(BaseModel):
    question_id: str
    answer_text: str = Field(min_length=0, max_length=20000)


class AnswerOut(ORMModel):
    id: str
    question_id: str
    answer_text: str
    word_count: int
    score: float | None
    assessment: dict[str, Any]
    assessed_by: str
    reviewer_score: float | None = None
    reviewer_comment: str | None = None


class ReviewerAnswerScore(BaseModel):
    reviewer_score: float = Field(ge=0, le=100)
    reviewer_comment: str = Field(default="", max_length=4000)


class InterviewOut(ORMModel):
    id: str
    title: str
    status: str
    mode: str
    evaluation_id: str | None
    candidate_id: str | None
    repository_id: str | None
    verification_score: float | None
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    summary: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    questions: list[QuestionOut] = Field(default_factory=list)
    answers: list[AnswerOut] = Field(default_factory=list)
