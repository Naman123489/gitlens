"""Deterministic code-quality metrics.

Everything here is computed from the AST or from the raw text — no model is
consulted. The resulting score is a documented weighted combination of
sub-metrics, and each sub-metric contributes explicit evidence.

Thresholds live in :data:`QUALITY_THRESHOLDS` so they are auditable and can be
tuned without touching the maths.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from repolens_shared import AnalyzerResult, Evidence, EvidenceDetail, ScoreCategory, Severity
from repolens_shared.textutils import clamp, scale, split_identifier

from .ast_engine import FileAST
from .languages import supports_ast

ANALYZER_NAME = "code_metrics"
ANALYZER_VERSION = "1.0.0"

#: Auditable thresholds. "good"/"bad" anchor the linear scaling of each metric.
QUALITY_THRESHOLDS: dict[str, dict[str, float]] = {
    "avg_complexity": {"good": 3.0, "bad": 12.0},
    "high_complexity_ratio": {"good": 0.0, "bad": 0.25, "threshold": 15},
    "avg_function_lines": {"good": 20.0, "bad": 90.0},
    "long_function_ratio": {"good": 0.0, "bad": 0.30, "threshold": 80},
    "max_nesting": {"good": 3.0, "bad": 8.0},
    "duplication_ratio": {"good": 0.02, "bad": 0.25},
    "comment_ratio": {"low": 0.02, "ideal_low": 0.06, "ideal_high": 0.35, "high": 0.60},
    "large_file_lines": {"threshold": 600.0},
    "naming_quality": {"good": 0.9, "bad": 0.5},
    "error_handling_ratio": {"good": 0.12, "bad": 0.0},
}

#: Weights of each sub-metric inside the technical-quality score. Sums to 1.
QUALITY_WEIGHTS: dict[str, float] = {
    "complexity": 0.24,
    "function_size": 0.16,
    "nesting": 0.12,
    "duplication": 0.16,
    "naming": 0.10,
    "comments": 0.08,
    "error_handling": 0.08,
    "modularity": 0.06,
}

_DUPLICATION_WINDOW = 6  # lines per normalised block
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{0,63}\b")
_LOOP_VARS = {"i", "j", "k", "n", "x", "y", "z", "_", "e", "f", "a", "b", "c", "t", "v"}
_ERROR_HANDLING_TOKENS = ("try", "catch", "except", "rescue", "recover", "finally")
_GENERIC_NAMES = {"data", "data2", "temp", "tmp", "foo", "bar", "baz", "test1", "thing",
                  "stuff", "obj", "val", "var", "res", "ret", "arr", "lst", "dict1"}


@dataclass(slots=True)
class MetricsInput:
    """What the metrics engine needs: parsed ASTs plus their raw text."""

    asts: list[FileAST]
    texts: dict[str, str]
    test_file_paths: set[str] = field(default_factory=set)


def _normalise_line(line: str) -> str:
    """Strip comments, string contents and whitespace so that duplication is
    detected across renamed variables and reformatted code."""
    line = re.sub(r"(#|//).*$", "", line)
    line = re.sub(r"(\"[^\"]*\"|'[^']*')", '""', line)
    return re.sub(r"\s+", "", line)


def duplication_ratio(texts: dict[str, str]) -> tuple[float, list[tuple[str, str, int]]]:
    """Fraction of normalised code blocks that appear more than once.

    Returns the ratio plus up to a handful of concrete duplicate locations
    (``file_a``, ``file_b``, ``line_a``) so the finding is checkable.
    """
    seen: dict[str, tuple[str, int]] = {}
    duplicates: list[tuple[str, str, int]] = []
    total = 0
    duplicated = 0

    for path, text in texts.items():
        lines = [_normalise_line(l) for l in text.splitlines()]
        meaningful = [(i + 1, l) for i, l in enumerate(lines) if len(l) > 3]
        for index in range(0, max(0, len(meaningful) - _DUPLICATION_WINDOW + 1)):
            window = meaningful[index : index + _DUPLICATION_WINDOW]
            block = "\n".join(l for _, l in window)
            if len(block) < 60:
                continue
            total += 1
            digest = hashlib.sha256(block.encode()).hexdigest()
            if digest in seen:
                duplicated += 1
                origin_path, origin_line = seen[digest]
                if len(duplicates) < 8 and origin_path != path:
                    duplicates.append((origin_path, path, window[0][0]))
            else:
                seen[digest] = (path, window[0][0])

    return (duplicated / total if total else 0.0), duplicates


def naming_quality(asts: Iterable[FileAST]) -> tuple[float, list[str]]:
    """Share of declared symbols with descriptive names.

    A name is "poor" if it is a single character outside a loop context, or a
    well-known placeholder such as ``temp`` or ``foo``.
    """
    good = 0
    total = 0
    offenders: list[str] = []
    for file_ast in asts:
        for entity in file_ast.entities:
            name = entity.symbol
            if name in ("<anonymous>", ""):
                continue
            total += 1
            words = split_identifier(name)
            lowered = name.lower()
            poor = (
                (len(name) <= 2 and lowered not in ("id", "ok", "db", "io"))
                or lowered in _GENERIC_NAMES
                or (len(words) == 1 and len(name) <= 3)
            )
            if poor:
                if len(offenders) < 10:
                    offenders.append(f"{entity.file}:{entity.start_line} `{name}`")
            else:
                good += 1
    return (good / total if total else 1.0), offenders


def error_handling_ratio(texts: dict[str, str], function_count: int) -> float:
    """Error-handling constructs per function. Zero means no handling at all."""
    if function_count == 0:
        return 0.0
    count = 0
    for text in texts.values():
        tokens = Counter(_IDENTIFIER_RE.findall(text))
        count += sum(tokens.get(token, 0) for token in _ERROR_HANDLING_TOKENS)
    return count / function_count


def analyze_metrics(data: MetricsInput) -> AnalyzerResult:
    """Compute code-quality metrics and the technical-quality score."""
    result = AnalyzerResult(analyzer=ANALYZER_NAME, version=ANALYZER_VERSION)

    functions = [e for a in data.asts for e in a.functions]
    classes = [e for a in data.asts for e in a.classes]
    parsed_files = [a for a in data.asts if a.parsed]
    unparsed = [a for a in data.asts if not a.parsed]

    if not functions and not classes:
        broken = [a for a in data.asts if a.parser_unavailable]
        result.score = None
        result.confidence = 0.2
        result.partial = True
        result.metrics = {
            "function_count": 0,
            "class_count": 0,
            "analysed_files": len(data.asts),
            "parser_failures": len(broken),
        }
        if broken:
            # An operational fault, not a property of the repository. Reporting
            # it as "no supported source" would blame the candidate's code for a
            # broken deployment.
            reason = broken[0].parse_error or "the language parser could not be loaded"
            result.limit(
                "parser_unavailable",
                f"The source parser failed on {len(broken)} of {len(data.asts)} file(s), so quality "
                f"metrics could not be computed. This is a problem with this deployment, not with "
                f"the repository. First failure: {reason}",
            )
            result.add(
                Evidence(
                    category=ScoreCategory.TECHNICAL_QUALITY,
                    claim="Code quality could not be measured because the source parser is unavailable",
                    severity=Severity.HIGH,
                    confidence=0.95,
                    supports="neutral",
                    tags=("operational_fault",),
                    evidence=(
                        EvidenceDetail(detail=f"{len(broken)} file(s) failed to parse"),
                        EvidenceDetail(detail=reason[:300]),
                    ),
                )
            )
        else:
            result.limit(
                "code_metrics",
                "No functions or classes could be extracted, so quality metrics were not computed. "
                "This happens when the repository contains no source in a supported language.",
            )
            result.add(
                Evidence(
                    category=ScoreCategory.TECHNICAL_QUALITY,
                    claim="No analysable source entities were found in this repository",
                    severity=Severity.INFO,
                    confidence=0.9,
                    supports="neutral",
                    evidence=(EvidenceDetail(detail=f"{len(data.asts)} files inspected"),),
                )
            )
        return result

    complexities = [e.complexity for e in functions] or [1]
    lengths = [e.line_count for e in functions] or [1]
    avg_complexity = sum(complexities) / len(complexities)
    max_complexity = max(complexities)
    complexity_threshold = QUALITY_THRESHOLDS["high_complexity_ratio"]["threshold"]
    high_complexity = [e for e in functions if e.complexity > complexity_threshold]
    high_complexity_ratio = len(high_complexity) / len(functions)

    avg_length = sum(lengths) / len(lengths)
    length_threshold = QUALITY_THRESHOLDS["long_function_ratio"]["threshold"]
    long_functions = [e for e in functions if e.line_count > length_threshold]
    long_function_ratio = len(long_functions) / len(functions)

    max_nesting = max((a.max_nesting for a in data.asts), default=0)
    deep_nested = [e for e in functions if e.max_nesting >= 5]

    dup_ratio, dup_examples = duplication_ratio(data.texts)
    naming, naming_offenders = naming_quality(data.asts)
    handling = error_handling_ratio(data.texts, len(functions))

    code_lines = sum(a.code_lines for a in data.asts)
    comment_lines = sum(a.comment_lines for a in data.asts)
    comment_ratio = comment_lines / max(1, code_lines + comment_lines)

    large_files = [
        a for a in data.asts
        if a.total_lines > QUALITY_THRESHOLDS["large_file_lines"]["threshold"]
    ]
    documented = sum(1 for e in functions if e.has_doc)
    doc_ratio = documented / len(functions) if functions else 0.0

    # --- sub-scores (0..100) -------------------------------------------------
    t = QUALITY_THRESHOLDS
    complexity_score = 0.6 * scale(avg_complexity, t["avg_complexity"]["bad"], t["avg_complexity"]["good"]) + \
        0.4 * scale(high_complexity_ratio, t["high_complexity_ratio"]["bad"], t["high_complexity_ratio"]["good"])
    size_score = 0.6 * scale(avg_length, t["avg_function_lines"]["bad"], t["avg_function_lines"]["good"]) + \
        0.4 * scale(long_function_ratio, t["long_function_ratio"]["bad"], t["long_function_ratio"]["good"])
    nesting_score = scale(float(max_nesting), t["max_nesting"]["bad"], t["max_nesting"]["good"])
    duplication_score = scale(dup_ratio, t["duplication_ratio"]["bad"], t["duplication_ratio"]["good"])
    naming_score = scale(naming, t["naming_quality"]["bad"], t["naming_quality"]["good"])
    error_score = scale(min(handling, t["error_handling_ratio"]["good"]),
                        t["error_handling_ratio"]["bad"], t["error_handling_ratio"]["good"])

    ct = t["comment_ratio"]
    if comment_ratio < ct["low"]:
        comment_score = 35.0
    elif comment_ratio < ct["ideal_low"]:
        comment_score = 35.0 + 65.0 * (comment_ratio - ct["low"]) / (ct["ideal_low"] - ct["low"])
    elif comment_ratio <= ct["ideal_high"]:
        comment_score = 100.0
    elif comment_ratio <= ct["high"]:
        comment_score = 100.0 - 30.0 * (comment_ratio - ct["ideal_high"]) / (ct["high"] - ct["ideal_high"])
    else:
        comment_score = 60.0

    large_ratio = len(large_files) / max(1, len(data.asts))
    modularity_score = clamp(100.0 - large_ratio * 180.0)

    sub_scores = {
        "complexity": complexity_score,
        "function_size": size_score,
        "nesting": nesting_score,
        "duplication": duplication_score,
        "naming": naming_score,
        "comments": comment_score,
        "error_handling": error_score,
        "modularity": modularity_score,
    }
    score = sum(sub_scores[k] * w for k, w in QUALITY_WEIGHTS.items())

    result.score = round(clamp(score), 2)
    result.metrics = {
        "function_count": len(functions),
        "class_count": len(classes),
        "analysed_files": len(data.asts),
        "parsed_files": len(parsed_files),
        "unparsed_files": len(unparsed),
        "avg_complexity": round(avg_complexity, 2),
        "max_complexity": max_complexity,
        "high_complexity_functions": len(high_complexity),
        "high_complexity_ratio": round(high_complexity_ratio, 4),
        "avg_function_lines": round(avg_length, 2),
        "long_functions": len(long_functions),
        "max_nesting": max_nesting,
        "deeply_nested_functions": len(deep_nested),
        "duplication_ratio": round(dup_ratio, 4),
        "naming_quality": round(naming, 4),
        "error_handling_per_function": round(handling, 4),
        "comment_ratio": round(comment_ratio, 4),
        "documented_function_ratio": round(doc_ratio, 4),
        "code_lines": code_lines,
        "comment_lines": comment_lines,
        "large_files": len(large_files),
        "sub_scores": {k: round(v, 2) for k, v in sub_scores.items()},
        "weights": QUALITY_WEIGHTS,
    }

    # --- evidence ------------------------------------------------------------
    result.add(
        Evidence(
            category=ScoreCategory.TECHNICAL_QUALITY,
            claim=f"Average cyclomatic complexity is {avg_complexity:.1f} across {len(functions)} functions",
            severity=Severity.INFO if avg_complexity <= 8 else Severity.MEDIUM,
            confidence=0.95,
            supports="strength" if avg_complexity <= 6 else "weakness",
            tags=("complexity",),
            evidence=tuple(
                EvidenceDetail(
                    detail=f"`{e.symbol}` has complexity {e.complexity}",
                    file=e.file, line=e.start_line, metric=float(e.complexity),
                )
                for e in sorted(functions, key=lambda x: -x.complexity)[:5]
            ),
        )
    )

    if high_complexity:
        result.add(
            Evidence(
                category=ScoreCategory.TECHNICAL_QUALITY,
                claim=f"{len(high_complexity)} function(s) exceed a cyclomatic complexity of {int(complexity_threshold)}",
                severity=Severity.HIGH if high_complexity_ratio > 0.15 else Severity.MEDIUM,
                confidence=0.95,
                supports="weakness",
                tags=("complexity", "maintainability"),
                evidence=tuple(
                    EvidenceDetail(
                        detail=f"`{e.symbol}` complexity {e.complexity} over {e.line_count} lines",
                        file=e.file, line=e.start_line, metric=float(e.complexity),
                    )
                    for e in sorted(high_complexity, key=lambda x: -x.complexity)[:6]
                ),
            )
        )

    if long_functions:
        result.add(
            Evidence(
                category=ScoreCategory.TECHNICAL_QUALITY,
                claim=f"{len(long_functions)} function(s) are longer than {int(length_threshold)} lines",
                severity=Severity.MEDIUM,
                confidence=0.95,
                supports="weakness",
                tags=("function_size",),
                evidence=tuple(
                    EvidenceDetail(detail=f"`{e.symbol}` spans {e.line_count} lines",
                                   file=e.file, line=e.start_line, metric=float(e.line_count))
                    for e in sorted(long_functions, key=lambda x: -x.line_count)[:6]
                ),
            )
        )

    if dup_ratio > QUALITY_THRESHOLDS["duplication_ratio"]["good"]:
        result.add(
            Evidence(
                category=ScoreCategory.TECHNICAL_QUALITY,
                claim=f"{dup_ratio * 100:.1f}% of {_DUPLICATION_WINDOW}-line code blocks are duplicated elsewhere",
                severity=Severity.HIGH if dup_ratio > 0.15 else Severity.MEDIUM,
                confidence=0.85,
                supports="weakness",
                tags=("duplication",),
                evidence=tuple(
                    EvidenceDetail(detail=f"block also appears in {b}", file=a, line=line)
                    for a, b, line in dup_examples[:5]
                ),
            )
        )
    else:
        result.add(
            Evidence(
                category=ScoreCategory.TECHNICAL_QUALITY,
                claim="Code duplication is low",
                severity=Severity.INFO,
                confidence=0.85,
                supports="strength",
                tags=("duplication",),
                evidence=(EvidenceDetail(detail=f"duplicated block ratio {dup_ratio * 100:.1f}%",
                                         metric=dup_ratio),),
            )
        )

    if naming_offenders:
        result.add(
            Evidence(
                category=ScoreCategory.TECHNICAL_QUALITY,
                claim=f"{(1 - naming) * 100:.0f}% of declared symbols use short or placeholder names",
                severity=Severity.LOW,
                confidence=0.7,
                supports="weakness",
                tags=("naming",),
                evidence=tuple(EvidenceDetail(detail=o) for o in naming_offenders[:6]),
            )
        )

    if handling <= 0.01:
        result.add(
            Evidence(
                category=ScoreCategory.TECHNICAL_QUALITY,
                claim="No error-handling constructs were found in the analysed source",
                severity=Severity.MEDIUM,
                confidence=0.8,
                supports="weakness",
                tags=("error_handling", "robustness"),
                evidence=(EvidenceDetail(detail="no try/except/catch constructs detected"),),
            )
        )
    else:
        result.add(
            Evidence(
                category=ScoreCategory.TECHNICAL_QUALITY,
                claim=f"Error handling appears in roughly {handling:.2f} constructs per function",
                severity=Severity.INFO,
                confidence=0.7,
                supports="strength" if handling >= 0.05 else "neutral",
                tags=("error_handling",),
                evidence=(EvidenceDetail(detail=f"{len(functions)} functions analysed", metric=handling),),
            )
        )

    if large_files:
        result.add(
            Evidence(
                category=ScoreCategory.TECHNICAL_QUALITY,
                claim=f"{len(large_files)} file(s) exceed {int(QUALITY_THRESHOLDS['large_file_lines']['threshold'])} lines",
                severity=Severity.LOW,
                confidence=0.9,
                supports="weakness",
                tags=("modularity",),
                evidence=tuple(
                    EvidenceDetail(detail=f"{a.total_lines} lines", file=a.path, metric=float(a.total_lines))
                    for a in sorted(large_files, key=lambda x: -x.total_lines)[:5]
                ),
            )
        )

    if unparsed:
        languages = sorted({a.language for a in unparsed if not supports_ast(a.language)})
        result.partial = True
        result.limit(
            "ast_coverage",
            f"{len(unparsed)} file(s) were counted by line but not parsed into an AST "
            f"({', '.join(languages) or 'unsupported or oversized files'}). "
            "Complexity and naming metrics cover only parsed files.",
        )

    coverage = len(parsed_files) / max(1, len(data.asts))
    result.confidence = round(clamp(0.5 + 0.5 * coverage, 0.0, 1.0), 4)
    return result
