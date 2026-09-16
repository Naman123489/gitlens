"""Evaluation policies.

A policy is the set of weights and thresholds an organisation evaluates with.
Policies are **versioned and immutable**: editing one creates a new version, and
every evaluation records the version it used, so a historic evaluation can
always be explained with the rules that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from repolens_shared import ScoreCategory

#: The default weighting, matching the product specification.
DEFAULT_WEIGHTS: dict[ScoreCategory, float] = {
    ScoreCategory.TECHNICAL_QUALITY: 0.20,
    ScoreCategory.ARCHITECTURE: 0.15,
    ScoreCategory.JOB_RELEVANCE: 0.20,
    ScoreCategory.OWNERSHIP: 0.15,
    ScoreCategory.TESTING: 0.10,
    ScoreCategory.DOCUMENTATION: 0.05,
    ScoreCategory.GIT_ENGINEERING: 0.05,
    ScoreCategory.SECURITY: 0.05,
    ScoreCategory.AI_UTILIZATION: 0.05,
}


class PolicyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VerificationThresholds:
    """When an evaluation should be flagged for a human conversation.

    None of these produce a rejection. The strongest outcome is
    ``VERIFICATION_REQUIRED``, which means "ask the candidate about this".
    """

    ownership_review_below: float = 65.0
    ownership_verification_below: float = 45.0
    external_similarity_review_above: float = 0.55
    external_similarity_verification_above: float = 0.75
    ai_likelihood_review_above: float = 65.0
    resume_gap_review_above: int = 2
    min_available_categories: int = 4

    def to_dict(self) -> dict[str, Any]:
        return {
            "ownership_review_below": self.ownership_review_below,
            "ownership_verification_below": self.ownership_verification_below,
            "external_similarity_review_above": self.external_similarity_review_above,
            "external_similarity_verification_above": self.external_similarity_verification_above,
            "ai_likelihood_review_above": self.ai_likelihood_review_above,
            "resume_gap_review_above": self.resume_gap_review_above,
            "min_available_categories": self.min_available_categories,
        }


@dataclass(frozen=True, slots=True)
class EvaluationPolicy:
    name: str
    version: int = 1
    weights: dict[ScoreCategory, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    thresholds: VerificationThresholds = field(default_factory=VerificationThresholds)
    organization_id: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        validate_weights(self.weights)

    def normalised_weights(self) -> dict[ScoreCategory, float]:
        total = sum(self.weights.values())
        return {k: v / total for k, v in self.weights.items() if v > 0}

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "organization_id": self.organization_id,
            "weights": {str(k): round(v, 4) for k, v in self.weights.items()},
            "thresholds": self.thresholds.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvaluationPolicy":
        weights = {
            ScoreCategory(key): float(value)
            for key, value in (payload.get("weights") or {}).items()
        }
        thresholds_payload = payload.get("thresholds") or {}
        known = VerificationThresholds().to_dict()
        thresholds = VerificationThresholds(
            **{k: thresholds_payload.get(k, v) for k, v in known.items()}
        )
        return cls(
            name=payload.get("name", "Custom policy"),
            version=int(payload.get("version", 1)),
            weights=weights or dict(DEFAULT_WEIGHTS),
            thresholds=thresholds,
            organization_id=payload.get("organization_id"),
            description=payload.get("description", ""),
        )


def validate_weights(weights: dict[ScoreCategory, float]) -> None:
    """Weights must be non-negative, cover known categories and not all be zero.

    They are *not* required to sum to 1: the engine normalises. Requiring exactly
    1.0 makes the UI hostile for no benefit.
    """
    if not weights:
        raise PolicyError("a policy must define at least one category weight")
    for category, value in weights.items():
        if not isinstance(category, ScoreCategory):
            raise PolicyError(f"unknown score category: {category}")
        if value < 0:
            raise PolicyError(f"weight for {category} must not be negative")
    if sum(weights.values()) <= 0:
        raise PolicyError("at least one category weight must be greater than zero")


DEFAULT_POLICY = EvaluationPolicy(
    name="RepoLens default",
    version=1,
    description="Balanced weighting across engineering quality, relevance and ownership.",
)

#: Ready-made alternatives offered in the interviewer UI.
PRESET_POLICIES: tuple[EvaluationPolicy, ...] = (
    DEFAULT_POLICY,
    EvaluationPolicy(
        name="Relevance-weighted",
        version=1,
        description="For hiring against a specific stack: job relevance dominates.",
        weights={
            ScoreCategory.JOB_RELEVANCE: 0.35, ScoreCategory.TECHNICAL_QUALITY: 0.17,
            ScoreCategory.ARCHITECTURE: 0.12, ScoreCategory.OWNERSHIP: 0.15,
            ScoreCategory.TESTING: 0.08, ScoreCategory.DOCUMENTATION: 0.04,
            ScoreCategory.GIT_ENGINEERING: 0.03, ScoreCategory.SECURITY: 0.03,
            ScoreCategory.AI_UTILIZATION: 0.03,
        },
    ),
    EvaluationPolicy(
        name="Ownership-weighted",
        version=1,
        description="For internship and graduate hiring: evidence of building and owning software.",
        weights={
            ScoreCategory.OWNERSHIP: 0.28, ScoreCategory.GIT_ENGINEERING: 0.14,
            ScoreCategory.TESTING: 0.14, ScoreCategory.TECHNICAL_QUALITY: 0.16,
            ScoreCategory.ARCHITECTURE: 0.10, ScoreCategory.JOB_RELEVANCE: 0.10,
            ScoreCategory.DOCUMENTATION: 0.04, ScoreCategory.SECURITY: 0.02,
            ScoreCategory.AI_UTILIZATION: 0.02,
        },
    ),
    EvaluationPolicy(
        name="Production-readiness",
        version=1,
        description="For senior hiring: testing, security and architecture carry the weight.",
        weights={
            ScoreCategory.TECHNICAL_QUALITY: 0.20, ScoreCategory.ARCHITECTURE: 0.20,
            ScoreCategory.TESTING: 0.18, ScoreCategory.SECURITY: 0.14,
            ScoreCategory.JOB_RELEVANCE: 0.10, ScoreCategory.OWNERSHIP: 0.08,
            ScoreCategory.DOCUMENTATION: 0.05, ScoreCategory.GIT_ENGINEERING: 0.03,
            ScoreCategory.AI_UTILIZATION: 0.02,
        },
    ),
)
