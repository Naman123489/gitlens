"""The scoring engine.

Deterministic by construction: it takes analyzer outputs, a policy and a set of
signals, and produces the final evaluation. No model is consulted here, and no
code path lets an LLM set a number.

Two behaviours are worth calling out:

* **Unavailable categories are renormalised, not zeroed.** If the security
  analyzer failed, security is excluded from the weighting and the evaluation is
  marked incomplete for that dimension. Scoring a failure as zero would invent a
  finding.
* **Verification status is advisory.** The worst outcome is
  ``VERIFICATION_REQUIRED``, which asks a human to have a conversation. Nothing
  here rejects anybody.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from repolens_shared import (
    AIUsageClassification,
    AnalyzerResult,
    CategoryScore,
    ConfidenceBand,
    Evidence,
    OriginalityClassification,
    RunVersions,
    ScoreCategory,
    VerificationStatus,
)
from repolens_shared.textutils import clamp

from .policy import DEFAULT_POLICY, EvaluationPolicy

ENGINE_VERSION = "1.0.0"


@dataclass(slots=True)
class AnalyzerFailure:
    """Recorded when an analyzer could not run. Never replaced with a guess."""

    analyzer: str
    category: ScoreCategory | None
    reason: str
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "analyzer": self.analyzer,
            "category": str(self.category) if self.category else None,
            "reason": self.reason,
            "occurred_at": self.occurred_at,
        }


@dataclass(slots=True)
class VerificationSignals:
    """Inputs to the verification-status decision."""

    ownership_confidence: float | None = None
    ai_likelihood: float | None = None
    ai_classification: AIUsageClassification | None = None
    max_external_similarity: float | None = None
    originality: OriginalityClassification | None = None
    resume_gaps: int = 0
    analysis_complete: bool = True
    disclosure_provided: bool = False


@dataclass(slots=True)
class ScoredEvaluation:
    overall_score: float | None
    confidence: float
    scores: list[CategoryScore]
    evidence: list[Evidence]
    limitations: list[dict[str, str]]
    verification_status: VerificationStatus
    verification_reasons: list[str]
    policy: dict[str, Any]
    versions: dict[str, Any]
    failures: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 2) if self.overall_score is not None else None,
            "confidence": round(self.confidence, 4),
            "confidence_band": str(ConfidenceBand.from_value(self.confidence)),
            "scores": [s.to_dict() for s in self.scores],
            "evidence": [
                {"id": e.evidence_id(), **e.to_dict()} for e in self.evidence
            ],
            "limitations": self.limitations,
            "verification_status": str(self.verification_status),
            "verification_reasons": self.verification_reasons,
            "policy": self.policy,
            "versions": self.versions,
            "failures": self.failures,
            "metrics": self.metrics,
        }


def build_category_scores(
    results: dict[ScoreCategory, AnalyzerResult | None],
    failures: list[AnalyzerFailure],
) -> list[CategoryScore]:
    """Turn analyzer results into category scores, linking their evidence ids."""
    failure_by_category = {f.category: f for f in failures if f.category}
    scores: list[CategoryScore] = []
    for category in ScoreCategory:
        result = results.get(category)
        if result is None or result.score is None:
            failure = failure_by_category.get(category)
            reason = (
                failure.reason if failure
                else (result.limitations[0].detail if result and result.limitations
                      else "analyzer produced no score for this category")
            )
            scores.append(CategoryScore(
                category=category, score=0.0, confidence=0.0,
                available=False, unavailable_reason=reason,
            ))
            continue
        evidence_ids = tuple(
            e.evidence_id() for e in result.evidence if e.category == category
        )
        scores.append(CategoryScore(
            category=category, score=clamp(result.score), confidence=result.confidence,
            evidence_ids=evidence_ids, available=True,
        ))
    return scores


def decide_verification_status(
    signals: VerificationSignals, policy: EvaluationPolicy, available_categories: int
) -> tuple[VerificationStatus, list[str]]:
    """Decide the advisory verification status.

    Returns the status and the human-readable reasons behind it. The reasons are
    phrased as things to check, never as accusations.
    """
    thresholds = policy.thresholds
    reasons: list[str] = []
    needs_verification = False
    needs_review = False

    if not signals.analysis_complete or available_categories < thresholds.min_available_categories:
        return (
            VerificationStatus.ANALYSIS_INCOMPLETE,
            [
                f"Only {available_categories} scoring categories could be computed "
                f"(minimum {thresholds.min_available_categories}). Re-run the analysis or "
                "review the analyzer failures before drawing conclusions."
            ],
        )

    ownership = signals.ownership_confidence
    if ownership is not None:
        if ownership < thresholds.ownership_verification_below:
            needs_verification = True
            reasons.append(
                f"Ownership evidence is insufficient ({ownership:.0f}% confidence). "
                "The repository does not show enough development history, tests or iteration to "
                "establish authorship from artefacts alone."
            )
        elif ownership < thresholds.ownership_review_below:
            needs_review = True
            reasons.append(
                f"Ownership evidence is limited ({ownership:.0f}% confidence). A short technical "
                "conversation would resolve it."
            )

    similarity = signals.max_external_similarity
    if similarity is not None:
        if similarity >= thresholds.external_similarity_verification_above:
            needs_verification = True
            reasons.append(
                f"Code closely matching another analysed repository was found "
                f"(similarity {similarity:.2f}). Shared open-source ancestry is the most common "
                "explanation; ask the candidate about the overlap."
            )
        elif similarity >= thresholds.external_similarity_review_above:
            needs_review = True
            reasons.append(
                f"Moderate similarity to another analysed repository (similarity {similarity:.2f})."
            )

    if signals.originality == OriginalityClassification.STRONG_TUTORIAL_SIMILARITY:
        needs_verification = True
        reasons.append(
            "Repository contains strong similarity to publicly available tutorial or scaffold "
            "patterns. A candidate explanation is recommended."
        )
    elif signals.originality == OriginalityClassification.POSSIBLY_TUTORIAL_DERIVED:
        needs_review = True
        reasons.append("Some scaffold or tutorial-derived material appears to remain unmodified.")

    likelihood = signals.ai_likelihood
    if likelihood is not None and likelihood >= thresholds.ai_likelihood_review_above:
        if signals.ai_classification in (AIUsageClassification.AI_DEPENDENT,
                                         AIUsageClassification.AI_DOMINATED):
            needs_verification = True
            reasons.append(
                f"AI-assistance signals are strong ({likelihood:.0f}/100) and ownership evidence is "
                "limited. This is a prompt to verify understanding, not a finding of misconduct — "
                "AI-assisted development is legitimate."
            )
        elif not signals.disclosure_provided:
            needs_review = True
            reasons.append(
                f"AI-assistance signals are present ({likelihood:.0f}/100) and the candidate has "
                "not recorded a disclosure. Inviting a disclosure usually resolves this."
            )

    if signals.resume_gaps > thresholds.resume_gap_review_above:
        needs_review = True
        reasons.append(
            f"{signals.resume_gaps} claimed skill(s) on the résumé have no supporting repository "
            "evidence. Repository evidence is partial by nature; verification is recommended."
        )

    if needs_verification:
        return VerificationStatus.VERIFICATION_REQUIRED, reasons
    if needs_review:
        return VerificationStatus.REVIEW_RECOMMENDED, reasons
    return VerificationStatus.CLEAR, reasons or [
        "No ownership, similarity or completeness concerns were raised by the analysis."
    ]


def score_evaluation(
    results: dict[ScoreCategory, AnalyzerResult | None],
    signals: VerificationSignals,
    policy: EvaluationPolicy = DEFAULT_POLICY,
    failures: list[AnalyzerFailure] | None = None,
    versions: RunVersions | None = None,
) -> ScoredEvaluation:
    """Combine analyzer output into a final, explainable evaluation."""
    failures = failures or []
    versions = versions or RunVersions(policy_version=policy.version)
    scores = build_category_scores(results, failures)
    weights = policy.normalised_weights()

    available = [s for s in scores if s.available and s.category in weights]
    weight_sum = sum(weights[s.category] for s in available)

    if available and weight_sum > 0:
        overall = sum(s.score * weights[s.category] for s in available) / weight_sum
        # Confidence in the overall number is the weighted mean of the confidence
        # of the parts, discounted by how much of the policy weight was available.
        coverage = weight_sum / sum(weights.values())
        part_confidence = sum(s.confidence * weights[s.category] for s in available) / weight_sum
        confidence = clamp(part_confidence * (0.55 + 0.45 * coverage), 0.0, 1.0)
    else:
        overall = None
        confidence = 0.0

    status, reasons = decide_verification_status(signals, policy, len(available))

    evidence: list[Evidence] = []
    limitations: list[dict[str, str]] = []
    for result in results.values():
        if result is None:
            continue
        evidence.extend(result.evidence)
        limitations.extend(
            {"scope": l.scope, "detail": l.detail, "analyzer": result.analyzer}
            for l in result.limitations
        )

    return ScoredEvaluation(
        overall_score=overall,
        confidence=confidence,
        scores=scores,
        evidence=evidence,
        limitations=limitations,
        verification_status=status,
        verification_reasons=reasons,
        policy=policy.to_dict(),
        versions={**versions.to_dict(), "scoring_engine": ENGINE_VERSION},
        failures=[f.to_dict() for f in failures],
        metrics={
            "categories_available": len(available),
            "categories_total": len(weights),
            "policy_weight_coverage": round(weight_sum / sum(weights.values()), 4) if weights else 0.0,
            "ownership_confidence": signals.ownership_confidence,
            "ai_likelihood": signals.ai_likelihood,
            "ai_classification": str(signals.ai_classification) if signals.ai_classification else None,
            "max_external_similarity": signals.max_external_similarity,
            "originality": str(signals.originality) if signals.originality else None,
        },
    )
