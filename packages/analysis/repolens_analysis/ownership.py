"""Ownership confidence and AI-utilization efficiency.

Ownership is the question RepoLens actually cares about: *does the evidence show
that this candidate built, understands and maintained this software?* It is
computed from positive evidence of engineering work, not from the absence of AI
signals.

The AI-utilization efficiency score answers a different question: *given that AI
was probably used, was it used well?* Low AI usage does not score highly here.
Effective augmentation — generated components that were integrated, tested,
verified and architecturally owned — is what scores highly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from repolens_shared import (
    AnalyzerResult,
    ConfidenceBand,
    Evidence,
    EvidenceDetail,
    ScoreCategory,
    Severity,
)
from repolens_shared.textutils import clamp, scale

from .git_history import HistorySignals

ANALYZER_NAME = "ownership"
ANALYZER_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class OwnershipFactor:
    id: str
    label: str
    weight: float
    positive_hint: str


#: Positive evidence of authorship. Weights sum to 1.0.
OWNERSHIP_FACTORS: tuple[OwnershipFactor, ...] = (
    OwnershipFactor("incremental_development", "Incremental development over time", 0.20,
                    "Multiple commits spread over multiple days."),
    OwnershipFactor("iteration_evidence", "Bug fixes and refactoring after the first version", 0.18,
                    "Commits that fix, refactor or optimise existing code."),
    OwnershipFactor("test_evolution", "Tests written for this codebase", 0.14,
                    "Test files that reference this project's own modules."),
    OwnershipFactor("project_specific_docs", "Documentation specific to this project", 0.12,
                    "A README that describes this project rather than a template."),
    OwnershipFactor("commit_quality", "Commit messages that describe intent", 0.12,
                    "Messages naming what changed and why."),
    OwnershipFactor("style_consistency", "Consistent style across the codebase", 0.08,
                    "One authorial voice across files."),
    OwnershipFactor("attribution", "Commits attributed to the candidate", 0.10,
                    "The candidate authored the majority of commits."),
    OwnershipFactor("candidate_explanation", "Candidate explained the code under questioning", 0.06,
                    "Technical verification answers consistent with the repository."),
)

#: Components of the AI-utilization efficiency score.
UTILIZATION_FACTORS: tuple[OwnershipFactor, ...] = (
    OwnershipFactor("delivery", "Working software was delivered", 0.15,
                    "A substantive, structured codebase exists."),
    OwnershipFactor("integration", "Generated components were integrated and modified", 0.20,
                    "Files changed again after they were first added."),
    OwnershipFactor("verification", "The result was verified", 0.22,
                    "Tests, CI and error handling are present."),
    OwnershipFactor("architectural_ownership", "Architecture is coherent and owned", 0.18,
                    "Recognisable layering, low coupling, no import cycles."),
    OwnershipFactor("understanding", "Understanding is demonstrable", 0.15,
                    "Project documentation and, where available, verification answers."),
    OwnershipFactor("dependency_discipline", "Dependencies are controlled", 0.10,
                    "Pinned, locked and proportionate to the project."),
)


@dataclass(slots=True)
class OwnershipInput:
    history: HistorySignals
    test_cases: int = 0
    test_files: int = 0
    references_own_modules: bool = False
    readme_words: int = 0
    readme_is_placeholder: bool = False
    readme_features: int = 0
    style_discontinuity: float = 0.0
    documented_function_ratio: float = 0.0
    candidate_is_author: bool | None = None
    verification_score: float | None = None
    file_rework_ratio: float | None = None
    source_file_count: int = 0

    # AI-utilization inputs
    architecture_score: float | None = None
    import_cycles: int = 0
    ci_runs_tests: bool = False
    error_handling_per_function: float = 0.0
    security_score: float | None = None
    dependency_score: float | None = None
    documentation_score: float | None = None
    ai_likelihood: float = 0.0


@dataclass(slots=True)
class FactorOutcome:
    factor: OwnershipFactor
    value: float  # 0..1
    observations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.factor.id,
            "label": self.factor.label,
            "weight": self.factor.weight,
            "value": round(self.value, 4),
            "contribution": round(self.value * self.factor.weight * 100, 2),
            "observations": self.observations[:4],
        }


def _ownership_factors(data: OwnershipInput) -> list[FactorOutcome]:
    history = data.history
    outcomes: list[FactorOutcome] = []

    # Incremental development
    if history.commit_count:
        value = (
            0.55 * clamp(scale(float(history.commit_count), 1.0, 40.0), 0, 100) / 100
            + 0.45 * clamp(scale(float(history.active_days), 1.0, 15.0), 0, 100) / 100
        )
        observations = [
            f"{history.commit_count} commits across {history.active_days} active day(s)",
            f"development span {history.span_days} day(s)",
        ]
    else:
        value, observations = 0.0, ["no commit history available"]
    outcomes.append(FactorOutcome(OWNERSHIP_FACTORS[0], value, observations))

    # Iteration evidence
    iteration_phases = {"bug_fixes", "refactoring", "optimization"}
    present = iteration_phases & set(history.phases_present)
    value = len(present) / len(iteration_phases)
    if history.evolution_score:
        value = max(value, history.evolution_score / 100.0 * 0.8)
    outcomes.append(FactorOutcome(
        OWNERSHIP_FACTORS[1], clamp(value, 0, 1),
        [f"evolution phases observed: {', '.join(history.phases_present) or 'none'}",
         f"engineering evolution score {history.evolution_score}"],
    ))

    # Test evolution
    value = 0.0
    observations = []
    if data.test_cases:
        value = 0.55 + (0.25 if data.references_own_modules else 0.0)
        value += 0.2 if "testing" in history.phases_present else 0.0
        observations.append(f"{data.test_cases} test case(s) in {data.test_files} file(s)")
        if data.references_own_modules:
            observations.append("tests import this project's own modules")
        if "testing" in history.phases_present:
            observations.append("test-related commits appear in the history")
    else:
        observations.append("no test cases detected")
    outcomes.append(FactorOutcome(OWNERSHIP_FACTORS[2], clamp(value, 0, 1), observations))

    # Project-specific documentation
    value = 0.0
    observations = []
    if data.readme_words:
        value = clamp(scale(float(data.readme_words), 30.0, 400.0), 0, 100) / 100 * 0.6
        value += min(0.4, data.readme_features * 0.05)
        if data.readme_is_placeholder:
            value *= 0.35
            observations.append("README retains scaffold/template text")
        observations.append(f"README is {data.readme_words} words covering {data.readme_features} sections")
    else:
        observations.append("no README found")
    outcomes.append(FactorOutcome(OWNERSHIP_FACTORS[3], clamp(value, 0, 1), observations))

    # Commit message quality
    value = history.message_quality
    observations = [f"message quality {history.message_quality:.2f}",
                    f"{history.low_effort_message_ratio * 100:.0f}% non-descriptive messages"]
    if history.conventional_commit_ratio > 0.4:
        value = min(1.0, value + 0.1)
        observations.append(
            f"{history.conventional_commit_ratio * 100:.0f}% follow a conventional-commit format")
    outcomes.append(FactorOutcome(OWNERSHIP_FACTORS[4], clamp(value, 0, 1), observations))

    # Style consistency
    value = clamp(1.0 - data.style_discontinuity, 0, 1)
    outcomes.append(FactorOutcome(
        OWNERSHIP_FACTORS[5], value,
        [f"style discontinuity {data.style_discontinuity:.2f} (0 = fully consistent)"],
    ))

    # Attribution
    if data.candidate_is_author is None and not history.commit_count:
        value, observations = 0.0, ["commit authorship could not be established"]
    else:
        value = history.candidate_commit_share
        observations = [
            f"{history.candidate_commit_share * 100:.0f}% of commits attributed to the candidate",
            "git authorship is self-reported and can be set to any value",
        ]
        if history.contributor_count > 1:
            observations.append(f"{history.contributor_count} distinct contributors in the history")
    outcomes.append(FactorOutcome(OWNERSHIP_FACTORS[6], clamp(value, 0, 1), observations))

    # Candidate explanation (technical verification)
    if data.verification_score is None:
        outcomes.append(FactorOutcome(
            OWNERSHIP_FACTORS[7], 0.0,
            ["no technical verification session has been completed for this repository"],
        ))
    else:
        outcomes.append(FactorOutcome(
            OWNERSHIP_FACTORS[7], clamp(data.verification_score / 100.0, 0, 1),
            [f"technical verification score {data.verification_score:.0f}/100"],
        ))
    return outcomes


def analyze_ownership(data: OwnershipInput) -> AnalyzerResult:
    """Compute ownership confidence from positive evidence of engineering work."""
    result = AnalyzerResult(analyzer=ANALYZER_NAME, version=ANALYZER_VERSION)
    outcomes = _ownership_factors(data)

    # Factors that could not be assessed are excluded from the denominator
    # rather than counted as zero — absence of data is not absence of ownership.
    unavailable = set()
    if not data.history.commit_count:
        unavailable |= {"incremental_development", "iteration_evidence", "commit_quality", "attribution"}
    if data.verification_score is None:
        unavailable.add("candidate_explanation")
    if data.source_file_count < 3:
        unavailable.add("style_consistency")

    scored = [o for o in outcomes if o.factor.id not in unavailable]
    weight_total = sum(o.factor.weight for o in scored) or 1.0
    confidence_score = 100.0 * sum(o.value * o.factor.weight for o in scored) / weight_total

    # Confidence in the *measurement*: how much of the evidence base was available.
    availability = sum(o.factor.weight for o in scored)
    measurement_confidence = clamp(0.3 + 0.7 * availability, 0.0, 0.95)

    result.score = round(clamp(confidence_score), 2)
    result.confidence = round(measurement_confidence, 3)
    result.metrics = {
        "ownership_confidence": round(confidence_score, 2),
        "confidence_band": str(ConfidenceBand.from_value(measurement_confidence)),
        "factors": [o.to_dict() for o in outcomes],
        "unavailable_factors": sorted(unavailable),
        "evidence_availability": round(availability, 3),
    }

    strengths = [o for o in scored if o.value >= 0.6]
    weaknesses = [o for o in scored if o.value < 0.35]

    if strengths:
        result.add(Evidence(
            category=ScoreCategory.OWNERSHIP,
            claim=f"Ownership confidence {confidence_score:.0f}% — "
                  f"{len(strengths)} ownership factor(s) are well evidenced",
            severity=Severity.INFO, confidence=measurement_confidence, supports="strength",
            tags=("ownership",),
            evidence=tuple(
                EvidenceDetail(detail=f"{o.factor.label}: {o.observations[0] if o.observations else 'present'}",
                               metric=o.value)
                for o in sorted(strengths, key=lambda x: -x.value * x.factor.weight)[:6]
            ),
        ))
    if weaknesses:
        result.add(Evidence(
            category=ScoreCategory.OWNERSHIP,
            claim=f"{len(weaknesses)} ownership factor(s) lack supporting evidence",
            severity=Severity.MEDIUM if confidence_score < 55 else Severity.LOW,
            confidence=measurement_confidence, supports="weakness", tags=("ownership",),
            evidence=tuple(
                EvidenceDetail(detail=f"{o.factor.label}: {o.observations[0] if o.observations else 'not evidenced'}",
                               metric=o.value)
                for o in sorted(weaknesses, key=lambda x: x.value)[:6]
            ),
        ))
    if unavailable:
        result.partial = True
        result.limit(
            "ownership_evidence",
            "These factors could not be assessed and were excluded from the calculation rather than "
            f"scored as zero: {', '.join(sorted(unavailable))}.",
        )
    result.limit(
        "ownership_scope",
        "Ownership confidence measures the evidence visible in the repository. Low confidence means "
        "the evidence is thin, not that the candidate did not write the code.",
    )
    return result


def analyze_ai_utilization(data: OwnershipInput, ownership_confidence: float) -> AnalyzerResult:
    """Score how *productively* AI appears to have been used.

    This is explicitly not a measure of how little AI was used: a repository with
    strong assistance signals and strong verification, integration and
    architectural ownership scores highly.
    """
    result = AnalyzerResult(analyzer="ai_utilization", version=ANALYZER_VERSION)
    outcomes: list[FactorOutcome] = []

    # Delivery
    delivery = clamp(scale(float(data.source_file_count), 0.0, 25.0), 0, 100) / 100
    outcomes.append(FactorOutcome(UTILIZATION_FACTORS[0], delivery,
                                  [f"{data.source_file_count} source file(s) delivered"]))

    # Integration: did the code change after it first appeared?
    if data.file_rework_ratio is None:
        integration = clamp(len({"refactoring", "bug_fixes"} & set(data.history.phases_present)) / 2.0, 0, 1)
        integration_notes = ["measured from commit intent: "
                             f"{', '.join(data.history.phases_present) or 'no iteration commits'}"]
    else:
        integration = clamp(data.file_rework_ratio / 0.5, 0, 1)
        integration_notes = [f"{data.file_rework_ratio * 100:.0f}% of files were modified in a later commit"]
    outcomes.append(FactorOutcome(UTILIZATION_FACTORS[1], integration, integration_notes))

    # Verification
    verification = 0.0
    notes: list[str] = []
    if data.test_cases:
        verification += 0.45
        notes.append(f"{data.test_cases} test case(s)")
    if data.ci_runs_tests:
        verification += 0.25
        notes.append("CI runs the test suite")
    if data.error_handling_per_function >= 0.05:
        verification += 0.15
        notes.append(f"{data.error_handling_per_function:.2f} error-handling constructs per function")
    if data.security_score is not None and data.security_score >= 70:
        verification += 0.15
        notes.append(f"security analysis score {data.security_score:.0f}")
    if not notes:
        notes.append("no tests, CI or systematic error handling detected")
    outcomes.append(FactorOutcome(UTILIZATION_FACTORS[2], clamp(verification, 0, 1), notes))

    # Architectural ownership
    architecture = (data.architecture_score or 0.0) / 100.0
    if data.import_cycles:
        architecture *= 0.85
    outcomes.append(FactorOutcome(
        UTILIZATION_FACTORS[3], clamp(architecture, 0, 1),
        [f"architecture score {data.architecture_score:.0f}" if data.architecture_score is not None
         else "architecture score unavailable",
         f"{data.import_cycles} import cycle(s)"],
    ))

    # Understanding
    understanding = (data.documentation_score or 0.0) / 100.0 * 0.6
    if data.verification_score is not None:
        understanding += data.verification_score / 100.0 * 0.4
        understanding_notes = [f"technical verification score {data.verification_score:.0f}/100"]
    else:
        understanding = understanding / 0.6 * 0.6  # documentation carries it alone
        understanding_notes = ["no technical verification session completed; "
                               "understanding inferred from documentation only"]
    outcomes.append(FactorOutcome(UTILIZATION_FACTORS[4], clamp(understanding, 0, 1), understanding_notes))

    # Dependency discipline
    dependency = (data.dependency_score or 50.0) / 100.0
    outcomes.append(FactorOutcome(
        UTILIZATION_FACTORS[5], clamp(dependency, 0, 1),
        [f"dependency hygiene score {data.dependency_score:.0f}" if data.dependency_score is not None
         else "no dependency manifest to assess"],
    ))

    score = 100.0 * sum(o.value * o.factor.weight for o in outcomes)

    # Where assistance signals are strong AND ownership is strong, the candidate
    # is demonstrably getting leverage from the tool. That is rewarded.
    leverage_bonus = 0.0
    if data.ai_likelihood >= 45 and ownership_confidence >= 65 and score >= 55:
        leverage_bonus = 6.0
    score = clamp(score + leverage_bonus)

    classification = (
        "Effective AI Augmentation" if score >= 75
        else "Productive, With Gaps" if score >= 55
        else "Verification Recommended" if score >= 35
        else "Insufficient Evidence of Productive Use"
    )

    result.score = round(score, 2)
    result.confidence = 0.65
    result.metrics = {
        "ai_utilization_efficiency": round(score, 2),
        "classification": classification,
        "leverage_bonus": leverage_bonus,
        "factors": [o.to_dict() for o in outcomes],
    }

    result.add(Evidence(
        category=ScoreCategory.AI_UTILIZATION,
        claim=f"AI utilization efficiency {score:.0f}/100 — {classification}",
        severity=Severity.INFO, confidence=0.65,
        supports="strength" if score >= 65 else "weakness", tags=("ai_utilization",),
        evidence=(
            *(
                EvidenceDetail(detail=f"{o.factor.label}: {o.observations[0] if o.observations else '-'}",
                               metric=o.value)
                for o in sorted(outcomes, key=lambda x: -x.value * x.factor.weight)[:5]
            ),
            EvidenceDetail(
                detail="This score measures whether AI appears to have been used productively while "
                       "preserving engineering ownership. It does not reward low AI usage."),
        ),
    ))
    if leverage_bonus:
        result.add(Evidence(
            category=ScoreCategory.AI_UTILIZATION,
            claim="Strong assistance signals combined with strong ownership evidence",
            severity=Severity.INFO, confidence=0.6, supports="strength",
            tags=("ai_utilization", "leverage"),
            evidence=(
                EvidenceDetail(detail=f"assistance likelihood {data.ai_likelihood:.0f}/100"),
                EvidenceDetail(detail=f"ownership confidence {ownership_confidence:.0f}%"),
                EvidenceDetail(detail="The candidate appears to have used assistance to deliver more "
                                      "while retaining ownership of the result."),
            ),
        ))
    result.limit(
        "ai_utilization",
        "Efficiency is inferred from repository artefacts. A technical verification session provides "
        "far stronger evidence of understanding than any static signal.",
    )
    return result
