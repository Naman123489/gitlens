"""AI-assistance likelihood estimation.

**Read this before changing anything here.**

There is no reliable way to determine from source code alone that a particular
line was produced by a language model. This module therefore does not try. It
estimates a *likelihood* from a set of named, individually weak signals, and it
reports:

* the estimated likelihood (0-100),
* a confidence band,
* every signal that fired, with the observation behind it,
* the limitations of the method.

Design rules that must not be broken:

1. No signal may be described as proof.
2. A high likelihood never becomes a negative judgement on its own. It is
   combined with ownership evidence, and the worst outcome is
   ``VERIFICATION_REQUIRED`` — a request for a conversation.
3. AI use is not misconduct. The efficiency score below rewards *effective* use.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Any

from repolens_shared import (
    AIUsageClassification,
    AnalyzerResult,
    ConfidenceBand,
    Evidence,
    EvidenceDetail,
    ScoreCategory,
    Severity,
)
from repolens_shared.textutils import clamp

from .ast_engine import FileAST
from .git_history import HistorySignals
from .style import StyleProfile, profile_file, style_discontinuity

ANALYZER_NAME = "ai_usage"
ANALYZER_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class SignalDefinition:
    id: str
    label: str
    weight: float
    description: str
    caveat: str


#: Every signal that can contribute to the likelihood estimate. Weights sum to
#: 1.0 so the estimate is a weighted mean of normalised signal strengths.
SIGNAL_DEFINITIONS: tuple[SignalDefinition, ...] = (
    SignalDefinition(
        "history_shape", "Repository appeared with little incremental history", 0.20,
        "Most of the code arrived in one or very few commits with no iteration afterwards.",
        "Importing existing work in one commit, or squashing history, produces the same shape.",
    ),
    SignalDefinition(
        "style_discontinuity", "Style discontinuity between files", 0.14,
        "Some files differ sharply from the repository's own style baseline.",
        "A second contributor, a copied module or an editor's auto-format produce the same effect.",
    ),
    SignalDefinition(
        "uniform_documentation", "Uniform, exhaustive documentation on trivial code", 0.14,
        "Nearly every function carries a full structured docstring, including trivial ones, "
        "while project-level documentation is comparatively thin.",
        "Disciplined developers and docstring linters also produce uniformly documented code.",
    ),
    SignalDefinition(
        "boilerplate_repetition", "Repetitive near-identical implementations", 0.12,
        "Multiple functions share an identical shape with only names changed.",
        "Code generators, framework conventions and CRUD scaffolding do the same.",
    ),
    SignalDefinition(
        "abstraction_inconsistency", "Inconsistent abstraction level", 0.12,
        "Sophisticated constructs sit beside markedly naive ones in the same codebase.",
        "Normal in a codebase written over a long period or while learning.",
    ),
    SignalDefinition(
        "assistant_artifacts", "Assistant-style artefacts left in the source", 0.16,
        "Explanatory prose, placeholder markers or tutorial-style narration typical of "
        "generated-then-pasted code.",
        "Copied documentation and tutorial code produce identical artefacts.",
    ),
    SignalDefinition(
        "growth_bursts", "Large code volume added in very short periods", 0.12,
        "Days where the repository grew by many times its own median daily change.",
        "A focused work session, a merge or a vendored import look the same.",
    ),
)

#: Textual artefacts frequently left behind when generated code is pasted in.
ARTIFACT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("narration", re.compile(r"(?im)^\s*(?://|#)\s*(?:here'?s|this (?:function|method|code|class) "
                             r"(?:will|is used to|does)|note that|let'?s|we (?:will|need to|can))\b")),
    ("step_markers", re.compile(r"(?im)^\s*(?://|#)\s*(?:step\s*\d+|\d+\.\s+[A-Z])")),
    ("placeholder_impl", re.compile(r"(?im)^\s*(?://|#)\s*(?:your (?:code|implementation|logic) here|"
                                    r"implement(?:ation)? (?:goes )?here|add your|replace (?:this|with)|"
                                    r"rest of the (?:code|implementation)|\.\.\. *(?:existing|rest))")),
    ("example_usage_block", re.compile(r"(?im)^\s*(?://|#)\s*example usage\s*:?\s*$")),
    ("markdown_fence_in_code", re.compile(r"(?m)^\s*```")),
    ("apology_or_meta", re.compile(r"(?im)^\s*(?://|#)\s*(?:as an ai|i cannot|i'?m sorry|"
                                   r"certainly[,!]|of course[,!]|feel free to)")),
    ("emoji_section_comment", re.compile(r"(?m)^\s*(?://|#)\s*[\U0001F300-\U0001FAFF✀-➿]")),
)

_STRUCTURED_DOCSTRING = re.compile(
    r"(?:Args?|Arguments|Parameters|Params|Returns?|Raises?|Yields?|Attributes)\s*:", re.M
)


@dataclass(slots=True)
class AIUsageInput:
    asts: list[FileAST]
    texts: dict[str, str]
    categories: dict[str, str]
    history: HistorySignals
    duplication_ratio: float = 0.0
    structural_clone_groups: int = 0
    documented_function_ratio: float = 0.0
    readme_words: int = 0
    test_cases: int = 0
    complexity_values: list[float] = field(default_factory=list)


@dataclass(slots=True)
class SignalOutcome:
    definition: SignalDefinition
    strength: float  # 0..1
    observations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.definition.id,
            "label": self.definition.label,
            "weight": self.definition.weight,
            "strength": round(self.strength, 4),
            "description": self.definition.description,
            "caveat": self.definition.caveat,
            "observations": self.observations[:5],
        }


def _history_signal(history: HistorySignals) -> SignalOutcome:
    definition = SIGNAL_DEFINITIONS[0]
    observations: list[str] = []
    if not history.commit_count:
        return SignalOutcome(definition, 0.0, ["no git history available"])

    strength = 0.0
    if history.single_commit_repository:
        strength = 0.85
        observations.append("the repository has a single commit")
    else:
        if history.largest_commit_share > 0.7:
            strength = max(strength, 0.6)
            observations.append(
                f"one commit accounts for {history.largest_commit_share * 100:.0f}% of all changed lines")
        if history.active_days <= 2 and history.commit_count < 15:
            strength = max(strength, 0.5)
            observations.append(f"development spans only {history.active_days} active day(s)")
        if not history.phases_present or history.phases_present == ["initial_implementation"]:
            strength = max(strength, 0.45)
            observations.append("no bug-fix, refactoring or test commits follow the initial implementation")
    if history.commit_count > 40 and history.active_days > 10:
        strength = min(strength, 0.2)
        observations.append(
            f"{history.commit_count} commits across {history.active_days} active days indicate iteration")
    return SignalOutcome(definition, strength, observations)


def _style_signal(profiles: list[StyleProfile]) -> SignalOutcome:
    definition = SIGNAL_DEFINITIONS[1]
    discontinuity, deviations = style_discontinuity(profiles)
    observations = [f"{path} deviates {value}σ from the repository style baseline"
                    for path, value in deviations[:4] if value > 1.5]
    if not observations and discontinuity == 0.0 and len(profiles) >= 3:
        observations.append("style is consistent across analysed files")
    return SignalOutcome(definition, discontinuity, observations)


def _documentation_signal(data: AIUsageInput) -> SignalOutcome:
    definition = SIGNAL_DEFINITIONS[2]
    functions = [e for a in data.asts for e in a.functions]
    if len(functions) < 5:
        return SignalOutcome(definition, 0.0, ["too few functions to assess documentation uniformity"])

    trivial = [e for e in functions if e.line_count <= 4 and e.complexity == 1]
    documented_trivial = sum(1 for e in trivial if e.has_doc)
    trivial_doc_ratio = documented_trivial / len(trivial) if trivial else 0.0

    structured = sum(len(_STRUCTURED_DOCSTRING.findall(text)) for text in data.texts.values())
    structured_ratio = min(1.0, structured / max(1, len(functions)))

    strength = 0.0
    observations: list[str] = []
    if data.documented_function_ratio > 0.9 and trivial_doc_ratio > 0.85 and trivial:
        strength = 0.6
        observations.append(
            f"{documented_trivial} of {len(trivial)} trivial functions carry full docstrings")
    if structured_ratio > 0.8:
        strength = max(strength, 0.55)
        observations.append(
            f"structured Args/Returns sections appear in ~{structured_ratio * 100:.0f}% of functions")
    if strength and data.readme_words < 120:
        strength = min(1.0, strength + 0.2)
        observations.append(
            f"project README is only {data.readme_words} words despite exhaustive inline documentation")
    if not observations:
        observations.append("documentation density is within normal ranges")
    return SignalOutcome(definition, strength, observations)


def _boilerplate_signal(data: AIUsageInput) -> SignalOutcome:
    definition = SIGNAL_DEFINITIONS[3]
    observations: list[str] = []
    strength = 0.0
    if data.structural_clone_groups >= 3:
        strength = min(0.8, 0.2 + data.structural_clone_groups * 0.1)
        observations.append(f"{data.structural_clone_groups} groups of structurally identical functions")
    if data.duplication_ratio > 0.15:
        strength = max(strength, min(0.7, data.duplication_ratio * 2.5))
        observations.append(f"{data.duplication_ratio * 100:.0f}% of code blocks are duplicated")
    if not observations:
        observations.append("no unusual repetition detected")
    return SignalOutcome(definition, strength, observations)


def _abstraction_signal(data: AIUsageInput) -> SignalOutcome:
    definition = SIGNAL_DEFINITIONS[4]
    per_file_complexity = [
        statistics.mean([e.complexity for e in a.functions])
        for a in data.asts if len(a.functions) >= 2
    ]
    if len(per_file_complexity) < 4:
        return SignalOutcome(definition, 0.0, ["too few files to assess abstraction consistency"])
    mean = statistics.mean(per_file_complexity)
    spread = statistics.pstdev(per_file_complexity)
    coefficient = spread / mean if mean else 0.0
    strength = clamp((coefficient - 0.55) / 0.9, 0.0, 1.0)
    observations = [
        f"per-file mean complexity varies with a coefficient of variation of {coefficient:.2f}"
    ]
    if strength > 0.3:
        extremes = sorted(
            ((a.path, statistics.mean([e.complexity for e in a.functions]))
             for a in data.asts if len(a.functions) >= 2),
            key=lambda item: item[1],
        )
        observations.append(f"simplest module: {extremes[0][0]} (mean complexity {extremes[0][1]:.1f})")
        observations.append(f"most complex module: {extremes[-1][0]} (mean complexity {extremes[-1][1]:.1f})")
    return SignalOutcome(definition, strength, observations)


def _artifact_signal(data: AIUsageInput) -> SignalOutcome:
    definition = SIGNAL_DEFINITIONS[5]
    hits: dict[str, list[str]] = {}
    for path, text in data.texts.items():
        if data.categories.get(path) not in ("CANDIDATE_CODE", "TEST_CODE"):
            continue
        for name, pattern in ARTIFACT_PATTERNS:
            for match in list(pattern.finditer(text))[:2]:
                line = text.count("\n", 0, match.start()) + 1
                hits.setdefault(name, []).append(f"{path}:{line} — {match.group(0).strip()[:80]}")
    total = sum(len(v) for v in hits.values())
    source_files = max(1, sum(1 for c in data.categories.values() if c == "CANDIDATE_CODE"))
    density = total / source_files
    strength = clamp(density / 0.8, 0.0, 1.0) if total else 0.0
    observations = [item for items in hits.values() for item in items][:5]
    if not observations:
        observations.append("no assistant-style artefacts found in source comments")
    return SignalOutcome(definition, strength, observations)


def _burst_signal(history: HistorySignals) -> SignalOutcome:
    definition = SIGNAL_DEFINITIONS[6]
    if not history.commit_count:
        return SignalOutcome(definition, 0.0, ["no git history available"])
    if not history.burst_days:
        return SignalOutcome(definition, 0.0, ["daily change volume is within normal variation"])
    strength = clamp(len(history.burst_days) / 4.0, 0.0, 0.8)
    return SignalOutcome(
        definition, strength,
        [f"unusually large change volume on {day}" for day in history.burst_days[:4]],
    )


def classify(likelihood: float, ownership_confidence: float | None) -> AIUsageClassification:
    """Map likelihood + ownership evidence onto a classification.

    Ownership is what separates "used AI well" from "cannot show ownership".
    With no ownership evidence available the result is
    ``INSUFFICIENT_EVIDENCE``, never a negative classification.
    """
    if ownership_confidence is None:
        return AIUsageClassification.INSUFFICIENT_EVIDENCE
    if likelihood < 35:
        return AIUsageClassification.AI_ASSISTED
    if likelihood < 60:
        return (AIUsageClassification.AI_ASSISTED if ownership_confidence >= 75
                else AIUsageClassification.AI_AUGMENTED)
    if likelihood < 78:
        if ownership_confidence >= 70:
            return AIUsageClassification.AI_AUGMENTED
        return AIUsageClassification.AI_DEPENDENT
    if ownership_confidence >= 70:
        return AIUsageClassification.AI_AUGMENTED
    if ownership_confidence >= 45:
        return AIUsageClassification.AI_DEPENDENT
    return AIUsageClassification.AI_DOMINATED


CLASSIFICATION_DESCRIPTIONS: dict[AIUsageClassification, str] = {
    AIUsageClassification.AI_ASSISTED:
        "Signals are consistent with AI used for support tasks — debugging, boilerplate, "
        "documentation, test scaffolding — with the candidate demonstrating ownership.",
    AIUsageClassification.AI_AUGMENTED:
        "Signals suggest AI generated meaningful components which the candidate then integrated, "
        "modified and maintained.",
    AIUsageClassification.AI_DEPENDENT:
        "A substantial share of the code carries assistance signals and the available ownership "
        "evidence is limited. A conversation with the candidate is recommended.",
    AIUsageClassification.AI_DOMINATED:
        "The available evidence suggests substantial dependence on generated code with limited "
        "evidence of candidate-authored development. This is a prompt for verification, not a "
        "conclusion about the candidate.",
    AIUsageClassification.INSUFFICIENT_EVIDENCE:
        "There was not enough evidence to characterise how this repository was built.",
}


def analyze_ai_usage(
    data: AIUsageInput, ownership_confidence: float | None = None
) -> AnalyzerResult:
    """Estimate AI-assistance likelihood. Never asserts authorship."""
    result = AnalyzerResult(analyzer=ANALYZER_NAME, version=ANALYZER_VERSION)

    profiles = [
        profile_file(a, data.texts[a.path])
        for a in data.asts
        if a.path in data.texts and data.categories.get(a.path) == "CANDIDATE_CODE"
    ]

    outcomes = [
        _history_signal(data.history),
        _style_signal(profiles),
        _documentation_signal(data),
        _boilerplate_signal(data),
        _abstraction_signal(data),
        _artifact_signal(data),
        _burst_signal(data.history),
    ]

    likelihood = 100.0 * sum(o.strength * o.definition.weight for o in outcomes)
    firing = [o for o in outcomes if o.strength > 0.05]

    # Confidence in the *estimate*, not in an authorship claim. It rises with the
    # amount of evidence available and falls when the inputs are thin.
    evidence_breadth = len(firing) / len(outcomes)
    data_quality = 0.0
    data_quality += 0.35 if data.history.commit_count >= 5 else (0.1 if data.history.commit_count else 0.0)
    data_quality += 0.25 if len(profiles) >= 5 else (0.1 if profiles else 0.0)
    data_quality += 0.2 if sum(len(a.functions) for a in data.asts) >= 20 else 0.05
    data_quality += 0.2 if data.texts else 0.0
    confidence = clamp(0.25 + 0.4 * data_quality + 0.25 * evidence_breadth, 0.0, 0.8)

    classification = classify(likelihood, ownership_confidence)

    result.score = None  # The AI-utilization *score* is computed separately.
    result.confidence = round(confidence, 3)
    result.metrics = {
        "estimated_ai_assistance": round(likelihood, 1),
        "confidence": round(confidence, 3),
        "confidence_band": str(ConfidenceBand.from_value(confidence)),
        "classification": str(classification),
        "classification_description": CLASSIFICATION_DESCRIPTIONS[classification],
        "ownership_confidence_used": ownership_confidence,
        "signals": [o.to_dict() for o in outcomes],
        "style_profiles_analysed": len(profiles),
    }

    result.add(Evidence(
        category=ScoreCategory.AI_UTILIZATION,
        claim=f"Estimated AI-assistance likelihood {likelihood:.0f}/100 "
              f"({ConfidenceBand.from_value(confidence)} confidence)",
        severity=Severity.INFO,
        confidence=confidence,
        supports="neutral",
        tags=("ai_usage", "probabilistic", "signal_only"),
        evidence=(
            *(
                EvidenceDetail(detail=f"{o.definition.label} (weight {o.definition.weight}, "
                                      f"strength {o.strength:.2f}): {o.observations[0]}",
                               metric=o.strength)
                for o in sorted(firing, key=lambda x: -x.strength * x.definition.weight)[:5]
            ),
            EvidenceDetail(
                detail="This is a probabilistic estimate built from weak individual signals. "
                       "It is not a determination that any code was AI-generated."),
        ),
    ))

    for outcome in sorted(firing, key=lambda x: -x.strength * x.definition.weight)[:4]:
        result.add(Evidence(
            category=ScoreCategory.AI_UTILIZATION,
            claim=outcome.definition.label,
            severity=Severity.LOW,
            confidence=round(min(0.7, confidence + 0.1), 3),
            supports="neutral",
            tags=("ai_usage", "signal_only", outcome.definition.id),
            evidence=(
                *(EvidenceDetail(detail=observation) for observation in outcome.observations[:3]),
                EvidenceDetail(detail=f"Alternative explanation: {outcome.definition.caveat}"),
            ),
        ))

    result.limit(
        "ai_detection",
        "AI-generated code cannot be conclusively identified from source code alone. Every signal "
        "used here has legitimate non-AI explanations, which are listed alongside each signal.",
    )
    result.limit(
        "not_a_judgement",
        "AI assistance is not misconduct. This estimate exists to contextualise ownership evidence, "
        "never to justify rejecting a candidate.",
    )
    if not data.history.commit_count:
        result.partial = True
        result.limit("ai_detection_inputs",
                     "No commit history was available; development-timeline signals could not be used.")
    if len(profiles) < 3:
        result.limit("ai_detection_inputs",
                     "Fewer than three source files were available; style-consistency signals are weak.")
    return result
