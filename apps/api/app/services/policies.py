"""Policy persistence with immutable versioning."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from repolens_scoring import (
    DEFAULT_POLICY,
    PRESET_POLICIES,
    EvaluationPolicy,
    PolicyError,
    VerificationThresholds,
    validate_weights,
)
from repolens_shared import ScoreCategory

from app.core.errors import NotFoundError, ValidationError
from app.models import EvaluationPolicyRecord


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "policy"


def to_domain(record: EvaluationPolicyRecord) -> EvaluationPolicy:
    thresholds_defaults = VerificationThresholds().to_dict()
    thresholds = VerificationThresholds(
        **{k: (record.thresholds or {}).get(k, v) for k, v in thresholds_defaults.items()}
    )
    return EvaluationPolicy(
        name=record.name,
        version=record.version,
        weights={ScoreCategory(k): float(v) for k, v in (record.weights or {}).items()},
        thresholds=thresholds,
        organization_id=record.organization_id,
        description=record.description,
    )


def create_policy(
    db: Session, name: str, weights: dict[str, float], thresholds: dict[str, Any] | None = None,
    description: str = "", organization_id: str | None = None, created_by_id: str | None = None,
    policy_key: str | None = None,
) -> EvaluationPolicyRecord:
    """Create a policy, or a new immutable version of an existing one."""
    try:
        validate_weights({ScoreCategory(k): float(v) for k, v in weights.items()})
    except (PolicyError, ValueError) as exc:
        raise ValidationError(f"Invalid policy weights: {exc}") from exc

    key = policy_key or slugify(name)
    previous = (
        db.query(EvaluationPolicyRecord)
        .filter(
            EvaluationPolicyRecord.policy_key == key,
            EvaluationPolicyRecord.organization_id == organization_id,
        )
        .order_by(EvaluationPolicyRecord.version.desc())
        .first()
    )
    version = (previous.version + 1) if previous else 1
    if previous is not None:
        # Past versions stay readable so historic evaluations can be explained.
        db.query(EvaluationPolicyRecord).filter(
            EvaluationPolicyRecord.policy_key == key,
            EvaluationPolicyRecord.organization_id == organization_id,
        ).update({"is_current": False})

    record = EvaluationPolicyRecord(
        organization_id=organization_id, policy_key=key, name=name, description=description,
        version=version, is_current=True, weights={k: float(v) for k, v in weights.items()},
        thresholds=thresholds or VerificationThresholds().to_dict(),
        created_by_id=created_by_id,
    )
    db.add(record)
    db.flush()
    return record


def get_policy_record(db: Session, policy_id: str | None) -> EvaluationPolicyRecord | None:
    if not policy_id:
        return None
    record = db.get(EvaluationPolicyRecord, policy_id)
    if record is None:
        raise NotFoundError("Evaluation policy not found.")
    return record


def resolve_policy(
    db: Session, policy_id: str | None, organization_id: str | None = None
) -> tuple[EvaluationPolicy, str | None]:
    """Resolve the policy to score with, falling back to the default.

    Returns the domain policy plus the id of the record it came from (``None``
    for the built-in default), which the evaluation records for reproducibility.
    """
    record = get_policy_record(db, policy_id)
    if record is not None:
        return to_domain(record), record.id
    if organization_id:
        record = (
            db.query(EvaluationPolicyRecord)
            .filter(
                EvaluationPolicyRecord.organization_id == organization_id,
                EvaluationPolicyRecord.is_current.is_(True),
            )
            .order_by(EvaluationPolicyRecord.created_at.desc())
            .first()
        )
        if record is not None:
            return to_domain(record), record.id
    return DEFAULT_POLICY, None


def ensure_presets(db: Session) -> list[EvaluationPolicyRecord]:
    """Install the built-in preset policies as global (organization-less) rows."""
    created: list[EvaluationPolicyRecord] = []
    for preset in PRESET_POLICIES:
        key = slugify(preset.name)
        exists = (
            db.query(EvaluationPolicyRecord)
            .filter(
                EvaluationPolicyRecord.policy_key == key,
                EvaluationPolicyRecord.organization_id.is_(None),
            )
            .first()
        )
        if exists:
            continue
        created.append(create_policy(
            db, name=preset.name, weights={str(k): v for k, v in preset.weights.items()},
            thresholds=preset.thresholds.to_dict(), description=preset.description,
            organization_id=None, policy_key=key,
        ))
    return created
