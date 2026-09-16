"""Repository walking, file reading and content hashing.

The walker never executes anything from the repository. It reads bytes, decodes
them defensively, hashes them for incremental analysis, and classifies them.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from repolens_shared import FileCategory

from .classification import classify, should_ignore
from .languages import detect_language
from .limits import DEFAULT_LIMITS, AnalysisLimits, LimitExceeded

_HEAD_BYTES = 1024


@dataclass(slots=True)
class RepoFile:
    """One analysed file."""

    path: str
    size_bytes: int
    content_hash: str
    category: FileCategory
    language: str | None
    line_count: int
    text: str | None = None
    truncated: bool = False
    skipped_reason: str | None = None

    @property
    def is_source(self) -> bool:
        return self.category in (FileCategory.CANDIDATE_CODE, FileCategory.TEST_CODE)


@dataclass(slots=True)
class WalkResult:
    files: list[RepoFile] = field(default_factory=list)
    total_files_seen: int = 0
    ignored_files: int = 0
    total_bytes: int = 0
    truncated: bool = False
    notes: list[str] = field(default_factory=list)

    def by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for file in self.files:
            counts[str(file.category)] = counts.get(str(file.category), 0) + 1
        return counts

    def sources(self) -> list[RepoFile]:
        return [f for f in self.files if f.is_source and f.text is not None]


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode(data: bytes) -> str | None:
    """Decode to text or return ``None`` if the file is binary-looking."""
    if b"\x00" in data[:8192]:
        return None
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def walk_repository(
    root: str | Path,
    limits: AnalysisLimits = DEFAULT_LIMITS,
    load_text: bool = True,
) -> WalkResult:
    """Walk ``root`` and return classified, hashed files.

    Raises :class:`LimitExceeded` only for repository-level budgets; per-file
    budget breaches are recorded on the file as ``skipped_reason`` so the rest of
    the analysis continues.
    """
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise FileNotFoundError(f"repository root not found: {root_path}")

    result = WalkResult()
    analysed = 0

    for dirpath, dirnames, filenames in os.walk(root_path, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root_path)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        # Prune ignored directories in place so os.walk never descends into them.
        dirnames[:] = [
            d for d in dirnames
            if not should_ignore(f"{rel_dir}/{d}/x" if rel_dir else f"{d}/x")[0]
        ]

        for filename in filenames:
            rel_path = f"{rel_dir}/{filename}" if rel_dir else filename
            abs_path = Path(dirpath) / filename
            result.total_files_seen += 1

            if result.total_files_seen > limits.max_files:
                result.truncated = True
                result.notes.append(
                    f"walk stopped after {limits.max_files} files; repository is larger"
                )
                return result

            if abs_path.is_symlink() or not abs_path.is_file():
                result.ignored_files += 1
                continue

            ignored, reason = should_ignore(rel_path)
            if ignored:
                result.ignored_files += 1
                continue

            try:
                size = abs_path.stat().st_size
            except OSError as exc:  # pragma: no cover - filesystem race
                result.notes.append(f"stat failed for {rel_path}: {exc}")
                continue

            result.total_bytes += size
            if result.total_bytes > limits.max_repository_bytes:
                raise LimitExceeded(
                    "max_repository_bytes",
                    f"repository exceeds {limits.max_repository_bytes} bytes of analysable content",
                )

            if size > limits.max_file_bytes:
                result.files.append(
                    RepoFile(
                        path=rel_path, size_bytes=size, content_hash="",
                        category=FileCategory.IGNORED, language=detect_language(rel_path),
                        line_count=0, skipped_reason=f"file larger than {limits.max_file_bytes} bytes",
                    )
                )
                continue

            try:
                data = abs_path.read_bytes()
            except OSError as exc:  # pragma: no cover - filesystem race
                result.notes.append(f"read failed for {rel_path}: {exc}")
                continue

            content_hash = hash_bytes(data)
            text = _decode(data)
            if text is None:
                result.files.append(
                    RepoFile(
                        path=rel_path, size_bytes=size, content_hash=content_hash,
                        category=FileCategory.ASSET, language=None, line_count=0,
                        skipped_reason="binary content",
                    )
                )
                continue

            head = text[:_HEAD_BYTES]
            category = classify(rel_path, head)
            first_line = text.split("\n", 1)[0] if text else None
            language = detect_language(rel_path, first_line)
            line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)

            keep_text = load_text and category not in (
                FileCategory.IGNORED, FileCategory.ASSET
            )
            if keep_text and analysed >= limits.max_analysed_files:
                keep_text = False
                result.truncated = True

            if keep_text:
                analysed += 1

            result.files.append(
                RepoFile(
                    path=rel_path,
                    size_bytes=size,
                    content_hash=content_hash,
                    category=category,
                    language=language,
                    line_count=line_count,
                    text=text if keep_text else None,
                    skipped_reason=None if keep_text else (
                        f"analysed-file budget of {limits.max_analysed_files} reached"
                        if result.truncated else None
                    ),
                )
            )

    if result.truncated:
        result.notes.append(
            f"only the first {limits.max_analysed_files} eligible files were read in full"
        )
    return result
