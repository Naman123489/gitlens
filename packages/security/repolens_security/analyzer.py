"""The security analyzer: runs the secret and pattern scanners and scores them."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from repolens_shared import AnalyzerResult, Evidence, EvidenceDetail, ScoreCategory, Severity
from repolens_shared.textutils import clamp

from .patterns import PatternFinding, scan_patterns
from .secrets import SecretFinding, scan_text

ANALYZER_NAME = "security"
ANALYZER_VERSION = "1.0.0"

#: Score penalty per finding, by severity, scaled by the finding's confidence.
SEVERITY_PENALTY: dict[Severity, float] = {
    Severity.CRITICAL: 30.0,
    Severity.HIGH: 16.0,
    Severity.MEDIUM: 7.0,
    Severity.LOW: 2.5,
    Severity.INFO: 0.0,
}

#: Repository hygiene markers that earn back points.
GOOD_PRACTICE_MARKERS: tuple[tuple[str, str, float], ...] = (
    ("gitignore_env", "`.env` is git-ignored", 6.0),
    ("env_example", "`.env.example` documents configuration without secrets", 4.0),
    ("security_policy", "A SECURITY policy is published", 3.0),
    ("dependency_pinning", "Dependencies are pinned or locked", 3.0),
)


#: Insecure-code patterns are only meaningful in files that are executed.
#: Documentation quotes code constantly — a changelog entry describing
#: ``verify=False`` is prose, not a vulnerability — so pattern scanning is
#: restricted to these categories. Secret scanning still covers every file,
#: because a leaked credential in a README is a real leaked credential.
CODE_CATEGORIES: frozenset[str] = frozenset(
    {"CANDIDATE_CODE", "TEST_CODE", "CONFIGURATION", "GENERATED_CODE"}
)


@dataclass(slots=True)
class SecurityInput:
    texts: dict[str, str]
    languages: dict[str, str | None] = field(default_factory=dict)
    all_paths: list[str] = field(default_factory=list)
    has_lock_file: bool = False
    #: path -> FileCategory value. When empty every file is pattern-scanned,
    #: which is the correct behaviour for a caller that has no classification.
    categories: dict[str, str] = field(default_factory=dict)


def _dedupe_secrets(findings: list[SecretFinding]) -> list[SecretFinding]:
    """Keep one finding per (file, line, masked value).

    Provider patterns overlap — an Anthropic key also matches the generic
    ``sk-`` shape — and reporting the same credential twice would double the
    score penalty for a single mistake.
    """
    best: dict[tuple[str, int, str], SecretFinding] = {}
    for finding in findings:
        key = (finding.file, finding.line, finding.masked_value)
        current = best.get(key)
        if current is None or finding.confidence > current.confidence:
            best[key] = finding
    return sorted(best.values(), key=lambda f: (f.file, f.line))


def _confidence_weight(finding_confidence: float) -> float:
    """Low-confidence findings cost less. A 0.4-confidence LOW is nearly free."""
    return max(0.0, (finding_confidence - 0.3) / 0.7)


def analyze_security(data: SecurityInput) -> AnalyzerResult:
    result = AnalyzerResult(analyzer=ANALYZER_NAME, version=ANALYZER_VERSION)

    secret_findings: list[SecretFinding] = []
    pattern_findings: list[PatternFinding] = []
    for path, text in data.texts.items():
        secret_findings.extend(scan_text(path, text))
        if not data.categories or data.categories.get(path) in CODE_CATEGORIES:
            pattern_findings.extend(scan_patterns(path, text, data.languages.get(path)))
    secret_findings = _dedupe_secrets(secret_findings)

    gitignore = data.texts.get(".gitignore", "")
    practices: list[tuple[str, str, float]] = []
    if ".env" in gitignore:
        practices.append(GOOD_PRACTICE_MARKERS[0])
    if any(p.endswith((".env.example", ".env.sample", ".env.template")) for p in data.all_paths):
        practices.append(GOOD_PRACTICE_MARKERS[1])
    if any(p.upper().startswith("SECURITY") for p in data.all_paths):
        practices.append(GOOD_PRACTICE_MARKERS[2])
    if data.has_lock_file:
        practices.append(GOOD_PRACTICE_MARKERS[3])

    committed_env = [
        p for p in data.all_paths
        if p.rsplit("/", 1)[-1] in (".env", ".env.local", ".env.production")
    ]

    penalty = 0.0
    for finding in secret_findings:
        penalty += SEVERITY_PENALTY[finding.severity] * _confidence_weight(finding.confidence)
    for finding in pattern_findings:
        penalty += SEVERITY_PENALTY[finding.severity] * _confidence_weight(finding.confidence)
    penalty += 25.0 * len(committed_env)

    bonus = sum(weight for _, _, weight in practices)
    score = clamp(100.0 - penalty + bonus)

    severity_counts = Counter(
        str(f.severity) for f in (*secret_findings, *pattern_findings)
    )
    category_counts = Counter(f.category for f in pattern_findings)

    result.score = round(score, 2)
    result.confidence = 0.8 if data.texts else 0.2
    pattern_scanned = (
        len(data.texts) if not data.categories
        else sum(1 for c in data.categories.values() if c in CODE_CATEGORIES)
    )
    result.metrics = {
        "files_scanned": len(data.texts),
        "files_pattern_scanned": pattern_scanned,
        "secret_findings": len(secret_findings),
        "pattern_findings": len(pattern_findings),
        "severity_counts": dict(severity_counts),
        "pattern_categories": dict(category_counts),
        "committed_env_files": committed_env,
        "good_practices": [label for _, label, _ in practices],
        "penalty": round(penalty, 2),
        "bonus": round(bonus, 2),
        "findings": [
            {
                "kind": "secret", "rule_id": f.rule_id, "title": f.title, "file": f.file,
                "line": f.line, "severity": str(f.severity), "confidence": f.confidence,
                "masked_value": f.masked_value, "snippet": f.snippet, "note": f.note,
                "remediation": "Remove the value from source control, rotate the credential, "
                               "and load it from the environment at runtime.",
            }
            for f in sorted(secret_findings, key=lambda x: -x.confidence)[:200]
        ] + [
            {
                "kind": "pattern", "rule_id": f.rule_id, "title": f.title, "file": f.file,
                "line": f.line, "severity": str(f.severity), "confidence": f.confidence,
                "category": f.category, "snippet": f.snippet, "remediation": f.remediation,
                "cwe": f.cwe,
            }
            for f in sorted(pattern_findings, key=lambda x: -x.confidence)[:200]
        ],
    }

    if secret_findings:
        high = [f for f in secret_findings if f.confidence >= 0.7]
        result.add(Evidence(
            category=ScoreCategory.SECURITY,
            claim=f"{len(secret_findings)} potential hardcoded credential(s) detected"
                  + (f", {len(high)} at high confidence" if high else ""),
            severity=Severity.CRITICAL if high else Severity.MEDIUM,
            confidence=max(f.confidence for f in secret_findings),
            supports="weakness", tags=("secrets",),
            evidence=tuple(
                EvidenceDetail(
                    detail=f"{f.title} — value masked{f' ({f.note})' if f.note else ''}",
                    file=f.file, line=f.line, snippet=f.snippet,
                )
                for f in sorted(secret_findings, key=lambda x: -x.confidence)[:8]
            ),
        ))
    else:
        result.add(Evidence(
            category=ScoreCategory.SECURITY,
            claim="No hardcoded credentials were detected",
            severity=Severity.INFO, confidence=0.7, supports="strength", tags=("secrets",),
            evidence=(EvidenceDetail(detail=f"{len(data.texts)} files scanned against "
                                            "provider patterns and entropy rules"),),
        ))

    if committed_env:
        result.add(Evidence(
            category=ScoreCategory.SECURITY,
            claim="An environment file is committed to the repository",
            severity=Severity.CRITICAL, confidence=0.9, supports="weakness", tags=("secrets", "config"),
            evidence=tuple(EvidenceDetail(detail="environment files should never be committed", file=p)
                           for p in committed_env[:4]),
        ))

    for category, count in category_counts.most_common():
        items = [f for f in pattern_findings if f.category == category]
        worst = max(items, key=lambda f: (SEVERITY_PENALTY[f.severity], f.confidence))
        result.add(Evidence(
            category=ScoreCategory.SECURITY,
            claim=f"{count} finding(s) in category '{category.replace('_', ' ')}'",
            severity=worst.severity,
            confidence=round(sum(f.confidence for f in items) / len(items), 3),
            supports="weakness", tags=("static_analysis", category),
            evidence=tuple(
                EvidenceDetail(detail=f"{f.title} — {f.remediation}", file=f.file, line=f.line,
                               snippet=f.snippet)
                for f in sorted(items, key=lambda x: -x.confidence)[:5]
            ),
        ))

    if practices:
        result.add(Evidence(
            category=ScoreCategory.SECURITY,
            claim="Secure-configuration practices observed",
            severity=Severity.INFO, confidence=0.8, supports="strength", tags=("hygiene",),
            evidence=tuple(EvidenceDetail(detail=label) for _, label, _ in practices),
        ))

    if data.categories:
        result.limit(
            "pattern_scope",
            f"Insecure-code patterns were checked in {pattern_scanned} code and configuration "
            f"file(s) of {len(data.texts)} analysed. Documentation is excluded because prose that "
            "quotes code is not executable. Credential scanning covered every file.",
        )
    result.limit(
        "security_scope",
        "This is pattern-based static analysis without data-flow or taint tracking. It surfaces code "
        "worth a human review; it neither proves exploitability nor guarantees the absence of "
        "vulnerabilities. Detected credential values are masked and are never stored or displayed.",
    )
    result.limit(
        "dependency_cves",
        "Third-party dependency vulnerabilities are out of scope for this analyzer; no CVE database "
        "is consulted.",
    )
    return result
