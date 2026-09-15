"""Analyzer and prompt versioning.

Every evaluation persists the versions it was produced with so that a historic
evaluation can be explained and reproduced, and so that changing an analyzer
never silently rewrites past results.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Bump when any analyzer changes in a way that can change its output.
ANALYZER_VERSION = "1.0.0"

#: Bump when the deterministic scoring maths changes.
SCORING_ENGINE_VERSION = "1.0.0"

#: Bump when an LLM prompt template changes.
PROMPT_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class RunVersions:
    analyzer_version: str = ANALYZER_VERSION
    scoring_engine_version: str = SCORING_ENGINE_VERSION
    prompt_version: str = PROMPT_VERSION
    policy_version: int | None = None
    llm_model: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "analyzer_version": self.analyzer_version,
            "scoring_engine_version": self.scoring_engine_version,
            "prompt_version": self.prompt_version,
            "policy_version": self.policy_version,
            "llm_model": self.llm_model,
        }
