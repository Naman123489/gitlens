"""Rehydrate persisted analyzer output back into typed objects.

Analyses are stored as JSON so they stay readable and queryable, but the scoring
engine works with typed :class:`AnalyzerResult` objects. Round-tripping through
this module keeps evidence ids stable, which is what lets a score reference the
same evidence across re-scoring runs.
"""

from __future__ import annotations

from typing import Any

from repolens_shared import (
    AnalyzerResult,
    Evidence,
    EvidenceDetail,
    Limitation,
    ScoreCategory,
    Severity,
)


def evidence_from_dict(payload: dict[str, Any]) -> Evidence:
    return Evidence(
        category=ScoreCategory(payload["category"]),
        claim=payload["claim"],
        severity=Severity(payload.get("severity", "info")),
        confidence=float(payload.get("confidence", 0.0)),
        supports=payload.get("supports", "neutral"),
        tags=tuple(payload.get("tags") or ()),
        evidence=tuple(
            EvidenceDetail(
                detail=item.get("detail", ""), file=item.get("file"), line=item.get("line"),
                snippet=item.get("snippet"), metric=item.get("metric"),
            )
            for item in payload.get("evidence") or []
        ),
    )


def result_from_dict(payload: dict[str, Any]) -> AnalyzerResult:
    return AnalyzerResult(
        analyzer=payload.get("analyzer", ""),
        version=payload.get("version", ""),
        metrics=payload.get("metrics") or {},
        evidence=[evidence_from_dict(e) for e in payload.get("evidence") or []],
        limitations=[
            Limitation(scope=l.get("scope", ""), detail=l.get("detail", ""))
            for l in payload.get("limitations") or []
        ],
        score=payload.get("score"),
        confidence=float(payload.get("confidence", 0.0)),
        partial=bool(payload.get("partial", False)),
    )


def results_from_analysis(stored: dict[str, Any]) -> dict[str, AnalyzerResult]:
    return {name: result_from_dict(payload) for name, payload in (stored or {}).items()}
