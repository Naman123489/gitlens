"""Resource budgets protecting the workers from hostile or huge repositories."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnalysisLimits:
    max_repository_bytes: int = 256 * 1024 * 1024
    max_files: int = 12_000
    max_analysed_files: int = 4_000
    max_file_bytes: int = 1 * 1024 * 1024
    max_ast_file_bytes: int = 512 * 1024
    max_line_length: int = 5_000
    max_commits: int = 5_000
    analysis_timeout_seconds: int = 900
    clone_timeout_seconds: int = 300
    max_chunks_per_repository: int = 8_000


DEFAULT_LIMITS = AnalysisLimits()


class LimitExceeded(RuntimeError):
    """Raised when a repository exceeds a hard budget and cannot be analysed."""

    def __init__(self, limit_name: str, detail: str) -> None:
        super().__init__(f"{limit_name}: {detail}")
        self.limit_name = limit_name
        self.detail = detail
