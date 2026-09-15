"""Job descriptions: creation, parsing and requirement management."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from repolens_scoring import SKILLS_BY_KEY, parse_job_description

from app.core.deps import CurrentUser, DbSession, require_organization, user_organization_ids
from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.models import Job, JobRequirement, User
from app.schemas.common import Message, Page
from app.schemas.evaluation import (
    JobCreate,
    JobOut,
    JobParsePreview,
    JobUpdate,
)
from app.services import audit

router = APIRouter(prefix="/jobs", tags=["jobs"])


class ParseRequest(BaseModel):
    title: str = Field(default="", max_length=300)
    description: str = Field(min_length=10, max_length=40000)


def _writable_job(db: Session, user: User, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found.")
    if user.role == "ADMIN":
        return job
    if job.organization_id and job.organization_id in user_organization_ids(db, user):
        return job
    if job.created_by_id == user.id:
        return job
    raise NotFoundError("Job not found.")


def _apply_parse(db: Session, job: Job, title: str, description: str,
                 overrides: list | None = None) -> None:
    """Parse a description into requirements, then apply any manual overrides."""
    parsed = parse_job_description(description, title=title)
    job.experience_level = parsed.experience_level
    job.min_years_experience = parsed.min_years_experience
    job.domain = parsed.domain
    job.responsibilities = parsed.responsibilities
    job.parse_notes = parsed.notes

    db.query(JobRequirement).filter(JobRequirement.job_id == job.id).delete()
    by_skill = {r.skill: r for r in parsed.requirements}

    for override in overrides or []:
        if override.skill not in SKILLS_BY_KEY:
            raise ValidationError(
                f"Unknown skill '{override.skill}'. Use a key from the RepoLens taxonomy.",
                {"known_skills": sorted(SKILLS_BY_KEY)[:60]},
            )
        skill = SKILLS_BY_KEY[override.skill]
        existing = by_skill.get(override.skill)
        if existing is not None:
            existing.required = override.required
            if override.importance is not None:
                existing.importance = override.importance
            existing.source = "manual"
        else:
            from repolens_scoring.jd_parser import ParsedRequirement

            by_skill[override.skill] = ParsedRequirement(
                skill=skill.key, label=skill.label, dimension=str(skill.dimension),
                required=override.required, importance=override.importance or 0.1,
                matched_terms=[], source="manual",
            )

    requirements = list(by_skill.values())
    total = sum(r.importance for r in requirements) or 1.0
    for requirement in requirements:
        db.add(JobRequirement(
            job_id=job.id, skill=requirement.skill, label=requirement.label,
            dimension=requirement.dimension, required=requirement.required,
            importance=round(requirement.importance / total, 4), source=requirement.source,
            matched_terms=requirement.matched_terms,
        ))


@router.post("/parse", response_model=JobParsePreview)
def parse_preview(payload: ParseRequest, user: CurrentUser) -> JobParsePreview:
    """Parse a description without saving, so the UI can show what was extracted."""
    parsed = parse_job_description(payload.description, title=payload.title)
    return JobParsePreview(
        requirements=[r.to_dict() for r in parsed.requirements],
        responsibilities=parsed.responsibilities,
        experience_level=parsed.experience_level,
        min_years_experience=parsed.min_years_experience,
        domain=parsed.domain,
        technologies=parsed.technologies,
        notes=parsed.notes,
    )


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreate, user: CurrentUser, db: DbSession, request: Request
) -> JobOut:
    if user.role == "STUDENT":
        raise ForbiddenError("Only interviewers can create jobs.")
    organization_id = payload.organization_id
    if organization_id:
        require_organization(db, user, organization_id)
    else:
        owned = user_organization_ids(db, user)
        organization_id = owned[0] if owned else None

    job = Job(
        organization_id=organization_id, created_by_id=user.id, title=payload.title.strip(),
        description=payload.description, location=payload.location,
        policy_id=payload.policy_id, is_public=payload.is_public,
    )
    db.add(job)
    db.flush()
    _apply_parse(db, job, payload.title, payload.description, payload.requirements)
    audit.record(db, audit.ACTION_JOB_CREATED, actor=user, target_type="job", target_id=job.id,
                 organization_id=organization_id, detail={"title": job.title}, request=request)
    db.commit()
    db.refresh(job)
    return JobOut.model_validate(job)


@router.get("", response_model=Page[JobOut])
def list_jobs(
    user: CurrentUser, db: DbSession,
    include_public: bool = True,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[JobOut]:
    """List jobs the caller can see.

    Students see public jobs (so they can check readiness against real roles)
    plus any job in an organization they belong to.
    """
    organization_ids = user_organization_ids(db, user)
    query = db.query(Job)
    if user.role != "ADMIN":
        conditions = [Job.created_by_id == user.id]
        if organization_ids:
            conditions.append(Job.organization_id.in_(organization_ids))
        if include_public:
            conditions.append(Job.is_public.is_(True))
        from sqlalchemy import or_

        query = query.filter(or_(*conditions))
    total = query.count()
    rows = query.order_by(Job.created_at.desc()).limit(limit).offset(offset).all()
    return Page(items=[JobOut.model_validate(j) for j in rows], total=total,
                limit=limit, offset=offset)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, user: CurrentUser, db: DbSession) -> JobOut:
    job = db.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found.")
    if not job.is_public and user.role != "ADMIN":
        if job.created_by_id != user.id and job.organization_id not in user_organization_ids(db, user):
            raise NotFoundError("Job not found.")
    return JobOut.model_validate(job)


@router.patch("/{job_id}", response_model=JobOut)
def update_job(
    job_id: str, payload: JobUpdate, user: CurrentUser, db: DbSession, request: Request
) -> JobOut:
    job = _writable_job(db, user, job_id)
    if payload.title is not None:
        job.title = payload.title.strip()
    if payload.description is not None:
        job.description = payload.description
    if payload.location is not None:
        job.location = payload.location
    if payload.is_open is not None:
        job.is_open = payload.is_open
    if payload.is_public is not None:
        job.is_public = payload.is_public
    if payload.policy_id is not None:
        job.policy_id = payload.policy_id
    db.add(job)

    if payload.reparse or payload.description is not None or payload.requirements is not None:
        _apply_parse(db, job, job.title, job.description, payload.requirements)

    audit.record(db, "job.updated", actor=user, target_type="job", target_id=job.id,
                 organization_id=job.organization_id, request=request)
    db.commit()
    db.refresh(job)
    return JobOut.model_validate(job)


@router.delete("/{job_id}", response_model=Message)
def delete_job(job_id: str, user: CurrentUser, db: DbSession, request: Request) -> Message:
    job = _writable_job(db, user, job_id)
    title = job.title
    db.delete(job)
    audit.record(db, "job.deleted", actor=user, target_type="job", target_id=job_id,
                 detail={"title": title}, request=request)
    db.commit()
    return Message(message=f"Deleted job '{title}'. Existing evaluations are retained.")


@router.get("/taxonomy/skills", response_model=list[dict])
def list_skills(user: CurrentUser) -> list[dict]:
    """The skill taxonomy, so the UI can offer real options when editing requirements."""
    return [
        {
            "key": skill.key, "label": skill.label, "dimension": str(skill.dimension),
            "aliases": list(skill.aliases),
            "evidence_sources": [
                name for name, values in (
                    ("dependencies", skill.dependencies), ("imports", skill.imports),
                    ("languages", skill.languages), ("paths", skill.path_patterns),
                ) if values
            ],
        }
        for skill in sorted(SKILLS_BY_KEY.values(), key=lambda s: (str(s.dimension), s.label))
    ]
