"""FastAPI dependencies: authentication, authorization and shared services."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import TokenError, decode_token
from app.db.session import get_db
from app.models import Organization, OrganizationMember, User

ROLE_RANK = {"STUDENT": 1, "INTERVIEWER": 2, "ADMIN": 3}


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Resolve the caller from the bearer token.

    The token is also accepted from the ``repolens_session`` cookie so the OAuth
    redirect flow can hand the browser a session without exposing the token to
    JavaScript.
    """
    token: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        token = request.cookies.get("repolens_session")
    if not token:
        raise UnauthorizedError("Authentication is required.")

    try:
        payload = decode_token(token, expected_type="access")
    except TokenError as exc:
        raise UnauthorizedError(str(exc)) from exc

    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise UnauthorizedError("This account is no longer active.")
    request.state.user = user
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def require_role(*roles: str):
    """Dependency factory enforcing a minimum role.

    ADMIN satisfies every requirement; otherwise the role must be listed.
    """

    def _dependency(user: CurrentUser) -> User:
        if user.role == "ADMIN" or user.role in roles:
            return user
        raise ForbiddenError(
            f"This action requires one of: {', '.join(roles)}.",
            {"required_roles": list(roles), "your_role": user.role},
        )

    return _dependency


RequireInterviewer = Annotated[User, Depends(require_role("INTERVIEWER"))]
RequireAdmin = Annotated[User, Depends(require_role("ADMIN"))]


def get_membership(db: Session, user: User, organization_id: str) -> OrganizationMember | None:
    return (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user.id,
        )
        .one_or_none()
    )


def require_organization(db: Session, user: User, organization_id: str) -> Organization:
    """Assert the caller may act inside an organization.

    Admins may access any organization; everyone else must be a member. Raises
    ``NotFoundError`` rather than ``ForbiddenError`` for non-members so the API
    does not confirm the existence of organizations the caller cannot see.
    """
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise NotFoundError("Organization not found.")
    if user.role == "ADMIN":
        return organization
    if get_membership(db, user, organization_id) is None:
        raise NotFoundError("Organization not found.")
    return organization


def user_organization_ids(db: Session, user: User) -> list[str]:
    if user.role == "ADMIN":
        return [row.id for row in db.query(Organization.id).all()]
    return [
        row.organization_id
        for row in db.query(OrganizationMember.organization_id)
        .filter(OrganizationMember.user_id == user.id)
        .all()
    ]
