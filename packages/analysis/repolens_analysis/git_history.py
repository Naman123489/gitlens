"""Git history analysis and the Engineering Evolution score.

Produces two things:

1. A ``git_engineering`` score: commit hygiene, message quality, branching,
   releases, contributor structure.
2. Evolution signals consumed by the ownership analyzer: does the repository
   show the shape of software that was *built* (implement -> fix -> refactor ->
   test -> document -> deploy), or the shape of software that simply appeared?

Unusual patterns are reported as **signals**, never as proof. A large initial
commit is a normal way to publish existing work; it is recorded and weighted,
not treated as misconduct.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta

from repolens_shared import AnalyzerResult, Evidence, EvidenceDetail, ScoreCategory, Severity
from repolens_shared.textutils import clamp, scale

from .git_collect import Commit, GitHistory

ANALYZER_NAME = "git_history"
ANALYZER_VERSION = "1.0.0"

#: Commit-intent classification from the message. Ordered: first match wins.
COMMIT_INTENTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("revert", re.compile(r"^\s*revert\b", re.I)),
    ("merge", re.compile(r"^\s*merge\b", re.I)),
    ("fix", re.compile(r"\b(fix|bug ?fix|hotfix|patch|resolve[sd]?|correct|repair)\b", re.I)),
    ("test", re.compile(r"\b(test|tests|testing|spec|coverage)\b", re.I)),
    ("refactor", re.compile(r"\b(refactor|restructure|clean ?up|simplify|rename|extract|"
                            r"reorganis|reorganiz|tidy)\b", re.I)),
    ("perf", re.compile(r"\b(perf|performance|optimi[sz]e|speed ?up|cache|faster)\b", re.I)),
    ("docs", re.compile(r"\b(docs?|documentation|readme|comment)\b", re.I)),
    ("deploy", re.compile(r"\b(deploy|release|ci|cd|docker|pipeline|build|publish|"
                          r"workflow|infra)\b", re.I)),
    ("style", re.compile(r"\b(style|format|lint|prettier|black|eslint|whitespace)\b", re.I)),
    ("chore", re.compile(r"\b(chore|bump|upgrade|dependency|deps|version|config)\b", re.I)),
    ("feature", re.compile(r"\b(add(s|ed|ing)?|implement\w*|feat|features?|creat\w+|"
                           r"introduc\w+|support|initial|scaffold\w*)\b", re.I)),
)

_LOW_EFFORT_MESSAGES = re.compile(
    r"^\s*(update|updates|updated|changes?|edit|edits|stuff|wip|temp|test|asdf|"
    r"fix|fixes|fixed|misc|minor|final|done|new|commit|\.|x+|\d+)\s*[.!]*\s*$",
    re.I,
)
_CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]*\))?!?:\s+\S", re.I
)

#: Weights inside the git-engineering score.
GIT_WEIGHTS = {
    "volume": 0.18,
    "cadence": 0.20,
    "message_quality": 0.22,
    "commit_size": 0.15,
    "branching": 0.12,
    "releases": 0.13,
}

#: The evolution phases that make up the Engineering Evolution score.
EVOLUTION_PHASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("initial_implementation", ("feature",)),
    ("bug_fixes", ("fix",)),
    ("refactoring", ("refactor",)),
    ("testing", ("test",)),
    ("optimization", ("perf",)),
    ("documentation", ("docs",)),
    ("deployment", ("deploy",)),
)


@dataclass(slots=True)
class HistorySignals:
    """Machine-readable signals handed to the ownership and AI analyzers."""

    commit_count: int = 0
    active_days: int = 0
    span_days: int = 0
    evolution_score: float = 0.0
    phases_present: list[str] = field(default_factory=list)
    initial_commit_share: float = 0.0
    largest_commit_share: float = 0.0
    median_commit_size: float = 0.0
    burst_days: list[str] = field(default_factory=list)
    longest_gap_days: int = 0
    contributor_count: int = 0
    candidate_commit_share: float = 1.0
    message_quality: float = 0.0
    low_effort_message_ratio: float = 0.0
    conventional_commit_ratio: float = 0.0
    single_commit_repository: bool = False


def classify_intent(message: str) -> str:
    subject = message.split("\n", 1)[0]
    for intent, pattern in COMMIT_INTENTS:
        if pattern.search(subject):
            return intent
    return "other"


def message_quality_score(commits: list[Commit]) -> tuple[float, float, float]:
    """Return ``(quality 0..1, low_effort_ratio, conventional_ratio)``."""
    if not commits:
        return 0.0, 0.0, 0.0
    low_effort = 0
    conventional = 0
    scores: list[float] = []
    for commit in commits:
        subject = commit.subject
        if _LOW_EFFORT_MESSAGES.match(subject):
            low_effort += 1
            scores.append(0.15)
            continue
        if _CONVENTIONAL_RE.match(subject):
            conventional += 1
        words = len(subject.split())
        length_score = clamp(scale(float(words), 1.0, 7.0), 0.0, 100.0) / 100.0
        body_bonus = 0.15 if len(commit.message.strip().splitlines()) > 2 else 0.0
        specificity = 0.15 if re.search(r"[a-z]+[._/][a-z]+|`|#\d+", subject, re.I) else 0.0
        scores.append(min(1.0, 0.7 * length_score + body_bonus + specificity))
    return (
        sum(scores) / len(scores),
        low_effort / len(commits),
        conventional / len(commits),
    )


def _candidate_commits(history: GitHistory, candidate_emails: set[str]) -> list[Commit]:
    if not candidate_emails:
        return [c for c in history.commits if not c.is_merge]
    normalised = {e.lower() for e in candidate_emails if e}
    return [
        c for c in history.commits
        if not c.is_merge and (c.author_email in normalised
                               or any(c.author_email.endswith(f"+{e}") for e in normalised))
    ]


def analyze_git_history(
    history: GitHistory,
    candidate_emails: set[str] | None = None,
) -> tuple[AnalyzerResult, HistorySignals]:
    """Analyze git history. Returns the scored result plus raw signals."""
    result = AnalyzerResult(analyzer=ANALYZER_NAME, version=ANALYZER_VERSION)
    signals = HistorySignals()

    if not history.available or not history.commits:
        result.score = None
        result.partial = True
        result.confidence = 0.0
        result.metrics = {"available": False, "reason": history.error or "no commits found"}
        result.add(Evidence(
            category=ScoreCategory.GIT_ENGINEERING,
            claim="Git history is unavailable for this repository",
            severity=Severity.INFO, confidence=0.95, supports="neutral", tags=("git",),
            evidence=(EvidenceDetail(detail=history.error or "no commits found"),),
        ))
        result.limit(
            "git_history",
            "No commit history was available, so development-evolution and ownership signals "
            "derived from git could not be computed. This is reported as missing data, not as a "
            "negative finding.",
        )
        return result, signals

    commits = sorted(history.commits, key=lambda c: c.committed_at)
    non_merge = [c for c in commits if not c.is_merge]
    mine = _candidate_commits(history, candidate_emails or set())
    subject_commits = mine or non_merge

    first, last = commits[0].committed_at, commits[-1].committed_at
    span_days = max(1, (last - first).days)
    active_days = len({c.committed_at.date() for c in commits})

    sizes = [c.size for c in non_merge] or [0]
    total_changed = sum(sizes) or 1
    initial_share = (non_merge[0].size / total_changed) if non_merge else 0.0
    largest_share = max(sizes) / total_changed

    by_day = Counter(c.committed_at.date() for c in non_merge)
    day_sizes: Counter = Counter()
    for commit in non_merge:
        day_sizes[commit.committed_at.date()] += commit.size
    median_day = statistics.median(day_sizes.values()) if day_sizes else 0
    burst_pairs = [
        (str(day), size) for day, size in sorted(day_sizes.items())
        if median_day and size > max(8 * median_day, 1500)
    ]
    burst_days = [day for day, _ in burst_pairs]

    gaps = [
        (commits[i + 1].committed_at - commits[i].committed_at).days
        for i in range(len(commits) - 1)
    ]
    longest_gap = max(gaps) if gaps else 0

    intents = Counter(classify_intent(c.message) for c in non_merge)
    phases_present = [
        name for name, keys in EVOLUTION_PHASES if any(intents.get(k, 0) for k in keys)
    ]
    # Evolution rewards breadth of phases and the presence of the phases that
    # only appear when somebody actually maintained the code.
    phase_weights = {
        "initial_implementation": 0.10, "bug_fixes": 0.22, "refactoring": 0.18,
        "testing": 0.20, "optimization": 0.08, "documentation": 0.12, "deployment": 0.10,
    }
    evolution = 100.0 * sum(phase_weights[p] for p in phases_present)

    quality, low_effort_ratio, conventional_ratio = message_quality_score(subject_commits)
    contributors = Counter(c.author_email for c in non_merge)
    candidate_share = (len(mine) / len(non_merge)) if non_merge and mine else (
        1.0 if not candidate_emails else 0.0
    )

    releases = [t for t in history.tags]
    feature_branches = [
        b for b in history.branches
        if b.split("/")[-1] not in ("HEAD", "main", "master", "develop", "dev")
    ]

    # --- sub-scores ----------------------------------------------------------
    volume = scale(float(len(non_merge)), 1.0, 60.0)
    cadence = 0.6 * scale(float(active_days), 1.0, 30.0) + 0.4 * scale(
        float(active_days) / span_days if span_days else 0.0, 0.0, 0.35
    )
    message_score = quality * 100.0
    # Commit-size score rewards incremental commits; a single huge commit scores
    # low here but that is a *hygiene* judgement, not an authorship judgement.
    size_score = scale(largest_share, 0.95, 0.25)
    branching = scale(float(len(feature_branches)), 0.0, 4.0)
    release_score = scale(float(len(releases)), 0.0, 3.0)

    subs = {
        "volume": volume, "cadence": cadence, "message_quality": message_score,
        "commit_size": size_score, "branching": branching, "releases": release_score,
    }
    score = sum(subs[k] * w for k, w in GIT_WEIGHTS.items())

    signals = HistorySignals(
        commit_count=len(non_merge),
        active_days=active_days,
        span_days=span_days,
        evolution_score=round(clamp(evolution), 2),
        phases_present=phases_present,
        initial_commit_share=round(initial_share, 4),
        largest_commit_share=round(largest_share, 4),
        median_commit_size=float(statistics.median(sizes)),
        burst_days=burst_days,
        longest_gap_days=longest_gap,
        contributor_count=len(contributors),
        candidate_commit_share=round(candidate_share, 4),
        message_quality=round(quality, 4),
        low_effort_message_ratio=round(low_effort_ratio, 4),
        conventional_commit_ratio=round(conventional_ratio, 4),
        single_commit_repository=len(non_merge) <= 1,
    )

    result.score = round(clamp(score), 2)
    result.confidence = 0.9 if len(non_merge) >= 5 else 0.55
    result.metrics = {
        "available": True,
        "commit_count": len(commits),
        "non_merge_commits": len(non_merge),
        "candidate_commits": len(mine),
        "candidate_commit_share": signals.candidate_commit_share,
        "contributors": len(contributors),
        "top_contributors": [{"email": e, "commits": n} for e, n in contributors.most_common(5)],
        "first_commit": first.isoformat(),
        "last_commit": last.isoformat(),
        "span_days": span_days,
        "active_days": active_days,
        "commits_per_active_day": round(len(non_merge) / active_days, 2) if active_days else 0,
        "median_commit_size": signals.median_commit_size,
        "largest_commit_share": signals.largest_commit_share,
        "initial_commit_share": signals.initial_commit_share,
        "longest_gap_days": longest_gap,
        "burst_days": burst_days,
        "branches": history.branches[:40],
        "feature_branches": len(feature_branches),
        "tags": releases[:40],
        "intents": dict(intents),
        "evolution_phases": phases_present,
        "evolution_score": signals.evolution_score,
        "message_quality": signals.message_quality,
        "low_effort_message_ratio": signals.low_effort_message_ratio,
        "conventional_commit_ratio": signals.conventional_commit_ratio,
        "timeline": _timeline(non_merge),
        "sub_scores": {k: round(v, 2) for k, v in subs.items()},
        "weights": GIT_WEIGHTS,
        "truncated": history.truncated,
    }

    # --- evidence ------------------------------------------------------------
    result.add(Evidence(
        category=ScoreCategory.GIT_ENGINEERING,
        claim=f"{len(non_merge)} commits over {span_days} day(s), active on {active_days} day(s)",
        severity=Severity.INFO, confidence=0.95,
        supports="strength" if len(non_merge) >= 20 and active_days >= 5 else "neutral",
        tags=("git", "cadence"),
        evidence=(
            EvidenceDetail(detail=f"first commit {first.date()}"),
            EvidenceDetail(detail=f"latest commit {last.date()}"),
            EvidenceDetail(detail=f"{round(len(non_merge) / active_days, 1) if active_days else 0} commits per active day"),
        ),
    ))

    if phases_present:
        result.add(Evidence(
            category=ScoreCategory.GIT_ENGINEERING,
            claim="Development evolution shows " + " → ".join(p.replace("_", " ") for p in phases_present),
            severity=Severity.INFO, confidence=0.8, supports="strength",
            tags=("git", "evolution", "ownership_signal"),
            evidence=tuple(
                EvidenceDetail(detail=f"{intents.get(key[0], 0)} {name.replace('_', ' ')} commit(s)")
                for name, key in EVOLUTION_PHASES if name in phases_present
            ),
        ))
    missing_phases = [name for name, _ in EVOLUTION_PHASES if name not in phases_present]
    if missing_phases:
        result.add(Evidence(
            category=ScoreCategory.GIT_ENGINEERING,
            claim=f"No commits indicate {', '.join(p.replace('_', ' ') for p in missing_phases)}",
            severity=Severity.LOW, confidence=0.6, supports="weakness",
            tags=("git", "evolution"),
            evidence=(EvidenceDetail(
                detail="commit-message classification found no commits in these phases"),),
        ))

    if signals.single_commit_repository:
        result.add(Evidence(
            category=ScoreCategory.GIT_ENGINEERING,
            claim="The repository contains a single commit, so development history is not observable",
            severity=Severity.MEDIUM, confidence=0.95, supports="weakness",
            tags=("git", "ownership_signal", "signal_only"),
            evidence=(EvidenceDetail(detail=f"commit {commits[0].sha[:8]}: "
                                            f"{commits[0].insertions} insertions across "
                                            f"{commits[0].files_changed} files",
                                     snippet=commits[0].subject[:120]),),
        ))
    elif initial_share > 0.75:
        result.add(Evidence(
            category=ScoreCategory.GIT_ENGINEERING,
            claim=f"The first commit contains {initial_share * 100:.0f}% of all changed lines",
            severity=Severity.LOW, confidence=0.85, supports="neutral",
            tags=("git", "signal_only", "ownership_signal"),
            evidence=(
                EvidenceDetail(detail=f"initial commit {non_merge[0].sha[:8]} changed "
                                      f"{non_merge[0].size} lines across {non_merge[0].files_changed} files"),
                EvidenceDetail(detail="This is a signal only. Importing existing work in one commit "
                                      "is a normal publishing pattern and is not evidence of misconduct."),
            ),
        ))

    if burst_days:
        result.add(Evidence(
            category=ScoreCategory.GIT_ENGINEERING,
            claim=f"{len(burst_days)} day(s) show unusually large growth relative to the project's median",
            severity=Severity.LOW, confidence=0.6, supports="neutral",
            tags=("git", "signal_only"),
            evidence=tuple(EvidenceDetail(detail=f"{day}: {size} lines changed", metric=float(size))
                           for day, size in burst_pairs[:4]),
        ))

    if low_effort_ratio > 0.3:
        result.add(Evidence(
            category=ScoreCategory.GIT_ENGINEERING,
            claim=f"{low_effort_ratio * 100:.0f}% of commit messages are non-descriptive",
            severity=Severity.MEDIUM, confidence=0.8, supports="weakness", tags=("git", "messages"),
            evidence=tuple(EvidenceDetail(detail=f"{c.sha[:8]}: \"{c.subject}\"")
                           for c in subject_commits if _LOW_EFFORT_MESSAGES.match(c.subject))[:5],
        ))
    elif quality > 0.6:
        result.add(Evidence(
            category=ScoreCategory.GIT_ENGINEERING,
            claim="Commit messages are descriptive",
            severity=Severity.INFO, confidence=0.75, supports="strength", tags=("git", "messages"),
            evidence=tuple(EvidenceDetail(detail=f"{c.sha[:8]}: \"{c.subject[:80]}\"")
                           for c in subject_commits[-4:]),
        ))

    if len(contributors) > 1:
        result.add(Evidence(
            category=ScoreCategory.GIT_ENGINEERING,
            claim=f"{len(contributors)} contributors appear in the history",
            severity=Severity.INFO, confidence=0.9,
            supports="neutral", tags=("git", "contributors", "ownership_signal"),
            evidence=tuple(EvidenceDetail(detail=f"{email}: {count} commit(s)")
                           for email, count in contributors.most_common(5)),
        ))

    if releases:
        result.add(Evidence(
            category=ScoreCategory.GIT_ENGINEERING,
            claim=f"{len(releases)} release tag(s) published",
            severity=Severity.INFO, confidence=0.9, supports="strength", tags=("git", "releases"),
            evidence=tuple(EvidenceDetail(detail=tag) for tag in releases[:5]),
        ))

    if history.truncated:
        result.limit("git_history",
                     "Commit history was truncated at the configured maximum; long-term trends may be incomplete.")
    if candidate_emails and not mine:
        result.partial = True
        result.limit(
            "attribution",
            "No commits matched the candidate's known email addresses, so per-author attribution "
            "could not be established. Commit authorship is self-reported in git and can be set freely.",
        )
    return result, signals


def _timeline(commits: list[Commit], buckets: int = 24) -> list[dict[str, object]]:
    """Commit activity bucketed over the project's lifetime, for charting."""
    if not commits:
        return []
    start = commits[0].committed_at
    end = commits[-1].committed_at
    total = max(timedelta(days=1), end - start)
    step = total / buckets
    series = [{"start": (start + step * i).date().isoformat(), "commits": 0, "lines": 0}
              for i in range(buckets)]
    for commit in commits:
        index = min(buckets - 1, int((commit.committed_at - start) / step))
        series[index]["commits"] = int(series[index]["commits"]) + 1
        series[index]["lines"] = int(series[index]["lines"]) + commit.size
    return series
