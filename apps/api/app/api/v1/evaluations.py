"""Evaluations: scoring, evidence, reviewer notes, overrides and comparison."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, DbSession, user_organization_ids
from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.models import (
    Candidate,
    Evaluation,
    EvaluationScore,
    EvidenceRecord,
    HumanOverride,
    InterviewSession,
    Job,
    Recommendation,
    Repository,
    RepositoryAnalysis,
    ReviewerNote,
    User,
)
from app.schemas.common import EvidenceOut, Message, Page
from app.schemas.evaluation import (
    CompareRequest,
    EvaluateRequest,
    EvaluationOut,
    EvaluationSummaryOut,
    OverrideIn,
    OverrideOut,
    ReviewerNoteIn,
    ReviewerNoteOut,
)
from app.services import audit, policies
from app.services.evaluation_service import create_evaluation

router = APIRouter(tags=["evaluations"])


def _visible_evaluation(db: Session, user: User, evaluation_id: str) -> Evaluation:
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise NotFoundError("Evaluation not found.")
    if user.role == "ADMIN" or evaluation.user_id == user.id:
        return evaluation
    if evaluation.organization_id and evaluation.organization_id in user_organization_ids(db, user):
        return evaluation
    if evaluation.candidate_id:
        candidate = db.get(Candidate, evaluation.candidate_id)
        if candidate and candidate.user_id == user.id:
            return evaluation
    raise NotFoundError("Evaluation not found.")


def _require_interviewer(user: User) -> None:
    if user.role not in ("INTERVIEWER", "ADMIN"):
        raise ForbiddenError("This action is available to interviewers.")


@router.post("/evaluations", response_model=EvaluationOut, status_code=status.HTTP_201_CREATED)
def create(
    payload: EvaluateRequest, user: CurrentUser, db: DbSession, request: Request
) -> EvaluationOut:
    """Score an analysed repository against a job under a policy version."""
    repository = db.get(Repository, payload.repository_id)
    if repository is None:
        raise NotFoundError("Repository not found.")
    if user.role == "STUDENT" and repository.owner_user_id != user.id:
        raise ForbiddenError("You can only evaluate your own repositories.")

    analysis = (
        db.query(RepositoryAnalysis)
        .filter(RepositoryAnalysis.repository_id == repository.id)
        .order_by(RepositoryAnalysis.created_at.desc())
        .first()
    )
    if analysis is None:
        raise ValidationError(
            "This repository has not been analysed yet. Run an analysis before evaluating it.",
            {"repository_id": repository.id},
        )

    job: Job | None = None
    if payload.job_id:
        job = db.get(Job, payload.job_id)
        if job is None:
            raise NotFoundError("Job not found.")

    candidate: Candidate | None = None
    candidate_id = payload.candidate_id or repository.candidate_id
    if candidate_id:
        candidate = db.get(Candidate, candidate_id)

    organization_id = payload.organization_id or (job.organization_id if job else None) or (
        candidate.organization_id if candidate else None
    )

    policy, policy_id = policies.resolve_policy(
        db, payload.policy_id or (job.policy_id if job else None), organization_id
    )

    verification_score = None
    if candidate is not None:
        session = (
            db.query(InterviewSession)
            .filter(
                InterviewSession.candidate_id == candidate.id,
                InterviewSession.repository_id == repository.id,
                InterviewSession.verification_score.isnot(None),
            )
            .order_by(InterviewSession.created_at.desc())
            .first()
        )
        verification_score = session.verification_score if session else None

    evaluation = create_evaluation(
        db=db, repository=repository, analysis=analysis, policy=policy, policy_id=policy_id,
        job=job, candidate=candidate, user=user, organization_id=organization_id,
        verification_score=verification_score,
    )
    audit.record(
        db, audit.ACTION_EVALUATION_CREATED, actor=user, target_type="evaluation",
        target_id=evaluation.id, organization_id=organization_id,
        detail={
            "repository": repository.full_name, "job_id": payload.job_id,
            "policy": f"{policy.name} v{policy.version}",
            "overall_score": evaluation.overall_score,
            "verification_status": evaluation.verification_status,
            "versions": evaluation.versions,
        },
        request=request,
    )
    db.commit()
    db.refresh(evaluation)
    return _detail(db, evaluation)


def _detail(db: Session, evaluation: Evaluation) -> EvaluationOut:
    repository = db.get(Repository, evaluation.repository_id)
    job = db.get(Job, evaluation.job_id) if evaluation.job_id else None
    candidate = db.get(Candidate, evaluation.candidate_id) if evaluation.candidate_id else None
    scores = db.query(EvaluationScore).filter(
        EvaluationScore.evaluation_id == evaluation.id
    ).all()
    recommendations = db.query(Recommendation).filter(
        Recommendation.evaluation_id == evaluation.id
    ).all()
    policy_record = policies.get_policy_record(db, evaluation.policy_id) if evaluation.policy_id else None

    # Built from an explicit dict rather than straight from the ORM object:
    # `Evaluation.scores` is a relationship of ORM rows, and validating it
    # against the response schema's `list[dict]` would fail.
    payload = EvaluationOut(
        **EvaluationSummaryOut.model_validate(evaluation).model_dump(),
        verification_reasons=evaluation.verification_reasons or [],
        limitations=evaluation.limitations or [],
        failures=evaluation.failures or [],
        skill_matches=evaluation.skill_matches or [],
        engineering_dna=evaluation.engineering_dna or {},
        resume_consistency=evaluation.resume_consistency,
        narrative=evaluation.narrative,
        versions=evaluation.versions or {},
    )
    payload.scores = [
        {
            "category": s.category, "score": s.score, "confidence": s.confidence,
            "weight": s.weight, "available": s.available,
            "unavailable_reason": s.unavailable_reason, "evidence_ids": s.evidence_ids,
            "sub_scores": s.sub_scores,
        }
        for s in sorted(scores, key=lambda x: -x.weight)
    ]
    payload.repository = {
        "id": repository.id, "full_name": repository.full_name, "name": repository.name,
        "description": repository.description, "html_url": repository.html_url,
        "primary_language": repository.primary_language, "stars": repository.stars,
        "languages": repository.languages,
    } if repository else None
    payload.job = {
        "id": job.id, "title": job.title, "experience_level": job.experience_level,
        "domain": job.domain,
        "requirements": [
            {"skill": r.skill, "label": r.label, "required": r.required, "importance": r.importance}
            for r in job.requirements
        ],
    } if job else None
    payload.candidate = {
        "id": candidate.id, "full_name": candidate.full_name,
        "github_login": candidate.github_login, "headline": candidate.headline,
    } if candidate else None
    payload.policy = (
        {"id": policy_record.id, "name": policy_record.name, "version": policy_record.version,
         "weights": policy_record.weights}
        if policy_record else {"name": "RepoLens default", "version": 1}
    )
    payload.recommendations = [
        {
            "category": r.category, "title": r.title, "detail": r.detail, "impact": r.impact,
            "effort": r.effort, "expected_gain": r.expected_gain, "evidence_ids": r.evidence_ids,
        }
        for r in recommendations
    ]
    return payload


@router.get("/evaluations", response_model=Page[EvaluationSummaryOut])
def list_evaluations(
    user: CurrentUser, db: DbSession,
    job_id: str | None = None,
    candidate_id: str | None = None,
    repository_id: str | None = None,
    verification_status: str | None = None,
    min_score: float | None = Query(default=None, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[EvaluationSummaryOut]:
    query = db.query(Evaluation)
    if user.role != "ADMIN":
        organization_ids = user_organization_ids(db, user)
        from sqlalchemy import or_

        conditions = [Evaluation.user_id == user.id]
        if organization_ids:
            conditions.append(Evaluation.organization_id.in_(organization_ids))
        own_candidate = db.query(Candidate).filter(Candidate.user_id == user.id).first()
        if own_candidate is not None:
            conditions.append(Evaluation.candidate_id == own_candidate.id)
        query = query.filter(or_(*conditions))

    if job_id:
        query = query.filter(Evaluation.job_id == job_id)
    if candidate_id:
        query = query.filter(Evaluation.candidate_id == candidate_id)
    if repository_id:
        query = query.filter(Evaluation.repository_id == repository_id)
    if verification_status:
        query = query.filter(Evaluation.verification_status == verification_status)
    if min_score is not None:
        query = query.filter(Evaluation.overall_score >= min_score)

    total = query.count()
    rows = (
        query.order_by(Evaluation.overall_score.desc().nullslast(), Evaluation.created_at.desc())
        .limit(limit).offset(offset).all()
    )
    return Page(items=[EvaluationSummaryOut.model_validate(e) for e in rows],
                total=total, limit=limit, offset=offset)


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationOut)
def get_evaluation(
    evaluation_id: str, user: CurrentUser, db: DbSession, request: Request
) -> EvaluationOut:
    evaluation = _visible_evaluation(db, user, evaluation_id)
    audit.record(db, audit.ACTION_EVALUATION_VIEWED, actor=user, target_type="evaluation",
                 target_id=evaluation.id, organization_id=evaluation.organization_id,
                 request=request)
    db.commit()
    return _detail(db, evaluation)


@router.get("/evaluations/{evaluation_id}/evidence", response_model=list[EvidenceOut])
def get_evidence(
    evaluation_id: str, user: CurrentUser, db: DbSession,
    category: str | None = None, supports: str | None = None,
) -> list[EvidenceOut]:
    evaluation = _visible_evaluation(db, user, evaluation_id)
    query = db.query(EvidenceRecord).filter(EvidenceRecord.evaluation_id == evaluation.id)
    if category:
        query = query.filter(EvidenceRecord.category == category)
    if supports:
        query = query.filter(EvidenceRecord.supports == supports)
    return [
        EvidenceOut.model_validate(row)
        for row in query.order_by(EvidenceRecord.confidence.desc()).all()
    ]


@router.get("/evaluations/{evaluation_id}/notes", response_model=list[ReviewerNoteOut])
def list_notes(evaluation_id: str, user: CurrentUser, db: DbSession) -> list[ReviewerNoteOut]:
    evaluation = _visible_evaluation(db, user, evaluation_id)
    query = db.query(ReviewerNote).filter(ReviewerNote.evaluation_id == evaluation.id)
    if user.role == "STUDENT":
        # Reviewer notes are interviewer-only unless explicitly shared.
        query = query.filter(ReviewerNote.visible_to_candidate.is_(True))
    return [
        ReviewerNoteOut.model_validate(n)
        for n in query.order_by(ReviewerNote.created_at.desc()).all()
    ]


@router.post("/evaluations/{evaluation_id}/notes", response_model=ReviewerNoteOut,
             status_code=status.HTTP_201_CREATED)
def add_note(
    evaluation_id: str, payload: ReviewerNoteIn, user: CurrentUser, db: DbSession, request: Request
) -> ReviewerNoteOut:
    _require_interviewer(user)
    evaluation = _visible_evaluation(db, user, evaluation_id)
    note = ReviewerNote(
        evaluation_id=evaluation.id, author_id=user.id, author_name=user.full_name,
        body=payload.body, category=payload.category,
        visible_to_candidate=payload.visible_to_candidate,
    )
    db.add(note)
    audit.record(db, audit.ACTION_NOTE_CREATED, actor=user, target_type="evaluation",
                 target_id=evaluation.id, organization_id=evaluation.organization_id,
                 detail={"visible_to_candidate": payload.visible_to_candidate}, request=request)
    db.commit()
    db.refresh(note)
    return ReviewerNoteOut.model_validate(note)


@router.post("/evaluations/{evaluation_id}/overrides", response_model=OverrideOut,
             status_code=status.HTTP_201_CREATED)
def add_override(
    evaluation_id: str, payload: OverrideIn, user: CurrentUser, db: DbSession, request: Request
) -> OverrideOut:
    """Record a reviewer's correction.

    The original machine value is preserved alongside the new one: an override is
    an annotation on the record, never a rewrite of it.
    """
    _require_interviewer(user)
    evaluation = _visible_evaluation(db, user, evaluation_id)

    original: dict[str, Any] = {}
    if payload.target_type == "score":
        score = (
            db.query(EvaluationScore)
            .filter(
                EvaluationScore.evaluation_id == evaluation.id,
                EvaluationScore.category == payload.target_key,
            )
            .first()
        )
        if score is None:
            raise NotFoundError(f"No '{payload.target_key}' score on this evaluation.")
        original = {"score": score.score, "confidence": score.confidence}
        new_score = payload.new_value.get("score")
        if not isinstance(new_score, (int, float)) or not 0 <= float(new_score) <= 100:
            raise ValidationError("new_value.score must be a number between 0 and 100.")
        score.score = float(new_score)
        db.add(score)
    elif payload.target_type == "verification_status":
        original = {"verification_status": evaluation.verification_status}
        new_status = str(payload.new_value.get("verification_status", ""))
        allowed = {"CLEAR", "REVIEW_RECOMMENDED", "VERIFICATION_REQUIRED", "ANALYSIS_INCOMPLETE"}
        if new_status not in allowed:
            raise ValidationError(
                f"verification_status must be one of {sorted(allowed)}.",
                {"note": "RepoLens has no rejection status by design; the hiring decision is yours "
                         "to record outside the system."},
            )
        evaluation.verification_status = new_status
        db.add(evaluation)
    else:
        record = (
            db.query(EvidenceRecord)
            .filter(
                EvidenceRecord.evaluation_id == evaluation.id,
                EvidenceRecord.evidence_id == payload.target_key,
            )
            .first()
        )
        if record is None:
            raise NotFoundError("Evidence item not found on this evaluation.")
        original = {"claim": record.claim, "confidence": record.confidence,
                    "supports": record.supports}

    override = HumanOverride(
        evaluation_id=evaluation.id, author_id=user.id, author_name=user.full_name,
        target_type=payload.target_type, target_key=payload.target_key,
        original_value=original, new_value=payload.new_value, rationale=payload.rationale,
    )
    db.add(override)
    audit.record(db, audit.ACTION_OVERRIDE_CREATED, actor=user, target_type="evaluation",
                 target_id=evaluation.id, organization_id=evaluation.organization_id,
                 detail={"target_type": payload.target_type, "target_key": payload.target_key,
                         "original": original, "new": payload.new_value},
                 request=request)
    db.commit()
    db.refresh(override)
    return OverrideOut.model_validate(override)


@router.get("/evaluations/{evaluation_id}/overrides", response_model=list[OverrideOut])
def list_overrides(evaluation_id: str, user: CurrentUser, db: DbSession) -> list[OverrideOut]:
    evaluation = _visible_evaluation(db, user, evaluation_id)
    rows = (
        db.query(HumanOverride)
        .filter(HumanOverride.evaluation_id == evaluation.id)
        .order_by(HumanOverride.created_at.desc()).all()
    )
    return [OverrideOut.model_validate(r) for r in rows]


@router.post("/evaluations/compare", response_model=dict)
def compare(payload: CompareRequest, user: CurrentUser, db: DbSession) -> dict:
    """Side-by-side comparison of evaluations, with the evidence behind each score."""
    evaluations = [_visible_evaluation(db, user, eid) for eid in payload.evaluation_ids]
    categories: list[str] = []
    rows: dict[str, dict[str, Any]] = {}

    for evaluation in evaluations:
        scores = db.query(EvaluationScore).filter(
            EvaluationScore.evaluation_id == evaluation.id
        ).all()
        for score in scores:
            if score.category not in rows:
                rows[score.category] = {}
                categories.append(score.category)
            rows[score.category][evaluation.id] = {
                "score": score.score, "available": score.available,
                "confidence": score.confidence,
                "unavailable_reason": score.unavailable_reason,
            }

    return {
        "evaluations": [
            {
                "id": e.id,
                "candidate": (db.get(Candidate, e.candidate_id).full_name
                              if e.candidate_id and db.get(Candidate, e.candidate_id) else None),
                "repository": (db.get(Repository, e.repository_id).full_name
                               if db.get(Repository, e.repository_id) else None),
                "overall_score": e.overall_score, "job_match": e.job_match,
                "ownership_confidence": e.ownership_confidence,
                "ai_likelihood": e.ai_likelihood, "ai_utilization": e.ai_utilization,
                "verification_status": e.verification_status,
                "policy": e.versions.get("policy_version"),
            }
            for e in evaluations
        ],
        "categories": [
            {"category": category, "values": rows[category]} for category in categories
        ],
        "note": (
            "Scores are only comparable when the evaluations used the same policy version. "
            "Check the policy column before ranking."
        ),
    }


@router.delete("/evaluations/{evaluation_id}", response_model=Message)
def delete_evaluation(
    evaluation_id: str, user: CurrentUser, db: DbSession, request: Request
) -> Message:
    evaluation = _visible_evaluation(db, user, evaluation_id)
    if evaluation.user_id != user.id:
        _require_interviewer(user)
    db.delete(evaluation)
    audit.record(db, "evaluation.deleted", actor=user, target_type="evaluation",
                 target_id=evaluation_id, request=request)
    db.commit()
    return Message(message="Evaluation deleted.")
