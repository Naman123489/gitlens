"""Candidates: profiles, résumés and voluntary AI disclosure."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, File, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession, require_organization, user_organization_ids
from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.models import Candidate, Evaluation, Repository, User
from app.schemas.common import Message, Page
from app.schemas.evaluation import (
    CandidateCreate,
    CandidateOut,
    DisclosureIn,
    DisclosureOut,
)
from app.services import audit, resume

router = APIRouter(prefix="/candidates", tags=["candidates"])

#: Purposes a disclosure may mention, and the repository signals that would be
#: consistent with them. Used to *contextualise* a disclosure, never to score it.
_PURPOSE_CONTEXT: dict[str, str] = {
    "debugging": "Debugging assistance leaves little trace in a repository.",
    "documentation": "Consistent with uniform documentation across the codebase.",
    "boilerplate": "Consistent with repetitive, structurally similar code.",
    "testing": "Consistent with a test suite that appeared quickly.",
    "architecture": "Architectural assistance is not separable from authorship by static analysis.",
    "core_algorithms": "Core-algorithm assistance is not separable from authorship by static analysis.",
    "learning": "Learning use typically leaves no distinguishing repository signal.",
    "code_review": "Review assistance typically leaves no distinguishing repository signal.",
    "refactoring": "Consistent with refactoring commits in the history.",
}


def _visible_candidate(db: Session, user: User, candidate_id: str) -> Candidate:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise NotFoundError("Candidate not found.")
    if user.role == "ADMIN" or candidate.user_id == user.id:
        return candidate
    if candidate.organization_id and candidate.organization_id in user_organization_ids(db, user):
        return candidate
    raise NotFoundError("Candidate not found.")


def _to_out(db: Session, candidate: Candidate) -> CandidateOut:
    payload = CandidateOut.model_validate(candidate)
    payload.has_resume = bool(candidate.resume_text)
    payload.has_disclosure = bool(candidate.ai_disclosure)
    return payload


@router.post("", response_model=CandidateOut, status_code=status.HTTP_201_CREATED)
def create_candidate(
    payload: CandidateCreate, user: CurrentUser, db: DbSession, request: Request
) -> CandidateOut:
    if user.role == "STUDENT":
        raise ForbiddenError("Students already have a candidate profile created at registration.")
    organization_id = payload.organization_id
    if organization_id:
        require_organization(db, user, organization_id)
    else:
        owned = user_organization_ids(db, user)
        organization_id = owned[0] if owned else None

    candidate = Candidate(
        organization_id=organization_id, full_name=payload.full_name.strip(),
        email=(payload.email or "").lower() or None, github_login=payload.github_login,
        headline=payload.headline,
    )
    db.add(candidate)
    audit.record(db, audit.ACTION_CANDIDATE_CREATED, actor=user, target_type="candidate",
                 target_id=candidate.id, organization_id=organization_id, request=request)
    db.commit()
    db.refresh(candidate)
    return _to_out(db, candidate)


@router.get("", response_model=Page[CandidateOut])
def list_candidates(
    user: CurrentUser, db: DbSession,
    organization_id: str | None = None,
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[CandidateOut]:
    query = db.query(Candidate)
    if user.role == "ADMIN":
        pass
    elif user.role == "INTERVIEWER":
        organization_ids = user_organization_ids(db, user)
        query = query.filter(Candidate.organization_id.in_(organization_ids or ["-"]))
    else:
        query = query.filter(Candidate.user_id == user.id)
    if organization_id:
        query = query.filter(Candidate.organization_id == organization_id)
    if search:
        pattern = f"%{search.lower()}%"
        from sqlalchemy import func, or_

        query = query.filter(or_(
            func.lower(Candidate.full_name).like(pattern),
            func.lower(Candidate.email).like(pattern),
            func.lower(Candidate.github_login).like(pattern),
        ))
    total = query.count()
    rows = query.order_by(Candidate.created_at.desc()).limit(limit).offset(offset).all()
    return Page(items=[_to_out(db, c) for c in rows], total=total, limit=limit, offset=offset)


@router.get("/{candidate_id}", response_model=dict)
def get_candidate(
    candidate_id: str, user: CurrentUser, db: DbSession, request: Request
) -> dict:
    """Candidate profile with repositories and evaluations.

    Every read is audited: candidate data access is a consequential action.
    """
    candidate = _visible_candidate(db, user, candidate_id)
    repositories = db.query(Repository).filter(Repository.candidate_id == candidate.id).all()
    evaluations = (
        db.query(Evaluation)
        .filter(Evaluation.candidate_id == candidate.id)
        .order_by(Evaluation.created_at.desc())
        .limit(50).all()
    )
    audit.record(db, audit.ACTION_CANDIDATE_VIEWED, actor=user, target_type="candidate",
                 target_id=candidate.id, organization_id=candidate.organization_id, request=request)
    db.commit()

    best = max(
        (e for e in evaluations if e.overall_score is not None),
        key=lambda e: e.overall_score, default=None,
    )
    return {
        "candidate": _to_out(db, candidate).model_dump(),
        "repositories": [
            {
                "id": r.id, "full_name": r.full_name, "name": r.name,
                "description": r.description, "primary_language": r.primary_language,
                "stars": r.stars, "analysis_status": r.analysis_status,
                "last_analyzed_at": r.last_analyzed_at,
            }
            for r in repositories
        ],
        "evaluations": [
            {
                "id": e.id, "repository_id": e.repository_id, "job_id": e.job_id,
                "overall_score": e.overall_score, "job_match": e.job_match,
                "ownership_confidence": e.ownership_confidence,
                "ai_likelihood": e.ai_likelihood, "ai_utilization": e.ai_utilization,
                "ai_classification": e.ai_classification,
                "verification_status": e.verification_status, "created_at": e.created_at,
            }
            for e in evaluations
        ],
        "summary": {
            "repositories": len(repositories),
            "evaluations": len(evaluations),
            "best_overall_score": best.overall_score if best else None,
            "engineering_dna": best.engineering_dna if best else {},
            "needs_verification": sum(
                1 for e in evaluations if e.verification_status == "VERIFICATION_REQUIRED"
            ),
        },
    }


@router.post("/{candidate_id}/resume", response_model=dict)
async def upload_resume(
    candidate_id: str, user: CurrentUser, db: DbSession, request: Request,
    file: UploadFile = File(...),
) -> dict:
    """Upload a résumé (PDF, Markdown or plain text) and extract claimed skills."""
    settings = get_settings()
    candidate = _visible_candidate(db, user, candidate_id)
    if user.role == "STUDENT" and candidate.user_id != user.id:
        raise ForbiddenError("You can only upload a résumé to your own profile.")

    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise ValidationError(
            f"The file is larger than the {settings.max_upload_bytes // (1024 * 1024)} MB limit."
        )
    if not data:
        raise ValidationError("The uploaded file is empty.")

    filename = (file.filename or "resume").strip()[:300]
    if filename.lower().endswith(".pdf"):
        text = resume.extract_pdf_text(data)
        if not text.strip():
            raise ValidationError(
                "No text could be extracted from this PDF. It may be a scanned image; upload a "
                "text-based PDF, Markdown or plain text instead."
            )
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValidationError("The file is not UTF-8 text. Upload a PDF, Markdown or text file.")

    parsed = resume.parse_resume(text)
    candidate.resume_text = text[:200_000]
    candidate.resume_filename = filename
    candidate.resume_parsed = parsed.to_dict()
    db.add(candidate)
    audit.record(db, "candidate.resume_uploaded", actor=user, target_type="candidate",
                 target_id=candidate.id, organization_id=candidate.organization_id,
                 detail={"filename": filename, "skills_found": len(parsed.skills)}, request=request)
    db.commit()
    return {
        "filename": filename,
        "word_count": parsed.word_count,
        "skills": parsed.skills,
        "projects": parsed.projects[:10],
        "sections": parsed.sections,
        "note": "Claimed skills are compared with repository evidence when an evaluation runs.",
    }


@router.get("/{candidate_id}/disclosure", response_model=DisclosureOut)
def get_disclosure(candidate_id: str, user: CurrentUser, db: DbSession) -> DisclosureOut:
    candidate = _visible_candidate(db, user, candidate_id)
    disclosure = candidate.ai_disclosure or {}
    comparison = None
    if disclosure:
        latest = (
            db.query(Evaluation)
            .filter(Evaluation.candidate_id == candidate.id, Evaluation.ai_likelihood.isnot(None))
            .order_by(Evaluation.created_at.desc())
            .first()
        )
        if latest is not None:
            comparison = _compare_disclosure(disclosure, latest)
    return DisclosureOut(
        used_ai=disclosure.get("used_ai"),
        purposes=disclosure.get("purposes", []),
        tools=disclosure.get("tools", []),
        notes=disclosure.get("notes", ""),
        updated_at=(
            datetime.fromisoformat(disclosure["updated_at"]) if disclosure.get("updated_at") else None
        ),
        comparison=comparison,
    )


@router.put("/{candidate_id}/disclosure", response_model=DisclosureOut)
def set_disclosure(
    candidate_id: str, payload: DisclosureIn, user: CurrentUser, db: DbSession, request: Request
) -> DisclosureOut:
    """Record a candidate's voluntary AI-usage disclosure.

    Only the candidate can write their own disclosure: an interviewer filling
    this in on someone's behalf would make it worthless as a statement.
    """
    candidate = _visible_candidate(db, user, candidate_id)
    if candidate.user_id != user.id and user.role != "ADMIN":
        raise ForbiddenError(
            "A disclosure can only be recorded by the candidate it belongs to."
        )
    candidate.ai_disclosure = {
        "used_ai": payload.used_ai,
        "purposes": payload.purposes,
        "tools": [t[:60] for t in payload.tools],
        "notes": payload.notes,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    db.add(candidate)
    audit.record(db, audit.ACTION_DISCLOSURE_UPDATED, actor=user, target_type="candidate",
                 target_id=candidate.id, detail={"used_ai": payload.used_ai}, request=request)
    db.commit()
    return get_disclosure(candidate_id, user, db)


def _compare_disclosure(disclosure: dict, evaluation: Evaluation) -> dict:
    """Compare a declared disclosure with inferred signals.

    Explicitly *not* a lie detector: the two are different kinds of statement and
    disagreement has many innocent explanations.
    """
    likelihood = evaluation.ai_likelihood or 0.0
    declared = bool(disclosure.get("used_ai"))
    purposes = list(disclosure.get("purposes") or [])

    if declared and likelihood >= 45:
        alignment = "consistent"
        detail = ("The declared usage is consistent with the repository signals.")
    elif declared and likelihood < 45:
        alignment = "declared_more_than_observed"
        detail = ("The candidate declared AI use that the repository signals do not strongly show. "
                  "Assistance used for debugging, learning or review leaves little trace in code.")
    elif not declared and likelihood >= 65:
        alignment = "signals_above_declaration"
        detail = ("Repository signals are stronger than the disclosure suggests. These signals have "
                  "legitimate non-AI explanations and this is not evidence of a false statement; it "
                  "is a good topic for a conversation.")
    else:
        alignment = "consistent"
        detail = "The disclosure and the repository signals do not conflict."

    return {
        "declared_usage": declared,
        "declared_purposes": purposes,
        "estimated_ai_assistance": likelihood,
        "ai_classification": evaluation.ai_classification,
        "alignment": alignment,
        "detail": detail,
        "purpose_context": {p: _PURPOSE_CONTEXT.get(p, "") for p in purposes},
        "limitation": (
            "A disclosure is a statement of intent; the estimate is a probabilistic reading of "
            "artefacts. Disagreement between them is not evidence of dishonesty."
        ),
    }
