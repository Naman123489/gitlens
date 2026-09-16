"""Shared primitives for the RepoLens analysis engine."""

from .enums import (
    AIUsageClassification,
    ConfidenceBand,
    FileCategory,
    JobStatus,
    OriginalityClassification,
    Role,
    ScoreCategory,
    Severity,
    SkillDimension,
    VerificationStatus,
)
from .evidence import (
    AnalyzerResult,
    CategoryScore,
    Evidence,
    EvidenceDetail,
    Limitation,
)
from .versioning import (
    ANALYZER_VERSION,
    PROMPT_VERSION,
    SCORING_ENGINE_VERSION,
    RunVersions,
)

__all__ = [
    "AIUsageClassification",
    "ANALYZER_VERSION",
    "AnalyzerResult",
    "CategoryScore",
    "ConfidenceBand",
    "Evidence",
    "EvidenceDetail",
    "FileCategory",
    "JobStatus",
    "Limitation",
    "OriginalityClassification",
    "PROMPT_VERSION",
    "Role",
    "RunVersions",
    "SCORING_ENGINE_VERSION",
    "ScoreCategory",
    "Severity",
    "SkillDimension",
    "VerificationStatus",
]
