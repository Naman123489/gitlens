"""Testing analysis.

Detects test frameworks, counts test cases, measures test-to-source ratio and
looks for CI that actually runs the tests.

Deliberately *not* implemented: a real coverage percentage. Producing one would
require executing candidate code, which RepoLens never does. A coverage
configuration file is reported as evidence that coverage is tracked, but no
number is invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from repolens_shared import AnalyzerResult, Evidence, EvidenceDetail, ScoreCategory, Severity
from repolens_shared.textutils import clamp, scale

from .ast_engine import FileAST

ANALYZER_NAME = "testing"
ANALYZER_VERSION = "1.0.0"

#: framework -> import/usage markers
TEST_FRAMEWORKS: dict[str, tuple[str, ...]] = {
    "pytest": ("import pytest", "from pytest", "@pytest.", "pytest.fixture"),
    "unittest": ("import unittest", "unittest.TestCase"),
    # Markers must be specific to the framework. Bare "describe(" / "it(" match
    # ordinary code in other languages and produced false positives.
    "jest": ("@jest/globals", "jest.mock", "jest.fn(", "jest.spyOn", "from 'jest'"),
    "vitest": ("from 'vitest'", 'from "vitest"', "vi.mock", "vi.fn("),
    "mocha": ("require('mocha')", "from 'mocha'", 'from "mocha"'),
    "testing-library": ("@testing-library/",),
    "playwright": ("@playwright/test", "playwright.sync_api", "playwright.async_api"),
    "cypress": ("cypress/", "cy.visit(", "cy.get("),
    "junit": ("org.junit", "@Test"),
    "go-test": ("testing.T",),
    "rspec": ("RSpec.describe",),
    "gtest": ("gtest/gtest.h", "TEST_F("),
}

_TEST_CASE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*def\s+test_\w+", re.MULTILINE),
    re.compile(r"^\s*(?:async\s+)?(?:it|test)\s*\(\s*['\"`]", re.MULTILINE),
    re.compile(r"@Test\b"),
    re.compile(r"^\s*func\s+Test\w+", re.MULTILINE),
    re.compile(r"TEST(?:_F)?\s*\(", re.MULTILINE),
)

_INTEGRATION_HINTS = ("integration", "e2e", "end_to_end", "end-to-end", "functional", "api_test")
_E2E_HINTS = ("e2e", "playwright", "cypress", "selenium", "puppeteer")
_COVERAGE_FILES = (".coveragerc", "codecov.yml", ".codecov.yml", "jest.config", "vitest.config")
_COVERAGE_MARKERS = ("--cov", "coverage run", "collectCoverage", "nyc ", "jacoco", "coverage:")
_CI_TEST_MARKERS = ("pytest", "npm test", "npm run test", "yarn test", "pnpm test",
                    "go test", "mvn test", "gradle test", "vitest", "jest", "cargo test",
                    "tox", "make test")

#: Weights inside the testing score.
TESTING_WEIGHTS = {"presence": 0.30, "volume": 0.25, "breadth": 0.20, "ci": 0.15, "coverage_tracking": 0.10}


@dataclass(slots=True)
class TestingInput:
    texts: dict[str, str]
    categories: dict[str, str]
    asts: list[FileAST] = field(default_factory=list)
    all_paths: list[str] = field(default_factory=list)


def _detect_frameworks(texts: dict[str, str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for text in texts.values():
        for framework, markers in TEST_FRAMEWORKS.items():
            hits = sum(text.count(marker) for marker in markers)
            if hits:
                found[framework] = found.get(framework, 0) + hits
    return found


def _count_test_cases(text: str) -> int:
    return sum(len(pattern.findall(text)) for pattern in _TEST_CASE_PATTERNS)


def analyze_testing(data: TestingInput) -> AnalyzerResult:
    result = AnalyzerResult(analyzer=ANALYZER_NAME, version=ANALYZER_VERSION)

    test_paths = [p for p, c in data.categories.items() if c == "TEST_CODE"]
    source_paths = [p for p, c in data.categories.items() if c == "CANDIDATE_CODE"]
    test_texts = {p: data.texts[p] for p in test_paths if p in data.texts}
    source_texts = {p: data.texts[p] for p in source_paths if p in data.texts}

    test_cases = sum(_count_test_cases(t) for t in test_texts.values())
    frameworks = _detect_frameworks(test_texts)
    test_lines = sum(t.count("\n") for t in test_texts.values())
    source_lines = sum(t.count("\n") for t in source_texts.values())
    ratio = test_lines / source_lines if source_lines else 0.0

    has_integration = any(
        any(hint in p.lower() for hint in _INTEGRATION_HINTS) for p in test_paths
    )
    has_e2e = any(
        any(hint in p.lower() for hint in _E2E_HINTS) for p in test_paths
    ) or any(fw in frameworks for fw in ("playwright", "cypress"))
    has_unit = bool(test_cases) and not (has_integration and not test_cases)

    ci_files = [
        p for p in data.all_paths
        if p.startswith(".github/workflows/") or p in (".gitlab-ci.yml", ".circleci/config.yml",
                                                       "azure-pipelines.yml", "Jenkinsfile",
                                                       ".travis.yml")
    ]
    ci_texts = {p: data.texts[p] for p in ci_files if p in data.texts}
    ci_runs_tests = any(
        marker in text for text in ci_texts.values() for marker in _CI_TEST_MARKERS
    )
    coverage_tracked = any(
        any(marker in p for marker in _COVERAGE_FILES) for p in data.all_paths
    ) or any(
        marker in text for text in {**ci_texts, **{p: data.texts[p] for p in data.all_paths
                                                   if p in data.texts and p.endswith(("toml", "cfg", "ini", "json"))}}.values()
        for marker in _COVERAGE_MARKERS
    )

    # --- sub-scores ----------------------------------------------------------
    presence = 100.0 if test_cases > 0 else (40.0 if test_paths else 0.0)
    volume = scale(min(ratio, 0.6), 0.0, 0.35)
    breadth = 100.0 * (
        (0.45 if has_unit else 0.0) + (0.35 if has_integration else 0.0) + (0.20 if has_e2e else 0.0)
    )
    ci_score = 100.0 if ci_runs_tests else (45.0 if ci_files else 0.0)
    coverage_score = 100.0 if coverage_tracked else 0.0

    subs = {
        "presence": presence, "volume": volume, "breadth": breadth,
        "ci": ci_score, "coverage_tracking": coverage_score,
    }
    score = sum(subs[k] * w for k, w in TESTING_WEIGHTS.items())

    result.score = round(clamp(score), 2)
    result.confidence = 0.9 if source_paths else 0.5
    result.metrics = {
        "test_files": len(test_paths),
        "test_cases": test_cases,
        "test_lines": test_lines,
        "source_lines": source_lines,
        "test_to_source_ratio": round(ratio, 4),
        "frameworks": sorted(frameworks),
        "has_unit_tests": has_unit,
        "has_integration_tests": has_integration,
        "has_e2e_tests": has_e2e,
        "ci_files": ci_files,
        "ci_runs_tests": ci_runs_tests,
        "coverage_tracking_configured": coverage_tracked,
        "sub_scores": {k: round(v, 2) for k, v in subs.items()},
        "weights": TESTING_WEIGHTS,
    }

    if test_cases:
        result.add(Evidence(
            category=ScoreCategory.TESTING,
            claim=f"{test_cases} test case(s) detected across {len(test_paths)} test file(s)",
            severity=Severity.INFO, confidence=0.9, supports="strength", tags=("tests",),
            evidence=tuple(
                EvidenceDetail(detail=f"{_count_test_cases(t)} test case(s)", file=p)
                for p, t in sorted(test_texts.items(), key=lambda kv: -_count_test_cases(kv[1]))[:5]
            ),
        ))
    else:
        result.add(Evidence(
            category=ScoreCategory.TESTING,
            claim="No automated test cases were detected",
            severity=Severity.HIGH, confidence=0.85, supports="weakness", tags=("tests",),
            evidence=(EvidenceDetail(
                detail=f"{len(source_paths)} source file(s) analysed, no recognised test definitions found"),),
        ))

    if frameworks:
        result.add(Evidence(
            category=ScoreCategory.TESTING,
            claim=f"Test framework(s) in use: {', '.join(sorted(frameworks))}",
            severity=Severity.INFO, confidence=0.9, supports="strength", tags=("tests", "tooling"),
            evidence=tuple(EvidenceDetail(detail=f"{fw}: {count} marker(s)")
                           for fw, count in sorted(frameworks.items(), key=lambda kv: -kv[1])[:4]),
        ))

    if not has_integration:
        result.add(Evidence(
            category=ScoreCategory.TESTING,
            claim="No integration test suite was detected",
            severity=Severity.MEDIUM, confidence=0.75, supports="weakness", tags=("tests", "breadth"),
            evidence=(EvidenceDetail(
                detail="no test path matching integration/e2e/functional naming conventions"),),
        ))

    if ci_runs_tests:
        result.add(Evidence(
            category=ScoreCategory.TESTING,
            claim="Continuous integration runs the test suite",
            severity=Severity.INFO, confidence=0.85, supports="strength", tags=("ci",),
            evidence=tuple(EvidenceDetail(detail="CI workflow invokes a test runner", file=p)
                           for p in ci_files[:3]),
        ))
    elif ci_files:
        result.add(Evidence(
            category=ScoreCategory.TESTING,
            claim="CI configuration exists but no test invocation was found in it",
            severity=Severity.MEDIUM, confidence=0.7, supports="weakness", tags=("ci",),
            evidence=tuple(EvidenceDetail(detail="no test command detected", file=p) for p in ci_files[:3]),
        ))
    else:
        result.add(Evidence(
            category=ScoreCategory.TESTING,
            claim="No continuous integration configuration was found",
            severity=Severity.MEDIUM, confidence=0.9, supports="weakness", tags=("ci",),
            evidence=(EvidenceDetail(detail="no workflow file under .github/workflows or equivalent"),),
        ))

    # Which source modules have no obviously corresponding test file?
    untested = _untested_modules(source_paths, test_paths)
    if untested and test_cases:
        result.add(Evidence(
            category=ScoreCategory.TESTING,
            claim=f"{len(untested)} source module(s) have no matching test file",
            severity=Severity.MEDIUM, confidence=0.6, supports="weakness", tags=("tests", "coverage"),
            evidence=tuple(EvidenceDetail(detail="no test file references this module name", file=p)
                           for p in untested[:6]),
        ))

    result.limit(
        "coverage",
        "Line coverage is not measured. RepoLens never executes repository code, so coverage is "
        "inferred from test volume, breadth and configuration rather than from a coverage run.",
    )
    if not source_paths:
        result.partial = True
        result.limit("testing", "No candidate source files were available to compare tests against.")
    return result


def _untested_modules(source_paths: list[str], test_paths: list[str]) -> list[str]:
    """Source modules whose base name never appears in a test file path."""
    test_blob = " ".join(test_paths).lower()
    untested: list[str] = []
    for path in source_paths:
        stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        if stem in ("index", "__init__", "main", "app", "types", "constants"):
            continue
        if stem not in test_blob:
            untested.append(path)
    return sorted(untested)
