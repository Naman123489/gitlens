"""The evidence primitives every analyzer must emit.

Rule 4 of the RepoLens development rules: *every score must be traceable to
evidence*. Analyzers therefore never return bare numbers; they return
:class:`AnalyzerResult` objects carrying metrics, evidence and limitations.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .enums import ConfidenceBand, ScoreCategory, Severity


@dataclass(frozen=True, slots=True)
class EvidenceDetail:
    """A single concrete observation backing a claim.

    ``file``/``line`` are optional because some observations are repository-wide
    (for example "no CI workflow detected").
    """

    detail: str
    file: str | None = None
    line: int | None = None
    snippet: str | None = None
    metric: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(frozen=True, slots=True)
class Evidence:
    """A claim plus the observations that support it.

    ``confidence`` is in [0, 1] and is mandatory: a claim nobody can quantify
    should not be made at all.
    """

    category: ScoreCategory
    claim: str
    severity: Severity
    confidence: float
    evidence: tuple[EvidenceDetail, ...] = ()
    supports: str = "neutral"  # "strength" | "weakness" | "neutral"
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        if self.supports not in ("strength", "weakness", "neutral"):
            raise ValueError(f"invalid supports value: {self.supports}")

    @property
    def confidence_band(self) -> ConfidenceBand:
        return ConfidenceBand.from_value(self.confidence)

    def evidence_id(self) -> str:
        """Stable content-addressed id so the same observation keeps its id
        across re-analysis of an unchanged repository."""
        payload = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return "ev_" + hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": str(self.category),
            "claim": self.claim,
            "severity": str(self.severity),
            "confidence": round(self.confidence, 4),
            "confidence_band": str(self.confidence_band),
            "supports": self.supports,
            "tags": list(self.tags),
            "evidence": [d.to_dict() for d in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class Limitation:
    """An explicit statement of what the analysis could *not* establish.

    Surfacing limitations is a hard requirement for every probabilistic module.
    """

    scope: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"scope": self.scope, "detail": self.detail}


@dataclass
class AnalyzerResult:
    """Uniform return type for all analyzers.

    ``metrics`` holds the deterministic, machine-readable output used by the
    scoring engine. ``evidence`` explains it to a human. ``score`` is optional:
    analyzers that only produce signals (for example the git-history analyzer
    feeding ownership) leave it ``None``.
    """

    analyzer: str
    version: str
    metrics: dict[str, Any] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    limitations: list[Limitation] = field(default_factory=list)
    score: float | None = None
    confidence: float = 1.0
    partial: bool = False

    def add(self, evidence: Evidence) -> None:
        self.evidence.append(evidence)

    def limit(self, scope: str, detail: str) -> None:
        self.limitations.append(Limitation(scope=scope, detail=detail))

    def to_dict(self) -> dict[str, Any]:
        return {
            "analyzer": self.analyzer,
            "version": self.version,
            "metrics": self.metrics,
            "evidence": [e.to_dict() for e in self.evidence],
            "limitations": [l.to_dict() for l in self.limitations],
            "score": self.score,
            "confidence": round(self.confidence, 4),
            "partial": self.partial,
        }


@dataclass(frozen=True, slots=True)
class CategoryScore:
    """A scored dimension, linked back to the evidence that produced it."""

    category: ScoreCategory
    score: float
    confidence: float
    evidence_ids: tuple[str, ...] = ()
    available: bool = True
    unavailable_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": str(self.category),
            "score": round(self.score, 2) if self.available else None,
            "confidence": round(self.confidence, 4),
            "confidence_band": str(ConfidenceBand.from_value(self.confidence)),
            "evidence_ids": list(self.evidence_ids),
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
        }
