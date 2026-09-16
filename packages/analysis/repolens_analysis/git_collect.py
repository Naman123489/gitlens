"""Read git history from a local clone.

Uses ``git`` in a read-only, plumbing-only fashion. Hooks are disabled by the
fetcher when the clone is created, and no command here can execute repository
content.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .limits import DEFAULT_LIMITS, AnalysisLimits

_SEP = "\x1f"
_REC = "\x1e"

#: A --numstat line: "<added>\t<removed>\t<path>", where a binary file uses "-".
_NUMSTAT_RE = re.compile(r"^(\d+|-)\t(\d+|-)\t(.+)$")


def _split_message_and_numstat(tail: str) -> tuple[str, list[str]]:
    """Separate a commit message from the --numstat block that follows it.

    The commit message is free text and may itself contain blank lines, so the
    split cannot be done on a blank line. Instead the trailing run of lines that
    parse as numstat records is peeled off the end.
    """
    lines = tail.splitlines()
    index = len(lines)
    while index > 0:
        line = lines[index - 1]
        if not line.strip() or _NUMSTAT_RE.match(line):
            index -= 1
            continue
        break
    return "\n".join(lines[:index]), [l for l in lines[index:] if _NUMSTAT_RE.match(l)]


@dataclass(slots=True)
class Commit:
    sha: str
    author_name: str
    author_email: str
    committed_at: datetime
    message: str
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    is_merge: bool = False
    files: list[str] = field(default_factory=list)

    @property
    def subject(self) -> str:
        return self.message.split("\n", 1)[0].strip()

    @property
    def size(self) -> int:
        return self.insertions + self.deletions


@dataclass(slots=True)
class GitHistory:
    commits: list[Commit] = field(default_factory=list)
    branches: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    default_branch: str | None = None
    truncated: bool = False
    available: bool = True
    error: str | None = None


def _run(args: list[str], cwd: Path, timeout: int) -> str:
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", *args],
        cwd=cwd, capture_output=True, text=True, timeout=timeout,
        env={"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(cwd),
             "PATH": "/usr/bin:/bin:/usr/local/bin"},
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[:400] or f"git {args[0]} failed")
    return result.stdout


def collect_history(
    repo_path: str | Path, limits: AnalysisLimits = DEFAULT_LIMITS
) -> GitHistory:
    """Collect commits, branches and tags from a clone.

    Never raises: a repository without git metadata (for example a tarball
    download) comes back with ``available=False`` and an ``error``, and the
    git-history analyzer then reports itself unavailable instead of guessing.
    """
    path = Path(repo_path)
    history = GitHistory()
    if not (path / ".git").exists():
        history.available = False
        history.error = "no .git directory: repository was not obtained as a git clone"
        return history

    timeout = min(120, limits.clone_timeout_seconds)
    try:
        # The record separator leads each record: git appends the --numstat
        # block *after* the formatted fields, so a trailing separator would
        # attach each commit's numstat to the following record.
        fmt = _REC + _SEP.join(["%H", "%an", "%ae", "%aI", "%P", "%B"])
        raw = _run(
            ["log", f"--max-count={limits.max_commits}", f"--pretty=format:{fmt}",
             "--numstat", "--no-color"],
            path, timeout,
        )
    except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
        history.available = False
        history.error = f"git log failed: {exc}"
        return history

    for record in raw.split(_REC):
        if not record.strip():
            continue
        parts = record.split(_SEP)
        if len(parts) < 6:
            continue
        message, numstat_lines = _split_message_and_numstat(parts[5])
        try:
            committed_at = datetime.fromisoformat(parts[3].strip())
        except ValueError:
            continue
        if committed_at.tzinfo is None:
            committed_at = committed_at.replace(tzinfo=timezone.utc)

        insertions = deletions = 0
        files: list[str] = []
        for line in numstat_lines:
            match = _NUMSTAT_RE.match(line)
            if match is None:
                continue
            added, removed, filename = match.groups()
            insertions += int(added) if added.isdigit() else 0
            deletions += int(removed) if removed.isdigit() else 0
            if len(files) < 200:
                files.append(filename)

        history.commits.append(
            Commit(
                sha=parts[0].strip()[:64], author_name=parts[1][:200],
                author_email=parts[2].lower()[:320],
                committed_at=committed_at.astimezone(timezone.utc),
                message=message.strip(), files_changed=len(files),
                insertions=insertions, deletions=deletions,
                is_merge=len(parts[4].split()) > 1, files=files,
            )
        )

    history.truncated = len(history.commits) >= limits.max_commits
    for args, target in ((["branch", "-a", "--format=%(refname:short)"], history.branches),
                         (["tag", "--list"], history.tags)):
        try:
            target.extend(line.strip() for line in _run(args, path, 30).splitlines() if line.strip())
        except (RuntimeError, subprocess.TimeoutExpired, OSError):
            continue
    try:
        history.default_branch = _run(["rev-parse", "--abbrev-ref", "HEAD"], path, 20).strip()
    except (RuntimeError, subprocess.TimeoutExpired, OSError):
        history.default_branch = None
    return history
