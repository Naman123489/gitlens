"""Report generation.

Reports are assembled from persisted evaluation data only — nothing is
recomputed at render time, so a report always reflects the evaluation as it was
scored, including its policy version and analyzer version.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, DbSession
from app.models import (
    Candidate,
    Evaluation,
    EvaluationScore,
    EvidenceRecord,
    HumanOverride,
    InterviewAnswer,
    InterviewQuestion,
    InterviewSession,
    Job,
    Recommendation,
    Repository,
    ReviewerNote,
    SecurityFinding,
    SimilarityResult,
)
from app.services import audit
from app.api.v1.evaluations import _visible_evaluation

router = APIRouter(prefix="/reports", tags=["reports"])


def _build(db: Session, evaluation: Evaluation, include_private: bool) -> dict[str, Any]:
    repository = db.get(Repository, evaluation.repository_id)
    job = db.get(Job, evaluation.job_id) if evaluation.job_id else None
    candidate = db.get(Candidate, evaluation.candidate_id) if evaluation.candidate_id else None
    scores = db.query(EvaluationScore).filter(
        EvaluationScore.evaluation_id == evaluation.id
    ).all()
    evidence = db.query(EvidenceRecord).filter(
        EvidenceRecord.evaluation_id == evaluation.id
    ).all()
    recommendations = db.query(Recommendation).filter(
        Recommendation.evaluation_id == evaluation.id
    ).all()
    findings = (
        db.query(SecurityFinding)
        .filter(SecurityFinding.repository_id == evaluation.repository_id)
        .order_by(SecurityFinding.confidence.desc()).limit(25).all()
    )
    similarity = (
        db.query(SimilarityResult)
        .filter(
            SimilarityResult.repository_id == evaluation.repository_id,
            SimilarityResult.scope == "external",
        )
        .order_by(SimilarityResult.similarity.desc()).limit(10).all()
    )
    sessions = (
        db.query(InterviewSession)
        .filter(InterviewSession.evaluation_id == evaluation.id)
        .order_by(InterviewSession.created_at.desc()).all()
    )
    questions = (
        db.query(InterviewQuestion)
        .filter(InterviewQuestion.evaluation_id == evaluation.id).limit(20).all()
    )
    notes_query = db.query(ReviewerNote).filter(ReviewerNote.evaluation_id == evaluation.id)
    if not include_private:
        notes_query = notes_query.filter(ReviewerNote.visible_to_candidate.is_(True))
    notes = notes_query.order_by(ReviewerNote.created_at.desc()).all()
    overrides = db.query(HumanOverride).filter(
        HumanOverride.evaluation_id == evaluation.id
    ).all()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate": {
            "name": candidate.full_name if candidate else None,
            "github_login": candidate.github_login if candidate else None,
            "headline": candidate.headline if candidate else None,
        },
        "target_job": {
            "title": job.title if job else None,
            "experience_level": job.experience_level if job else None,
            "domain": job.domain if job else None,
            "requirements": [
                {"label": r.label, "required": r.required, "importance": r.importance}
                for r in (job.requirements if job else [])
            ],
        },
        "repository": {
            "full_name": repository.full_name if repository else None,
            "description": repository.description if repository else None,
            "url": repository.html_url if repository else None,
            "primary_language": repository.primary_language if repository else None,
        },
        "overall": {
            "score": evaluation.overall_score,
            "confidence": evaluation.confidence,
            "job_match": evaluation.job_match,
            "ownership_confidence": evaluation.ownership_confidence,
            "ai_utilization": evaluation.ai_utilization,
            "verification_status": evaluation.verification_status,
            "verification_reasons": evaluation.verification_reasons,
        },
        "summary": (evaluation.narrative or {}).get("text"),
        "summary_generated_by": (evaluation.narrative or {}).get("generated_by"),
        "scores": [
            {
                "category": s.category, "score": s.score, "weight": s.weight,
                "confidence": s.confidence, "available": s.available,
                "unavailable_reason": s.unavailable_reason,
            }
            for s in sorted(scores, key=lambda x: -x.weight)
        ],
        "strengths": [
            {"claim": e.claim, "category": e.category, "confidence": e.confidence,
             "details": e.details[:3]}
            for e in evidence if e.supports == "strength"
        ],
        "weaknesses": [
            {"claim": e.claim, "category": e.category, "severity": e.severity,
             "confidence": e.confidence, "details": e.details[:3]}
            for e in evidence if e.supports == "weakness"
        ],
        "ownership_analysis": {
            "confidence": evaluation.ownership_confidence,
            "evidence": [
                {"claim": e.claim, "details": e.details[:4]}
                for e in evidence if e.category == "ownership"
            ],
        },
        "ai_analysis": {
            "estimated_assistance": evaluation.ai_likelihood,
            "classification": evaluation.ai_classification,
            "utilization_efficiency": evaluation.ai_utilization,
            "evidence": [
                {"claim": e.claim, "confidence": e.confidence, "details": e.details[:4]}
                for e in evidence if e.category == "ai_utilization"
            ],
            "statement": (
                "AI-assistance figures are probabilistic estimates derived from repository "
                "signals. RepoLens cannot determine that any specific code was AI-generated, and "
                "AI-assisted development is not misconduct."
            ),
        },
        "similarity_analysis": {
            "originality": evaluation.originality,
            "external_matches": [
                {
                    "source": f"{s.source_file}:{s.source_symbol}",
                    "matched": f"{s.matched_repository_name}:{s.matched_file}",
                    "similarity": s.similarity,
                }
                for s in similarity
            ],
        },
        "security": [
            {
                "title": f.title, "severity": f.severity, "file": f.file_path, "line": f.line,
                "confidence": f.confidence, "remediation": f.remediation,
                "value": f.masked_value,
            }
            for f in findings
        ],
        "resume_consistency": evaluation.resume_consistency,
        "recommendations": [
            {"title": r.title, "detail": r.detail, "impact": r.impact, "effort": r.effort,
             "expected_gain": r.expected_gain}
            for r in recommendations
        ],
        "interview_questions": [
            {"category": q.category, "question": q.question, "rationale": q.rationale}
            for q in questions
        ],
        "verification_sessions": [
            {
                "id": s.id, "title": s.title, "status": s.status,
                "verification_score": s.verification_score,
                "dimension_scores": s.dimension_scores, "summary": s.summary,
                "answers": db.query(InterviewAnswer).filter(
                    InterviewAnswer.session_id == s.id
                ).count(),
            }
            for s in sessions
        ],
        "reviewer_notes": [
            {"author": n.author_name, "body": n.body, "created_at": n.created_at.isoformat()}
            for n in notes
        ],
        "human_overrides": [
            {
                "author": o.author_name, "target": f"{o.target_type}:{o.target_key}",
                "original": o.original_value, "new": o.new_value, "rationale": o.rationale,
            }
            for o in overrides
        ],
        "limitations": evaluation.limitations,
        "analyzer_failures": evaluation.failures,
        "reproducibility": evaluation.versions,
        "disclaimer": (
            "This report is decision support, not a decision. RepoLens does not recommend hiring "
            "outcomes. Scores measure evidence visible in the analysed repositories; absence of "
            "evidence is not evidence of absence, and every probabilistic conclusion is reported "
            "with its confidence and limitations."
        ),
    }


@router.get("/{evaluation_id}", response_model=dict)
def get_report(
    evaluation_id: str, user: CurrentUser, db: DbSession, request: Request
) -> dict:
    """Full report as JSON."""
    evaluation = _visible_evaluation(db, user, evaluation_id)
    include_private = user.role in ("INTERVIEWER", "ADMIN")
    report = _build(db, evaluation, include_private)
    audit.record(db, audit.ACTION_REPORT_GENERATED, actor=user, target_type="evaluation",
                 target_id=evaluation.id, organization_id=evaluation.organization_id,
                 detail={"format": "json", "include_private_notes": include_private},
                 request=request)
    db.commit()
    return report


@router.get("/{evaluation_id}/markdown", response_class=PlainTextResponse)
def get_report_markdown(
    evaluation_id: str, user: CurrentUser, db: DbSession, request: Request
) -> str:
    """Downloadable Markdown report."""
    evaluation = _visible_evaluation(db, user, evaluation_id)
    include_private = user.role in ("INTERVIEWER", "ADMIN")
    report = _build(db, evaluation, include_private)
    audit.record(db, audit.ACTION_REPORT_GENERATED, actor=user, target_type="evaluation",
                 target_id=evaluation.id, organization_id=evaluation.organization_id,
                 detail={"format": "markdown"}, request=request)
    db.commit()
    return _render_markdown(report)


def _render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append

    candidate = report["candidate"]["name"] or "Candidate"
    add(f"# RepoLens evaluation — {candidate}")
    add("")
    add(f"_Generated {report['generated_at']}_")
    add("")

    overall = report["overall"]
    add("## Summary")
    add("")
    add(f"- **Overall score:** {_fmt(overall['score'])}/100 "
        f"(confidence {overall['confidence']:.0%})")
    if report["target_job"]["title"]:
        add(f"- **Target role:** {report['target_job']['title']} "
            f"({report['target_job']['experience_level']})")
        add(f"- **Job match:** {_fmt(overall['job_match'])}%")
    add(f"- **Ownership confidence:** {_fmt(overall['ownership_confidence'])}%")
    add(f"- **AI utilization efficiency:** {_fmt(overall['ai_utilization'])}/100")
    add(f"- **Verification status:** {overall['verification_status'].replace('_', ' ').title()}")
    add("")
    if report.get("summary"):
        add(report["summary"])
        add("")
        add(f"_Summary generated by: {report.get('summary_generated_by', 'deterministic')}_")
        add("")

    if overall["verification_reasons"]:
        add("### Verification notes")
        add("")
        for reason in overall["verification_reasons"]:
            add(f"- {reason}")
        add("")

    add("## Scores")
    add("")
    add("| Category | Score | Weight | Confidence |")
    add("| --- | --- | --- | --- |")
    for score in report["scores"]:
        value = f"{score['score']:.0f}" if score["available"] and score["score"] is not None else "n/a"
        add(f"| {score['category'].replace('_', ' ').title()} | {value} | "
            f"{score['weight']:.0%} | {score['confidence']:.0%} |")
        if not score["available"] and score["unavailable_reason"]:
            add(f"| ↳ _unavailable_ | colspan | | {score['unavailable_reason'][:90]} |")
    add("")

    for title, key in (("Technical strengths", "strengths"), ("Weaknesses", "weaknesses")):
        items = report[key]
        add(f"## {title}")
        add("")
        if not items:
            add("_None recorded._")
        for item in items[:10]:
            add(f"- **{item['claim']}** _(confidence {item['confidence']:.0%})_")
            for detail in item.get("details", [])[:2]:
                location = f" — `{detail['file']}`" if detail.get("file") else ""
                add(f"  - {detail.get('detail', '')}{location}")
        add("")

    ai = report["ai_analysis"]
    add("## AI usage analysis")
    add("")
    add(f"- Estimated AI assistance: {_fmt(ai['estimated_assistance'])}/100")
    add(f"- Classification: {ai['classification'] or 'not determined'}")
    add(f"- Utilization efficiency: {_fmt(ai['utilization_efficiency'])}/100")
    add("")
    add(f"> {ai['statement']}")
    add("")

    add("## Ownership analysis")
    add("")
    add(f"Ownership confidence: {_fmt(report['ownership_analysis']['confidence'])}%")
    add("")
    for item in report["ownership_analysis"]["evidence"][:6]:
        add(f"- {item['claim']}")
    add("")

    similarity = report["similarity_analysis"]
    add("## Similarity analysis")
    add("")
    add(f"Originality assessment: {similarity['originality'] or 'not determined'}")
    add("")
    for match in similarity["external_matches"][:6]:
        add(f"- `{match['source']}` ≈ `{match['matched']}` (similarity {match['similarity']:.2f})")
    if not similarity["external_matches"]:
        add("_No cross-repository matches were found in this deployment's corpus._")
    add("")

    add("## Security")
    add("")
    if not report["security"]:
        add("_No findings._")
    for finding in report["security"][:12]:
        add(f"- **{finding['severity'].upper()}** {finding['title']} — "
            f"`{finding['file']}:{finding['line']}`"
            + (f" — value {finding['value']}" if finding.get("value") else ""))
        if finding.get("remediation"):
            add(f"  - {finding['remediation']}")
    add("")

    if report.get("resume_consistency"):
        consistency = report["resume_consistency"]
        add("## Résumé consistency")
        add("")
        add(f"{consistency['supported']} supported, {consistency['partially_supported']} partially "
            f"supported, {consistency['verification_recommended']} recommended for verification.")
        add("")
        for item in consistency["items"][:10]:
            add(f"- **{item['label']}** — {item['status'].replace('_', ' ')}"
                + (f" (claimed: {item['claimed_level']})" if item.get("claimed_level") else ""))
        add("")
        add(f"> {consistency['limitation']}")
        add("")

    add("## Recommended verification questions")
    add("")
    for question in report["interview_questions"][:10]:
        add(f"- _{question['category']}_ — {question['question']}")
    add("")

    if report["verification_sessions"]:
        add("## Technical verification")
        add("")
        for session in report["verification_sessions"]:
            add(f"- {session['title']}: {_fmt(session['verification_score'])}/100 "
                f"({session['answers']} answers, {session['status'].lower()})")
        add("")

    if report["reviewer_notes"]:
        add("## Reviewer notes")
        add("")
        for note in report["reviewer_notes"]:
            add(f"- **{note['author']}** — {note['body']}")
        add("")

    if report["human_overrides"]:
        add("## Human overrides")
        add("")
        for override in report["human_overrides"]:
            add(f"- {override['author']} changed {override['target']}: "
                f"{override['original']} → {override['new']}")
            add(f"  - Rationale: {override['rationale']}")
        add("")

    add("## Limitations")
    add("")
    for limitation in report["limitations"][:15]:
        add(f"- **{limitation.get('scope', 'general')}**: {limitation.get('detail', '')}")
    if report["analyzer_failures"]:
        add("")
        add("### Analyzer failures")
        add("")
        for failure in report["analyzer_failures"]:
            add(f"- `{failure.get('analyzer')}` did not run: {failure.get('reason')}")
            add("  - The affected dimension is reported as unavailable rather than estimated.")
    add("")

    add("## Reproducibility")
    add("")
    for key, value in (report["reproducibility"] or {}).items():
        add(f"- {key}: {value}")
    add("")
    add("---")
    add("")
    add(report["disclaimer"])
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return f"{value:.0f}" if isinstance(value, (int, float)) else "n/a"
