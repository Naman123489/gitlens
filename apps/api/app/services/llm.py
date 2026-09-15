"""Optional LLM layer.

The LLM is allowed to do exactly one thing: turn structured evidence that
RepoLens already computed into readable prose. It is never given the authority
to produce a score, a verification status or a classification, and every prompt
is built from evidence objects rather than from raw repository code.

With no ``LLM_API_KEY`` configured the deterministic templates below are used and
the product is fully functional; responses are marked with ``generated_by`` so
the UI can say which path produced the text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from repolens_shared.versioning import PROMPT_VERSION

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("repolens.llm")

SYSTEM_PROMPT = (
    "You are a technical reviewer writing an explanation for an engineering evaluation report.\n"
    "You will be given structured evidence that has already been computed by static analysis.\n\n"
    "Rules you must follow:\n"
    "1. Only state things that are supported by the evidence provided. Never invent a fact, a "
    "file name, a metric or a finding.\n"
    "2. Never assign or revise a score. Scores are computed deterministically and are given to "
    "you as inputs.\n"
    "3. Never assert that code was written by an AI. AI-assistance figures are probabilistic "
    "estimates; describe them as such, with their limitations.\n"
    "4. Never recommend rejecting a candidate. Where evidence is thin, recommend verification.\n"
    "5. Do not comment on anything other than the technical evidence. Never infer or mention any "
    "protected or personal characteristic.\n"
    "6. Be concise and concrete. Prefer naming the specific evidence over general praise."
)


@dataclass(slots=True)
class LLMResponse:
    text: str
    generated_by: str
    model: str | None = None
    prompt_version: str = PROMPT_VERSION
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text, "generated_by": self.generated_by, "model": self.model,
            "prompt_version": self.prompt_version, "error": self.error,
        }


def is_available() -> bool:
    return get_settings().llm_configured


def complete(prompt: str, max_tokens: int | None = None) -> LLMResponse:
    """Call the configured model. Falls back cleanly, never raises."""
    settings = get_settings()
    if not settings.llm_configured:
        return LLMResponse(text="", generated_by="unavailable",
                           error="No LLM_API_KEY is configured.")
    try:
        response = httpx.post(
            f"{settings.llm_base_url.rstrip('/')}/v1/messages",
            headers={
                "x-api-key": settings.llm_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "max_tokens": max_tokens or settings.llm_max_output_tokens,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=settings.llm_timeout_seconds,
        )
        if response.status_code >= 400:
            logger.warning("llm_error", status=response.status_code, body=response.text[:200])
            return LLMResponse(text="", generated_by="error", model=settings.llm_model,
                               error=f"LLM returned {response.status_code}")
        payload = response.json()
        text = "".join(
            block.get("text", "") for block in payload.get("content", [])
            if block.get("type") == "text"
        )
        return LLMResponse(text=text.strip(), generated_by="llm", model=settings.llm_model)
    except Exception as exc:  # noqa: BLE001 - the LLM is optional; never fail the request
        logger.warning("llm_call_failed", error=str(exc)[:200])
        return LLMResponse(text="", generated_by="error", model=settings.llm_model,
                           error=f"{type(exc).__name__}: {exc}"[:200])


def evidence_prompt(task: str, evidence: dict[str, Any], instructions: str) -> str:
    """Build a prompt that contains only structured evidence, never raw code."""
    return (
        f"Task: {task}\n\n"
        f"Structured evidence (JSON):\n```json\n{json.dumps(evidence, indent=2, default=str)[:12000]}\n```\n\n"
        f"Instructions:\n{instructions}"
    )
