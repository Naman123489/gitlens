"""RepoLens job matching, policies and deterministic scoring."""

from .engine import (
    ENGINE_VERSION,
    AnalyzerFailure,
    ScoredEvaluation,
    VerificationSignals,
    build_category_scores,
    decide_verification_status,
    score_evaluation,
)
from .jd_parser import ParsedJob, ParsedRequirement, parse_job_description
from .matching import (
    RepositoryEvidence,
    SkillMatch,
    engineering_dna,
    match_repository_to_job,
)
from .policy import (
    DEFAULT_POLICY,
    DEFAULT_WEIGHTS,
    PRESET_POLICIES,
    EvaluationPolicy,
    PolicyError,
    VerificationThresholds,
    validate_weights,
)
from .taxonomy import SKILLS, SKILLS_BY_KEY, Skill, expand_implications, extract_skills

__all__ = [
    "AnalyzerFailure", "DEFAULT_POLICY", "DEFAULT_WEIGHTS", "ENGINE_VERSION", "EvaluationPolicy",
    "PRESET_POLICIES", "ParsedJob", "ParsedRequirement", "PolicyError", "RepositoryEvidence",
    "SKILLS", "SKILLS_BY_KEY", "ScoredEvaluation", "Skill", "SkillMatch", "VerificationSignals",
    "VerificationThresholds", "build_category_scores", "decide_verification_status",
    "engineering_dna", "expand_implications", "extract_skills", "match_repository_to_job",
    "parse_job_description", "score_evaluation", "validate_weights",
]
