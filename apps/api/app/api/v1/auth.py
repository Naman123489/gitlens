"""Authentication: email/password, GitHub OAuth and session management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import func

from repolens_github import (
    GitHubClient,
    GitHubError,
    OAuthConfig,
    build_authorize_url,
    exchange_code,
    generate_state,
)

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.errors import ConflictError, ForbiddenError, UnauthorizedError, ValidationError
from app.core.security import (
    TokenError,
    create_token,
    decode_token,
    encrypt_secret,
    hash_password,
    verify_password,
)
from app.models import Candidate, GitHubAccount, OAuthState, Organization, OrganizationMember, User
from app.schemas.auth import (
    AuthResponse,
    GitHubAccountOut,
    GitHubAuthorizeOut,
    LoginRequest,
    MeOut,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
)
from app.schemas.common import Message
from app.services import audit
from app.services.policies import slugify

router = APIRouter(prefix="/auth", tags=["auth"])

STATE_TTL_MINUTES = 15


def _tokens(user: User) -> TokenPair:
    settings = get_settings()
    return TokenPair(
        access_token=create_token(user.id, user.role, "access"),
        refresh_token=create_token(user.id, user.role, "refresh"),
        expires_in=settings.access_token_ttl_minutes * 60,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: DbSession, request: Request) -> AuthResponse:
    """Create an account.

    ADMIN cannot be requested here: administrators are provisioned with
    ``scripts/create_admin.py`` so privilege escalation is not a signup form away.
    """
    email = payload.email.lower()
    if db.query(User).filter(func.lower(User.email) == email).first():
        raise ConflictError("An account with this email already exists.")

    user = User(
        email=email, full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password), role=payload.role,
    )
    db.add(user)
    db.flush()

    if payload.role == "INTERVIEWER":
        name = payload.organization_name or f"{user.full_name}'s team"
        slug = slugify(name)
        if db.query(Organization).filter(Organization.slug == slug).first():
            slug = f"{slug}-{user.id[:6]}"
        organization = Organization(name=name, slug=slug, created_by_id=user.id)
        db.add(organization)
        db.flush()
        db.add(OrganizationMember(
            organization_id=organization.id, user_id=user.id, role="OWNER",
        ))
    else:
        db.add(Candidate(user_id=user.id, full_name=user.full_name, email=user.email))

    audit.record(db, audit.ACTION_REGISTER, actor=user, target_type="user",
                 target_id=user.id, detail={"role": user.role}, request=request)
    db.commit()
    db.refresh(user)
    return AuthResponse(user=UserOut.model_validate(user), tokens=_tokens(user))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: DbSession, request: Request, response: Response) -> AuthResponse:
    user = db.query(User).filter(func.lower(User.email) == payload.email.lower()).first()
    # The same message either way: the API must not confirm which emails exist.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("Email or password is incorrect.")
    if not user.is_active:
        raise ForbiddenError("This account has been deactivated.")

    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)
    audit.record(db, audit.ACTION_LOGIN, actor=user, target_type="user", target_id=user.id,
                 request=request)
    db.commit()

    tokens = _tokens(user)
    response.set_cookie(
        "repolens_session", tokens.access_token, httponly=True, samesite="lax",
        secure=get_settings().is_production, max_age=tokens.expires_in, path="/",
    )
    return AuthResponse(user=UserOut.model_validate(user), tokens=tokens)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise UnauthorizedError(str(exc)) from exc
    user = db.get(User, claims["sub"])
    if user is None or not user.is_active:
        raise UnauthorizedError("This account is no longer active.")
    return _tokens(user)


@router.post("/logout", response_model=Message)
def logout(response: Response) -> Message:
    response.delete_cookie("repolens_session", path="/")
    return Message(message="Signed out.")


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser, db: DbSession) -> MeOut:
    memberships = (
        db.query(OrganizationMember, Organization)
        .join(Organization, Organization.id == OrganizationMember.organization_id)
        .filter(OrganizationMember.user_id == user.id)
        .all()
    )
    candidate = db.query(Candidate).filter(Candidate.user_id == user.id).first()
    accounts = db.query(GitHubAccount).filter(GitHubAccount.user_id == user.id).all()
    return MeOut(
        user=UserOut.model_validate(user),
        organizations=[
            {"id": org.id, "name": org.name, "slug": org.slug, "role": membership.role}
            for membership, org in memberships
        ],
        github_accounts=[
            GitHubAccountOut(
                id=a.id, login=a.login, name=a.name, avatar_url=a.avatar_url,
                profile_url=a.profile_url, scopes=a.scopes,
                can_read_private=a.can_read_private, connected_at=a.connected_at,
            )
            for a in accounts
        ],
        candidate_id=candidate.id if candidate else None,
    )


@router.get("/github/authorize", response_model=GitHubAuthorizeOut)
def github_authorize(user: CurrentUser, db: DbSession) -> GitHubAuthorizeOut:
    """Start the GitHub OAuth handshake for the signed-in user."""
    settings = get_settings()
    if not settings.github_oauth_configured:
        return GitHubAuthorizeOut(
            authorize_url="", state="", scopes="", configured=False,
            note="GitHub OAuth is not configured on this deployment. Set GITHUB_CLIENT_ID and "
                 "GITHUB_CLIENT_SECRET to enable it.",
        )
    config = OAuthConfig(
        client_id=settings.github_client_id, client_secret=settings.github_client_secret,
        redirect_uri=settings.github_redirect_uri,
        request_private_repos=settings.github_request_private_repos,
    )
    state = generate_state()
    now = datetime.now(timezone.utc)
    db.add(OAuthState(
        state=state, user_id=user.id, intent="connect", created_at=now,
        expires_at=now + timedelta(minutes=STATE_TTL_MINUTES),
    ))
    db.commit()
    return GitHubAuthorizeOut(
        authorize_url=build_authorize_url(config, state), state=state,
        scopes=config.scopes, configured=True,
    )


@router.get("/github/callback", response_model=MeOut)
async def github_callback(
    code: str, state: str, db: DbSession, request: Request
) -> MeOut:
    """Complete the OAuth handshake.

    The access token is encrypted before it is stored and is never returned to
    the client.
    """
    settings = get_settings()
    if not settings.github_oauth_configured:
        raise ValidationError("GitHub OAuth is not configured on this deployment.")

    record = db.query(OAuthState).filter(OAuthState.state == state).first()
    if record is None or record.consumed:
        raise UnauthorizedError("This authorization request is invalid or has already been used.")
    if record.expires_at < datetime.now(timezone.utc):
        raise UnauthorizedError("This authorization request has expired. Please try again.")
    record.consumed = 1
    db.add(record)

    user = db.get(User, record.user_id) if record.user_id else None
    if user is None:
        raise UnauthorizedError("The account that started this authorization no longer exists.")

    config = OAuthConfig(
        client_id=settings.github_client_id, client_secret=settings.github_client_secret,
        redirect_uri=settings.github_redirect_uri,
        request_private_repos=settings.github_request_private_repos,
    )
    try:
        token = await exchange_code(config, code)
        async with GitHubClient(token.access_token) as client:
            profile = await client.get_authenticated_user()
            emails = await client.get_user_emails()
    except GitHubError as exc:
        raise ValidationError(f"GitHub authorization failed: {exc}") from exc

    account = (
        db.query(GitHubAccount)
        .filter(GitHubAccount.user_id == user.id, GitHubAccount.github_user_id == profile.id)
        .first()
    )
    if account is None:
        account = GitHubAccount(user_id=user.id, github_user_id=profile.id, login=profile.login)
    account.login = profile.login
    account.name = profile.name
    account.avatar_url = profile.avatar_url
    account.profile_url = profile.html_url
    account.access_token_encrypted = encrypt_secret(token.access_token)
    account.scopes = token.scope
    account.verified_emails = emails or ([profile.email.lower()] if profile.email else [])
    account.profile_snapshot = {
        "login": profile.login, "name": profile.name, "company": profile.company,
        "bio": profile.bio, "public_repos": profile.public_repos, "followers": profile.followers,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }
    account.connected_at = datetime.now(timezone.utc)
    db.add(account)

    if not user.avatar_url:
        user.avatar_url = profile.avatar_url
        db.add(user)
    candidate = db.query(Candidate).filter(Candidate.user_id == user.id).first()
    if candidate is not None and not candidate.github_login:
        candidate.github_login = profile.login
        db.add(candidate)

    audit.record(db, audit.ACTION_GITHUB_CONNECTED, actor=user, target_type="github_account",
                 target_id=account.id, detail={"login": profile.login, "scopes": token.scope},
                 request=request)
    db.commit()
    return me(user, db)


@router.delete("/github/{account_id}", response_model=Message)
def disconnect_github(
    account_id: str, user: CurrentUser, db: DbSession, request: Request
) -> Message:
    account = db.get(GitHubAccount, account_id)
    if account is None or account.user_id != user.id:
        raise UnauthorizedError("This GitHub account is not connected to your profile.")
    login = account.login
    db.delete(account)
    audit.record(db, audit.ACTION_GITHUB_DISCONNECTED, actor=user, target_type="github_account",
                 target_id=account_id, detail={"login": login}, request=request)
    db.commit()
    return Message(message=f"Disconnected GitHub account {login}.")
