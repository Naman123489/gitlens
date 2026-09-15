"""Job relevance matching.

Computes, for every requirement in a parsed job, how strongly the repository
*evidences* that skill, and from that a job-match percentage. Every contribution
is traceable: each matched skill carries the concrete artefacts that produced it.

Evidence sources are deliberately ranked. A dependency declared in a manifest
and imported in source is strong evidence; the same word appearing in a README
is weak evidence, because anyone can write a word in a README.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from repolens_shared import (
    AnalyzerResult,
    Evidence,
    EvidenceDetail,
    ScoreCategory,
    Severity,
    SkillDimension,
)
from repolens_shared.textutils import clamp

from .jd_parser import ParsedJob
from .taxonomy import SKILLS_BY_KEY, Skill, extract_skills

#: Human-readable explanations for pipeline-observed signals.
_SIGNAL_LABELS: dict[str, str] = {
    "git": "commit history is present and was analysed",
    "testing": "automated test cases were found and counted",
    "ci_cd": "a CI workflow was found in the repository",
    "docker": "a Dockerfile or compose file was found",
    "rest_api": "HTTP route definitions were found in source",
    "security": "authentication or cryptography code was found in source",
    "open_source": "contribution guidelines were found",
    "research": "notebooks or experiment directories were found",
}

ANALYZER_NAME = "job_matching"
ANALYZER_VERSION = "1.0.0"

#: Evidence source -> strength contribution. Ordered strongest first.
EVIDENCE_WEIGHTS: dict[str, float] = {
    "dependency": 0.45,
    "import": 0.35,
    "path": 0.35,
    "signal": 0.50,
    "topic": 0.15,
    "readme": 0.10,
    "description": 0.08,
}


@dataclass(slots=True)
class RepositoryEvidence:
    """Everything the matcher may look at, gathered by the pipeline."""

    languages: dict[str, int] = field(default_factory=dict)      # language -> bytes or file count
    dependencies: set[str] = field(default_factory=set)
    imports: set[str] = field(default_factory=set)
    paths: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    readme: str = ""
    description: str = ""
    #: Direct observations made by the pipeline, as ``skill_key -> strength``.
    #: For example ``{"git": 1.0}`` when commit history exists, or
    #: ``{"testing": 0.8}`` when the testing analyzer found real test cases.
    #: These are first-hand facts, so they carry the highest evidence weight.
    signals: dict[str, float] = field(default_factory=dict)

    def language_share(self, language: str) -> float:
        total = sum(self.languages.values()) or 1
        return self.languages.get(language, 0) / total


@dataclass(slots=True)
class SkillMatch:
    skill: str
    label: str
    dimension: str
    required: bool
    importance: float
    strength: float
    sources: list[dict[str, Any]] = field(default_factory=list)

    @property
    def matched(self) -> bool:
        return self.strength >= 0.2

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": self.skill, "label": self.label, "dimension": self.dimension,
            "required": self.required, "importance": round(self.importance, 4),
            "strength": round(self.strength, 4), "matched": self.matched,
            "sources": self.sources[:6],
        }


def _skill_strength(skill: Skill, evidence: RepositoryEvidence) -> tuple[float, list[dict[str, Any]]]:
    strength = 0.0
    sources: list[dict[str, Any]] = []

    # A language the repository is actually written in is first-hand evidence,
    # so a dominant language alone can carry a skill close to full strength.
    share = max((evidence.language_share(l) for l in skill.languages), default=0.0)
    if share > 0:
        language = max(skill.languages, key=evidence.language_share)
        contribution = min(0.9, 0.35 + share * 1.1)
        strength += contribution
        sources.append({
            "type": "language", "detail": f"{language} accounts for {share * 100:.0f}% of analysed code",
            "weight": round(contribution, 3),
        })

    matched_deps = sorted(
        d for d in evidence.dependencies
        if any(d == m or d.startswith(f"{m}-") or d.endswith(f"/{m}") or d == f"@{m}"
               for m in skill.dependencies)
    )
    if matched_deps:
        contribution = EVIDENCE_WEIGHTS["dependency"] * min(1.0, 0.6 + 0.2 * len(matched_deps))
        strength += contribution
        sources.append({
            "type": "dependency", "detail": f"declares {', '.join(matched_deps[:4])}",
            "weight": round(contribution, 3),
        })

    matched_imports = sorted(i for i in evidence.imports if i in set(skill.imports))
    if matched_imports:
        contribution = EVIDENCE_WEIGHTS["import"]
        strength += contribution
        sources.append({
            "type": "import", "detail": f"source imports {', '.join(matched_imports[:4])}",
            "weight": round(contribution, 3),
        })

    for pattern in skill.path_patterns:
        matches = [p for p in evidence.paths if re.search(pattern, p)]
        if matches:
            contribution = EVIDENCE_WEIGHTS["path"]
            strength += contribution
            sources.append({
                "type": "path", "detail": f"{len(matches)} matching path(s), e.g. {matches[0]}",
                "weight": round(contribution, 3),
            })
            break

    signal_value = evidence.signals.get(skill.key)
    if signal_value:
        contribution = EVIDENCE_WEIGHTS["signal"] * min(1.0, signal_value)
        strength += contribution
        sources.append({
            "type": "observed", "detail": _SIGNAL_LABELS.get(skill.key, "observed directly during analysis"),
            "weight": round(contribution, 3),
        })

    topic_blob = " ".join(evidence.topics)
    if topic_blob and skill.key in extract_skills(topic_blob):
        strength += EVIDENCE_WEIGHTS["topic"]
        sources.append({"type": "topic", "detail": "listed in repository topics",
                        "weight": EVIDENCE_WEIGHTS["topic"]})

    if evidence.readme and skill.key in extract_skills(evidence.readme):
        strength += EVIDENCE_WEIGHTS["readme"]
        sources.append({"type": "readme", "detail": "mentioned in the README",
                        "weight": EVIDENCE_WEIGHTS["readme"]})
    if evidence.description and skill.key in extract_skills(evidence.description):
        strength += EVIDENCE_WEIGHTS["description"]
        sources.append({"type": "description", "detail": "mentioned in the repository description",
                        "weight": EVIDENCE_WEIGHTS["description"]})

    return clamp(strength, 0.0, 1.0), sources


def match_repository_to_job(
    job: ParsedJob, evidence: RepositoryEvidence
) -> tuple[AnalyzerResult, list[SkillMatch]]:
    """Score how relevant a repository is to a parsed job description."""
    result = AnalyzerResult(analyzer=ANALYZER_NAME, version=ANALYZER_VERSION)

    if not job.requirements:
        result.score = None
        result.partial = True
        result.confidence = 0.0
        result.metrics = {"matches": [], "reason": "job has no structured requirements"}
        result.limit("job_matching",
                     "The job description produced no structured requirements, so relevance could "
                     "not be computed. Add requirements to the job to enable matching.")
        return result, []

    matches: list[SkillMatch] = []
    for requirement in job.requirements:
        skill = SKILLS_BY_KEY.get(requirement.skill)
        if skill is None:  # pragma: no cover - taxonomy/job drift
            continue
        strength, sources = _skill_strength(skill, evidence)
        matches.append(SkillMatch(
            skill=skill.key, label=skill.label, dimension=str(skill.dimension),
            required=requirement.required, importance=requirement.importance,
            strength=strength, sources=sources,
        ))

    weight_total = sum(m.importance for m in matches) or 1.0
    relevance = 100.0 * sum(m.strength * m.importance for m in matches) / weight_total

    required = [m for m in matches if m.required]
    required_covered = [m for m in required if m.matched]
    missing_required = [m for m in required if not m.matched]

    result.score = round(clamp(relevance), 2)
    result.confidence = round(clamp(0.5 + 0.4 * (len(evidence.dependencies) > 0)
                                    + 0.1 * (len(evidence.languages) > 0), 0.0, 0.95), 3)
    result.metrics = {
        "job_relevance": round(relevance, 2),
        "required_skills": len(required),
        "required_skills_evidenced": len(required_covered),
        "required_coverage": round(len(required_covered) / len(required), 4) if required else None,
        "missing_required_skills": [m.label for m in missing_required],
        "matches": [m.to_dict() for m in matches],
        "experience_level": job.experience_level,
        "domain": job.domain,
        "dimension_coverage": _dimension_coverage(matches),
    }

    if required_covered:
        result.add(Evidence(
            category=ScoreCategory.JOB_RELEVANCE,
            claim=f"{len(required_covered)} of {len(required)} required skill(s) are evidenced "
                  "in this repository",
            severity=Severity.INFO, confidence=0.8, supports="strength", tags=("job_match",),
            evidence=tuple(
                EvidenceDetail(
                    detail=f"{m.label}: " + "; ".join(s["detail"] for s in m.sources[:2]),
                    metric=m.strength,
                )
                for m in sorted(required_covered, key=lambda x: -x.strength * x.importance)[:8]
            ),
        ))
    if missing_required:
        result.add(Evidence(
            category=ScoreCategory.JOB_RELEVANCE,
            claim=f"No repository evidence for {len(missing_required)} required skill(s)",
            severity=Severity.MEDIUM if len(missing_required) > len(required) / 2 else Severity.LOW,
            confidence=0.75, supports="weakness", tags=("job_match", "gap"),
            evidence=tuple(
                EvidenceDetail(detail=f"{m.label}: no dependency, import, language or path evidence found")
                for m in sorted(missing_required, key=lambda x: -x.importance)[:8]
            ),
        ))

    preferred_matched = [m for m in matches if not m.required and m.matched]
    if preferred_matched:
        result.add(Evidence(
            category=ScoreCategory.JOB_RELEVANCE,
            claim=f"{len(preferred_matched)} preferred skill(s) also evidenced",
            severity=Severity.INFO, confidence=0.7, supports="strength", tags=("job_match",),
            evidence=tuple(
                EvidenceDetail(detail=f"{m.label}: {m.sources[0]['detail'] if m.sources else 'evidenced'}")
                for m in preferred_matched[:6]
            ),
        ))

    result.limit(
        "job_matching",
        "Relevance measures evidence of the named technologies in this repository. It does not "
        "measure depth of expertise; a technical conversation remains the way to assess that.",
    )
    return result, matches


def _dimension_coverage(matches: list[SkillMatch]) -> dict[str, float]:
    """Average evidenced strength per Engineering DNA dimension."""
    totals: dict[str, list[float]] = {}
    for match in matches:
        totals.setdefault(match.dimension, []).append(match.strength)
    return {k: round(100.0 * sum(v) / len(v), 2) for k, v in totals.items()}


def engineering_dna(evidence: RepositoryEvidence) -> dict[str, float]:
    """Evidence-based strength across every Engineering DNA dimension.

    Unlike the job match this is job-independent: it scores the repository
    against the whole taxonomy so a candidate profile can be drawn.
    """
    per_dimension: dict[str, list[float]] = {str(d): [] for d in SkillDimension}
    for skill in SKILLS_BY_KEY.values():
        strength, _ = _skill_strength(skill, evidence)
        per_dimension[str(skill.dimension)].append(strength)
    return {
        dimension: round(100.0 * clamp(sum(sorted(values, reverse=True)[:4]) / 2.0, 0.0, 1.0), 2)
        for dimension, values in per_dimension.items()
    }
