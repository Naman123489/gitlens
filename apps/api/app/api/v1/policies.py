"""Evaluation policies: presets, versioned creation and history."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from repolens_scoring import PRESET_POLICIES

from app.core.deps import CurrentUser, DbSession, require_organization, user_organization_ids
from app.core.errors import ForbiddenError, NotFoundError
from app.models import EvaluationPolicyRecord
from app.schemas.evaluation import PolicyCreate, PolicyOut
from app.services import audit, policies

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("/presets", response_model=list[dict])
def list_presets(user: CurrentUser) -> list[dict]:
    return [p.to_dict() for p in PRESET_POLICIES]


@router.get("", response_model=list[PolicyOut])
def list_policies(
    user: CurrentUser, db: DbSession, organization_id: str | None = None,
    include_history: bool = False,
) -> list[PolicyOut]:
    query = db.query(EvaluationPolicyRecord)
    if organization_id:
        require_organization(db, user, organization_id)
        query = query.filter(EvaluationPolicyRecord.organization_id == organization_id)
    elif user.role != "ADMIN":
        organization_ids = user_organization_ids(db, user)
        from sqlalchemy import or_

        query = query.filter(or_(
            EvaluationPolicyRecord.organization_id.is_(None),
            EvaluationPolicyRecord.organization_id.in_(organization_ids or ["-"]),
        ))
    if not include_history:
        query = query.filter(EvaluationPolicyRecord.is_current.is_(True))
    rows = query.order_by(
        EvaluationPolicyRecord.policy_key, EvaluationPolicyRecord.version.desc()
    ).all()
    return [PolicyOut.model_validate(r) for r in rows]


@router.post("", response_model=PolicyOut, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: PolicyCreate, user: CurrentUser, db: DbSession, request: Request
) -> PolicyOut:
    """Create a policy, or a new version of an existing one with the same name.

    Earlier versions are retained and remain readable so any historic evaluation
    can still be explained with the rules that produced it.
    """
    if user.role not in ("INTERVIEWER", "ADMIN"):
        raise ForbiddenError("Only interviewers can define evaluation policies.")
    organization_id = payload.organization_id
    if organization_id:
        require_organization(db, user, organization_id)
    else:
        owned = user_organization_ids(db, user)
        organization_id = owned[0] if owned else None

    record = policies.create_policy(
        db, name=payload.name, weights=payload.weights.as_dict(),
        thresholds=payload.thresholds or None, description=payload.description,
        organization_id=organization_id, created_by_id=user.id,
    )
    audit.record(
        db, audit.ACTION_POLICY_CREATED if record.version == 1 else audit.ACTION_POLICY_UPDATED,
        actor=user, target_type="evaluation_policy", target_id=record.id,
        organization_id=organization_id,
        detail={"name": record.name, "version": record.version, "weights": record.weights},
        request=request,
    )
    db.commit()
    db.refresh(record)
    return PolicyOut.model_validate(record)


@router.get("/{policy_id}", response_model=PolicyOut)
def get_policy(policy_id: str, user: CurrentUser, db: DbSession) -> PolicyOut:
    record = db.get(EvaluationPolicyRecord, policy_id)
    if record is None:
        raise NotFoundError("Evaluation policy not found.")
    if record.organization_id and user.role != "ADMIN":
        require_organization(db, user, record.organization_id)
    return PolicyOut.model_validate(record)


@router.get("/{policy_id}/versions", response_model=list[PolicyOut])
def policy_versions(policy_id: str, user: CurrentUser, db: DbSession) -> list[PolicyOut]:
    record = db.get(EvaluationPolicyRecord, policy_id)
    if record is None:
        raise NotFoundError("Evaluation policy not found.")
    if record.organization_id and user.role != "ADMIN":
        require_organization(db, user, record.organization_id)
    rows = (
        db.query(EvaluationPolicyRecord)
        .filter(
            EvaluationPolicyRecord.policy_key == record.policy_key,
            EvaluationPolicyRecord.organization_id == record.organization_id,
        )
        .order_by(EvaluationPolicyRecord.version.desc()).all()
    )
    return [PolicyOut.model_validate(r) for r in rows]
