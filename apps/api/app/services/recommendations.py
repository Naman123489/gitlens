"""Improvement recommendations.

Generated from the same evidence that produced the scores, so every suggestion
is traceable to a finding and carries an estimated score gain computed from the
policy weights — not a guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from repolens_shared import ScoreCategory

#: (category, trigger, title, detail, impact, effort). ``trigger`` reads the
#: analyzer metrics and returns True when the recommendation applies.
_RULES: list[dict[str, Any]] = [
    {
        "category": ScoreCategory.TESTING,
        "when": lambda m: m.get("testing", {}).get("test_cases", 0) == 0,
        "title": "Add a first automated test suite",
        "detail": "No test cases were detected. Start with the module that has the highest "
                  "cyclomatic complexity: a handful of tests around it is the single biggest "
                  "improvement available on this repository, and it is strong ownership evidence.",
        "impact": "high", "effort": "medium",
    },
    {
        "category": ScoreCategory.TESTING,
        "when": lambda m: m.get("testing", {}).get("test_cases", 0) > 0
        and not m.get("testing", {}).get("has_integration_tests"),
        "title": "Add integration tests across module boundaries",
        "detail": "Unit tests exist but nothing exercises components together. An integration test "
                  "that drives a real request through the stack demonstrates that the system works, "
                  "not just its parts.",
        "impact": "medium", "effort": "medium",
    },
    {
        "category": ScoreCategory.TESTING,
        "when": lambda m: not m.get("testing", {}).get("ci_runs_tests", False),
        "title": "Run the test suite in CI",
        "detail": "Add a workflow that runs the tests on every push. Tests that are not run "
                  "automatically stop being trusted, and reviewers read a green CI badge as "
                  "evidence of discipline.",
        "impact": "medium", "effort": "low",
    },
    {
        "category": ScoreCategory.DOCUMENTATION,
        "when": lambda m: m.get("documentation", {}).get("readme_words", 0) < 150,
        "title": "Expand the README into something a stranger can follow",
        "detail": "Cover what the project does, how to run it, how it is structured and what its "
                  "limitations are. A reviewer who cannot run your project will not score it.",
        "impact": "high", "effort": "low",
    },
    {
        "category": ScoreCategory.DOCUMENTATION,
        "when": lambda m: not (m.get("documentation", {}).get("features") or {}).get("architecture"),
        "title": "Document the architecture and the decisions behind it",
        "detail": "Explain the components and why you chose them over the alternatives. This is the "
                  "strongest written evidence of ownership a repository can carry.",
        "impact": "medium", "effort": "low",
    },
    {
        "category": ScoreCategory.TECHNICAL_QUALITY,
        "when": lambda m: m.get("code_metrics", {}).get("high_complexity_functions", 0) > 0,
        "title": "Break up the most complex functions",
        "detail": "Several functions exceed a cyclomatic complexity of 15. Extracting their branches "
                  "into named helpers improves both the score and reviewability.",
        "impact": "medium", "effort": "medium",
    },
    {
        "category": ScoreCategory.TECHNICAL_QUALITY,
        "when": lambda m: m.get("code_metrics", {}).get("duplication_ratio", 0.0) > 0.12,
        "title": "Remove duplicated blocks",
        "detail": "More than 12% of code blocks are duplicated. Factoring them out reduces the "
                  "maintenance surface and removes a signal reviewers read as copy-paste development.",
        "impact": "medium", "effort": "medium",
    },
    {
        "category": ScoreCategory.TECHNICAL_QUALITY,
        "when": lambda m: m.get("code_metrics", {}).get("error_handling_per_function", 0.0) < 0.02,
        "title": "Handle failure paths explicitly",
        "detail": "No error-handling constructs were found. Decide what happens when I/O, the "
                  "network or user input fails, and make that visible in the code.",
        "impact": "medium", "effort": "medium",
    },
    {
        "category": ScoreCategory.SECURITY,
        "when": lambda m: m.get("security", {}).get("secret_findings", 0) > 0,
        "title": "Remove hardcoded credentials and rotate them",
        "detail": "Credential-shaped values were found in source. Move them to environment "
                  "variables, rotate the real values, and add a .env.example documenting the names. "
                  "Committed secrets stay in git history even after deletion.",
        "impact": "high", "effort": "low",
    },
    {
        "category": ScoreCategory.SECURITY,
        "when": lambda m: m.get("security", {}).get("pattern_findings", 0) > 0,
        "title": "Address the flagged insecure patterns",
        "detail": "Static analysis flagged patterns such as string-built SQL or shell invocation "
                  "with interpolated input. Each finding lists the file, line and a remediation.",
        "impact": "high", "effort": "medium",
    },
    {
        "category": ScoreCategory.ARCHITECTURE,
        "when": lambda m: not m.get("architecture", {}).get("layers_detected"),
        "title": "Introduce a clear module structure",
        "detail": "No conventional layering was detected. Separating routing, business logic and "
                  "data access makes the project navigable and testable.",
        "impact": "medium", "effort": "high",
    },
    {
        "category": ScoreCategory.ARCHITECTURE,
        "when": lambda m: len(m.get("architecture", {}).get("import_cycles") or []) > 0,
        "title": "Break the circular imports",
        "detail": "Circular imports between modules make the codebase fragile to change and often "
                  "indicate a missing abstraction.",
        "impact": "medium", "effort": "medium",
    },
    {
        "category": ScoreCategory.ARCHITECTURE,
        "when": lambda m: not m.get("dependencies", {}).get("lock_files"),
        "title": "Commit a dependency lock file",
        "detail": "Without a lock file the build is not reproducible: two people installing today "
                  "can get different versions.",
        "impact": "low", "effort": "low",
    },
    {
        "category": ScoreCategory.GIT_ENGINEERING,
        "when": lambda m: m.get("git_history", {}).get("low_effort_message_ratio", 0.0) > 0.3,
        "title": "Write commit messages that describe intent",
        "detail": "A third or more of commits use non-descriptive messages. Commit history is the "
                  "clearest record that you built this incrementally.",
        "impact": "medium", "effort": "low",
    },
    {
        "category": ScoreCategory.GIT_ENGINEERING,
        "when": lambda m: m.get("git_history", {}).get("commit_count", 0) <= 3,
        "title": "Develop in visible increments",
        "detail": "Very few commits means there is no observable development history, which is the "
                  "main artefact reviewers use to assess ownership. Commit as you work.",
        "impact": "high", "effort": "low",
    },
    {
        "category": ScoreCategory.OWNERSHIP,
        "when": lambda m: m.get("ownership", {}).get("ownership_confidence", 100.0) < 60,
        "title": "Strengthen the evidence that this is your work",
        "detail": "Ownership confidence is low, which usually means thin history, no tests and a "
                  "short README rather than anything suspicious. Iterating visibly, adding tests "
                  "and writing about your design decisions all raise it.",
        "impact": "high", "effort": "medium",
    },
]


@dataclass(slots=True)
class Recommendation:
    category: str
    title: str
    detail: str
    impact: str
    effort: str
    expected_gain: float | None = None
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category, "title": self.title, "detail": self.detail,
            "impact": self.impact, "effort": self.effort,
            "expected_gain": self.expected_gain, "evidence_ids": self.evidence_ids,
        }


def generate(
    analyzer_metrics: dict[str, dict[str, Any]],
    category_scores: dict[str, float | None],
    weights: dict[str, float],
    evidence: list[dict[str, Any]] | None = None,
    missing_job_skills: list[str] | None = None,
) -> list[Recommendation]:
    """Produce ranked recommendations.

    ``expected_gain`` is the overall-score movement if the category were lifted
    to 85, given the policy weight. It is arithmetic on the actual weighting, not
    an estimate.
    """
    evidence = evidence or []
    recommendations: list[Recommendation] = []

    for rule in _RULES:
        try:
            if not rule["when"](analyzer_metrics):
                continue
        except (TypeError, AttributeError, KeyError):
            continue
        category = str(rule["category"])
        current = category_scores.get(category)
        weight = weights.get(category, 0.0)
        gain = (
            round(max(0.0, 85.0 - current) * weight, 2)
            if current is not None and weight else None
        )
        recommendations.append(Recommendation(
            category=category, title=rule["title"], detail=rule["detail"],
            impact=rule["impact"], effort=rule["effort"], expected_gain=gain,
            evidence_ids=[
                e["id"] for e in evidence
                if e.get("category") == category and e.get("supports") == "weakness"
            ][:3],
        ))

    for skill in (missing_job_skills or [])[:4]:
        weight = weights.get(str(ScoreCategory.JOB_RELEVANCE), 0.0)
        current = category_scores.get(str(ScoreCategory.JOB_RELEVANCE))
        recommendations.append(Recommendation(
            category=str(ScoreCategory.JOB_RELEVANCE),
            title=f"Build something that demonstrates {skill}",
            detail=f"The target role asks for {skill} and no evidence of it was found in this "
                   "repository. A small, focused project that genuinely uses it is worth more than "
                   "adding it to a skills list.",
            impact="high", effort="high",
            expected_gain=round(max(0.0, 85.0 - current) * weight / max(1, len(missing_job_skills or [])), 2)
            if current is not None and weight else None,
        ))

    impact_rank = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(
        key=lambda r: (impact_rank.get(r.impact, 3), -(r.expected_gain or 0.0))
    )
    return recommendations
