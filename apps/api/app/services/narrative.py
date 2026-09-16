"""Human-readable explanations built from evidence.

Every function here has a deterministic implementation that works with no model
configured. When an LLM is available it rewrites the same evidence into better
prose; if the call fails the deterministic text is used and ``generated_by``
records which happened. No narrative can introduce a fact that is not already in
the evidence it was given.
"""

from __future__ import annotations

from typing import Any

from app.services import llm


def _top(items: list[dict[str, Any]], supports: str, limit: int = 4) -> list[dict[str, Any]]:
    return [e for e in items if e.get("supports") == supports][:limit]


def evaluation_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Summarise an evaluation for a reviewer."""
    scores = {s["category"]: s.get("score") for s in payload.get("scores", []) if s.get("available")}
    evidence = payload.get("evidence", [])
    strengths = _top(evidence, "strength")
    weaknesses = _top(evidence, "weakness")

    deterministic = _deterministic_summary(payload, scores, strengths, weaknesses)
    if not llm.is_available():
        return {"text": deterministic, "generated_by": "deterministic", "model": None}

    response = llm.complete(
        llm.evidence_prompt(
            task="Write a 120-180 word summary of this repository evaluation for a technical "
                 "interviewer preparing for a conversation.",
            evidence={
                "overall_score": payload.get("overall_score"),
                "verification_status": payload.get("verification_status"),
                "verification_reasons": payload.get("verification_reasons"),
                "category_scores": scores,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "ai_analysis": payload.get("ai_analysis"),
                "limitations": payload.get("limitations", [])[:5],
            },
            instructions=(
                "Open with what the repository demonstrates. Name specific evidence. Then state "
                "what is weak or unverified. If the verification status is not CLEAR, say what the "
                "interviewer should ask about, framed as verification rather than suspicion. "
                "Do not restate every number. Plain prose, no headings, no bullet points."
            ),
        )
    )
    if response.generated_by == "llm" and response.text:
        return {"text": response.text, "generated_by": "llm", "model": response.model}
    return {"text": deterministic, "generated_by": "deterministic", "model": None,
            "fallback_reason": response.error}


def _deterministic_summary(
    payload: dict[str, Any], scores: dict[str, Any],
    strengths: list[dict[str, Any]], weaknesses: list[dict[str, Any]],
) -> str:
    overall = payload.get("overall_score")
    status = payload.get("verification_status", "ANALYSIS_INCOMPLETE")
    parts: list[str] = []

    if overall is not None:
        best = sorted(
            ((k, v) for k, v in scores.items() if v is not None), key=lambda kv: -kv[1]
        )[:2]
        parts.append(
            f"This repository scores {overall:.0f}/100 overall against the selected policy"
            + (f", with its strongest dimensions being "
               f"{' and '.join(k.replace('_', ' ') + f' ({v:.0f})' for k, v in best)}." if best else ".")
        )
    else:
        parts.append("An overall score could not be computed for this repository.")

    if strengths:
        parts.append("Evidence of strength: " + "; ".join(e["claim"] for e in strengths[:3]) + ".")
    if weaknesses:
        parts.append("Gaps found: " + "; ".join(e["claim"] for e in weaknesses[:3]) + ".")

    reasons = payload.get("verification_reasons") or []
    if status == "CLEAR":
        parts.append("No ownership, similarity or completeness concerns were raised.")
    else:
        parts.append(
            f"Status: {status.replace('_', ' ').lower()}. " + (reasons[0] if reasons else "")
        )
    return " ".join(p for p in parts if p).strip()


def score_explanation(category: str, metrics: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Explain one category score: why it is what it is, and how to improve it."""
    supporting = [e for e in evidence if e.get("category") == category]
    deterministic = _deterministic_score_explanation(category, metrics, supporting)
    if not llm.is_available():
        return {"text": deterministic, "generated_by": "deterministic"}

    response = llm.complete(
        llm.evidence_prompt(
            task=f"Explain the '{category}' score of a repository evaluation to the developer who "
                 "wrote the code.",
            evidence={"category": category, "metrics": metrics, "evidence": supporting[:8]},
            instructions=(
                "Three short paragraphs: what the score reflects, which specific evidence drove it, "
                "and the two highest-impact changes that would raise it. Reference real files and "
                "metrics from the evidence. Encouraging but honest. No headings."
            ),
        ),
        max_tokens=700,
    )
    if response.generated_by == "llm" and response.text:
        return {"text": response.text, "generated_by": "llm", "model": response.model}
    return {"text": deterministic, "generated_by": "deterministic"}


def _deterministic_score_explanation(
    category: str, metrics: dict[str, Any], evidence: list[dict[str, Any]]
) -> str:
    label = category.replace("_", " ")
    sub_scores = metrics.get("sub_scores") or {}
    lines = [f"The {label} score is a weighted combination of measured sub-metrics."]
    if sub_scores:
        ranked = sorted(sub_scores.items(), key=lambda kv: kv[1])
        lines.append(
            "Weakest components: "
            + ", ".join(f"{k.replace('_', ' ')} ({v:.0f}/100)" for k, v in ranked[:3])
            + ". Strongest: "
            + ", ".join(f"{k.replace('_', ' ')} ({v:.0f}/100)" for k, v in ranked[-2:])
            + "."
        )
    weaknesses = [e for e in evidence if e.get("supports") == "weakness"]
    if weaknesses:
        lines.append("Improving this score starts with: "
                     + "; ".join(e["claim"] for e in weaknesses[:3]) + ".")
    return " ".join(lines)
