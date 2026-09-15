"""SQLAlchemy models. Importing this module registers every table on ``Base``."""

from app.db.base import Base
from app.models.evaluation import (
    Evaluation,
    EvaluationPolicyRecord,
    EvaluationScore,
    EvidenceRecord,
    HumanOverride,
    Job,
    JobRequirement,
    Recommendation,
    ReviewerNote,
)
from app.models.identity import (
    Candidate,
    GitHubAccount,
    Organization,
    OrganizationMember,
    User,
)
from app.models.interview import InterviewAnswer, InterviewQuestion, InterviewSession
from app.models.repository import (
    CodeChunk,
    Repository,
    RepositoryAnalysis,
    RepositoryBranch,
    RepositoryCommit,
    RepositoryDependency,
    RepositoryFile,
    SecurityFinding,
    SimilarityResult,
)
from app.models.system import AnalysisJob, AnalyzerFailureRecord, AuditLog, OAuthState

__all__ = [
    "AnalysisJob", "AnalyzerFailureRecord", "AuditLog", "Base", "Candidate", "CodeChunk",
    "Evaluation", "EvaluationPolicyRecord", "EvaluationScore", "EvidenceRecord", "GitHubAccount",
    "HumanOverride", "InterviewAnswer", "InterviewQuestion", "InterviewSession", "Job",
    "JobRequirement", "OAuthState", "Organization", "OrganizationMember", "Recommendation",
    "Repository", "RepositoryAnalysis", "RepositoryBranch", "RepositoryCommit",
    "RepositoryDependency", "RepositoryFile", "ReviewerNote", "SecurityFinding",
    "SimilarityResult", "User",
]
