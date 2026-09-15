"""Audit logging service.

Audit entries are written in the same transaction as the action they describe,
so an action can never succeed without its audit record.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog, User

#: Actions that must always be logged.
ACTION_EVALUATION_CREATED = "evaluation.created"
ACTION_EVALUATION_SCORED = "evaluation.scored"
ACTION_EVALUATION_VIEWED = "evaluation.viewed"
ACTION_OVERRIDE_CREATED = "evaluation.override"
ACTION_NOTE_CREATED = "evaluation.note"
ACTION_REPORT_GENERATED = "report.generated"
ACTION_REPOSITORY_ANALYZED = "repository.analyzed"
ACTION_REPOSITORY_ACCESSED = "repository.accessed"
ACTION_CANDIDATE_VIEWED = "candidate.viewed"
ACTION_CANDIDATE_CREATED = "candidate.created"
ACTION_GITHUB_CONNECTED = "github.connected"
ACTION_GITHUB_DISCONNECTED = "github.disconnected"
ACTION_POLICY_CREATED = "policy.created"
ACTION_POLICY_UPDATED = "policy.updated"
ACTION_JOB_CREATED = "job.created"
ACTION_LOGIN = "auth.login"
ACTION_REGISTER = "auth.register"
ACTION_INTERVIEW_CREATED = "interview.created"
ACTION_INTERVIEW_SCORED = "interview.scored"
ACTION_DISCLOSURE_UPDATED = "candidate.disclosure"


def record(
    db: Session,
    action: str,
    actor: User | None = None,
    target_type: str = "",
    target_id: str | None = None,
    organization_id: str | None = None,
    detail: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    """Append an audit entry. The caller commits."""
    entry = AuditLog(
        created_at=datetime.now(timezone.utc),
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else "",
        actor_role=actor.role if actor else "",
        organization_id=organization_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip_address=_client_ip(request),
        user_agent=(request.headers.get("user-agent", "")[:300] if request else None),
        detail=detail or {},
    )
    db.add(entry)
    return entry


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None
