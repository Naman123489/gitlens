"""Enumerations shared by every RepoLens analyzer and by the API layer.

These values are persisted, so they must stay stable. Renaming a member is a
breaking change that requires a migration and an analyzer version bump.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """Python 3.11 has ``enum.StrEnum`` but we keep an explicit base so the
    serialised value is always the member value, including in JSON columns."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class Role(StrEnum):
    STUDENT = "STUDENT"
    INTERVIEWER = "INTERVIEWER"
    ADMIN = "ADMIN"


class FileCategory(StrEnum):
    """How a file is treated by the analysis engine.

    Only ``CANDIDATE_CODE`` counts as candidate-authored source for quality,
    ownership and similarity scoring.
    """

    CANDIDATE_CODE = "CANDIDATE_CODE"
    TEST_CODE = "TEST_CODE"
    GENERATED_CODE = "GENERATED_CODE"
    DEPENDENCY_CODE = "DEPENDENCY_CODE"
    CONFIGURATION = "CONFIGURATION"
    DOCUMENTATION = "DOCUMENTATION"
    ASSET = "ASSET"
    IGNORED = "IGNORED"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidenceBand(StrEnum):
    """Human-readable confidence attached to every probabilistic conclusion."""

    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @classmethod
    def from_value(cls, value: float) -> "ConfidenceBand":
        if value < 0.35:
            return cls.VERY_LOW
        if value < 0.55:
            return cls.LOW
        if value < 0.78:
            return cls.MEDIUM
        return cls.HIGH


class ScoreCategory(StrEnum):
    """The scoreable dimensions. Evaluation policies assign weights to these."""

    TECHNICAL_QUALITY = "technical_quality"
    ARCHITECTURE = "architecture"
    JOB_RELEVANCE = "job_relevance"
    OWNERSHIP = "ownership"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    GIT_ENGINEERING = "git_engineering"
    SECURITY = "security"
    AI_UTILIZATION = "ai_utilization"


class VerificationStatus(StrEnum):
    """Outcome of an evaluation.

    Deliberately contains no accusatory or auto-rejecting member. The final
    hiring decision always belongs to a human reviewer.
    """

    CLEAR = "CLEAR"
    REVIEW_RECOMMENDED = "REVIEW_RECOMMENDED"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
    ANALYSIS_INCOMPLETE = "ANALYSIS_INCOMPLETE"


class AIUsageClassification(StrEnum):
    AI_ASSISTED = "AI_ASSISTED"
    AI_AUGMENTED = "AI_AUGMENTED"
    AI_DEPENDENT = "AI_DEPENDENT"
    AI_DOMINATED = "AI_DOMINATED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class OriginalityClassification(StrEnum):
    ORIGINAL = "ORIGINAL"
    POSSIBLY_TUTORIAL_DERIVED = "POSSIBLY_TUTORIAL_DERIVED"
    STRONG_TUTORIAL_SIMILARITY = "STRONG_TUTORIAL_SIMILARITY"
    UNKNOWN = "UNKNOWN"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SkillDimension(StrEnum):
    """Engineering DNA axes."""

    BACKEND = "backend"
    FRONTEND = "frontend"
    AI_ML = "ai_ml"
    SYSTEMS = "systems"
    DEVOPS = "devops"
    TESTING = "testing"
    SECURITY = "security"
    RESEARCH = "research"
    OPEN_SOURCE = "open_source"
