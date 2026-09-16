"""Administration: health, audit log, job monitoring and analyzer configuration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import func

from repolens_analysis import DEFAULT_LIMITS
from repolens_analysis.languages import AST_SUPPORTED
from repolens_security import PATTERN_RULES, PROVIDER_RULES
from repolens_shared.versioning import ANALYZER_VERSION, PROMPT_VERSION, SCORING_ENGINE_VERSION
from repolens_similarity import TUTORIAL_SIGNALS

from app.core.config import get_settings
from app.core.deps import DbSession, RequireAdmin
from app.core.errors import NotFoundError
from app.models import (
    AnalysisJob,
    AnalyzerFailureRecord,
    AuditLog,
    Candidate,
    Evaluation,
    Organization,
    Repository,
    RepositoryAnalysis,
    User,
)
from app.schemas.common import Message, Page
from app.services import llm, vectors
from app.services.queue import backend_status
from app.services.ratelimit_dep import get_limiter

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/health", response_model=dict)
def health(user: RequireAdmin, db: DbSession) -> dict:
    """Operational health: dependencies, throughput, failures and configuration."""
    settings = get_settings()
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    try:
        db.query(func.count(User.id)).scalar()
        database_ok = True
        database_error = None
    except Exception as exc:  # noqa: BLE001 - reporting a dependency outage
        database_ok = False
        database_error = str(exc)[:200]

    recent_jobs = db.query(AnalysisJob).filter(AnalysisJob.created_at >= since).all()
    durations = [j.duration_seconds for j in recent_jobs if j.duration_seconds]
    failures = (
        db.query(AnalyzerFailureRecord.analyzer, func.count(AnalyzerFailureRecord.id))
        .filter(AnalyzerFailureRecord.created_at >= since)
        .group_by(AnalyzerFailureRecord.analyzer).all()
    )

    return {
        "status": "ok" if database_ok else "degraded",
        "environment": settings.environment,
        "configuration_problems": settings.validate_for_runtime(),
        "dependencies": {
            "database": {"ok": database_ok, "error": database_error},
            "queue": backend_status(),
            "rate_limiter": {"backend": get_limiter().backend},
            "vector_store": {"backend": vectors.backend_name()},
            "github_oauth": {"configured": settings.github_oauth_configured},
            "llm": {
                "configured": llm.is_available(),
                "model": settings.llm_model if llm.is_available() else None,
                "note": None if llm.is_available() else
                        "No LLM is configured. Narratives and answer assessments use deterministic "
                        "templates; all scoring is unaffected because scores are never model-derived.",
            },
        },
        "versions": {
            "analyzer": ANALYZER_VERSION,
            "scoring_engine": SCORING_ENGINE_VERSION,
            "prompt": PROMPT_VERSION,
        },
        "activity_24h": {
            "analysis_jobs": len(recent_jobs),
            "completed": sum(1 for j in recent_jobs if j.status == "COMPLETED"),
            "failed": sum(1 for j in recent_jobs if j.status == "FAILED"),
            "running": sum(1 for j in recent_jobs if j.status == "RUNNING"),
            "avg_duration_seconds": round(sum(durations) / len(durations), 2) if durations else None,
            "max_duration_seconds": round(max(durations), 2) if durations else None,
            "analyzer_failures": {name: count for name, count in failures},
        },
        "totals": {
            "users": db.query(func.count(User.id)).scalar(),
            "organizations": db.query(func.count(Organization.id)).scalar(),
            "candidates": db.query(func.count(Candidate.id)).scalar(),
            "repositories": db.query(func.count(Repository.id)).scalar(),
            "analyses": db.query(func.count(RepositoryAnalysis.id)).scalar(),
            "evaluations": db.query(func.count(Evaluation.id)).scalar(),
        },
    }


@router.get("/analyzers", response_model=dict)
def analyzer_configuration(user: RequireAdmin) -> dict:
    """What the analysis engine is currently configured to do."""
    settings = get_settings()
    return {
        "analyzer_version": ANALYZER_VERSION,
        "ast_languages": sorted(AST_SUPPORTED),
        "security_rules": {
            "secret_patterns": len(PROVIDER_RULES) + 1,
            "code_patterns": len(PATTERN_RULES),
            "rules": [
                {"id": r.id, "title": r.title, "category": r.category,
                 "severity": str(r.severity), "confidence": r.confidence, "cwe": r.cwe}
                for r in PATTERN_RULES
            ],
        },
        "tutorial_signals": [
            {"id": s.id, "label": s.label, "weight": s.weight, "note": s.note}
            for s in TUTORIAL_SIGNALS
        ],
        "limits": {
            "max_repository_mb": settings.max_repository_mb,
            "max_files": settings.max_files_per_repository,
            "max_file_kb": settings.max_file_kb,
            "max_ast_file_bytes": DEFAULT_LIMITS.max_ast_file_bytes,
            "analysis_timeout_seconds": settings.analysis_timeout_seconds,
            "clone_timeout_seconds": settings.clone_timeout_seconds,
            "rate_limit_per_minute": settings.rate_limit_per_minute,
            "rate_limit_analysis_per_hour": settings.rate_limit_analysis_per_hour,
        },
        "embedding": {
            "dimensions": settings.embedding_dimensions,
            "backend": vectors.backend_name(),
            "kind": "lexical (feature hashing)" if not settings.llm_configured else
                    "lexical (feature hashing); configure an embedding provider for neural vectors",
        },
    }


@router.get("/audit-logs", response_model=Page[dict])
def audit_logs(
    user: RequireAdmin, db: DbSession,
    action: str | None = None,
    actor_id: str | None = None,
    target_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[dict]:
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if actor_id:
        query = query.filter(AuditLog.actor_id == actor_id)
    if target_type:
        query = query.filter(AuditLog.target_type == target_type)
    total = query.count()
    rows = query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset).all()
    return Page(
        items=[
            {
                "id": r.id, "created_at": r.created_at, "actor_email": r.actor_email,
                "actor_role": r.actor_role, "action": r.action, "target_type": r.target_type,
                "target_id": r.target_id, "organization_id": r.organization_id,
                "ip_address": r.ip_address, "detail": r.detail,
            }
            for r in rows
        ],
        total=total, limit=limit, offset=offset,
    )


@router.get("/jobs", response_model=Page[dict])
def analysis_jobs(
    user: RequireAdmin, db: DbSession,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[dict]:
    query = db.query(AnalysisJob)
    if status_filter:
        query = query.filter(AnalysisJob.status == status_filter)
    total = query.count()
    rows = query.order_by(AnalysisJob.created_at.desc()).limit(limit).offset(offset).all()
    repositories = {
        r.id: r.full_name
        for r in db.query(Repository).filter(
            Repository.id.in_([j.repository_id for j in rows] or ["-"])
        ).all()
    }
    return Page(
        items=[
            {
                "id": j.id, "repository": repositories.get(j.repository_id, j.repository_id),
                "status": j.status, "progress": j.progress, "current_stage": j.current_stage,
                "worker": j.worker, "error": j.error, "created_at": j.created_at,
                "duration_seconds": j.duration_seconds,
            }
            for j in rows
        ],
        total=total, limit=limit, offset=offset,
    )


@router.get("/analyzer-failures", response_model=list[dict])
def analyzer_failures(
    user: RequireAdmin, db: DbSession, limit: int = Query(default=100, ge=1, le=500)
) -> list[dict]:
    rows = (
        db.query(AnalyzerFailureRecord)
        .order_by(AnalyzerFailureRecord.created_at.desc()).limit(limit).all()
    )
    return [
        {
            "id": r.id, "created_at": r.created_at, "analyzer": r.analyzer,
            "category": r.category, "reason": r.reason, "repository_id": r.repository_id,
            "traceback_digest": r.traceback_digest,
        }
        for r in rows
    ]


@router.get("/users", response_model=Page[dict])
def list_users(
    user: RequireAdmin, db: DbSession,
    role: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[dict]:
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    total = query.count()
    rows = query.order_by(User.created_at.desc()).limit(limit).offset(offset).all()
    return Page(
        items=[
            {
                "id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role,
                "is_active": u.is_active, "is_demo": u.is_demo, "created_at": u.created_at,
                "last_login_at": u.last_login_at,
            }
            for u in rows
        ],
        total=total, limit=limit, offset=offset,
    )


@router.post("/users/{user_id}/role", response_model=Message)
def set_user_role(user_id: str, role: str, user: RequireAdmin, db: DbSession) -> Message:
    if role not in ("STUDENT", "INTERVIEWER", "ADMIN"):
        raise NotFoundError("Unknown role.")
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found.")
    target.role = role
    db.add(target)
    from app.services import audit

    audit.record(db, "admin.role_changed", actor=user, target_type="user", target_id=target.id,
                 detail={"new_role": role})
    db.commit()
    return Message(message=f"{target.email} is now {role}.")


@router.post("/users/{user_id}/deactivate", response_model=Message)
def deactivate_user(user_id: str, user: RequireAdmin, db: DbSession) -> Message:
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found.")
    target.is_active = False
    db.add(target)
    from app.services import audit

    audit.record(db, "admin.user_deactivated", actor=user, target_type="user", target_id=target.id)
    db.commit()
    return Message(message=f"{target.email} has been deactivated.")
