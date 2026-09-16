"""Authentication primitives: password hashing, JWTs and credential encryption.

Three separate concerns, deliberately kept apart:

* **Passwords** are hashed with bcrypt. Plaintext never leaves the request.
* **Sessions** use short-lived signed JWTs plus a longer-lived refresh token.
* **GitHub tokens** are encrypted at rest with Fernet (AES-128-CBC + HMAC)
  under a key derived from ``ENCRYPTION_KEY``. They are decrypted only inside
  the worker and the GitHub service, and never serialised into an API response.
"""

from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

TokenType = Literal["access", "refresh"]

_MAX_PASSWORD_BYTES = 72  # bcrypt truncates beyond this


class TokenError(ValueError):
    pass


# -- passwords ---------------------------------------------------------------

def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("password must be at least 10 characters")
    return bcrypt.hashpw(
        password.encode("utf-8")[:_MAX_PASSWORD_BYTES], bcrypt.gensalt()
    ).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-time-ish verification that does not leak whether a user exists.

    When ``password_hash`` is ``None`` (an OAuth-only account) a dummy hash is
    still checked so the timing profile matches an existing account.
    """
    candidate = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    if not password_hash:
        bcrypt.checkpw(candidate, bcrypt.hashpw(b"dummy", bcrypt.gensalt()))
        return False
    try:
        return bcrypt.checkpw(candidate, password_hash.encode("utf-8"))
    except ValueError:
        return False


# -- JWT ---------------------------------------------------------------------

def create_token(
    subject: str, role: str, token_type: TokenType = "access",
    extra_claims: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    ttl = (
        timedelta(minutes=settings.access_token_ttl_minutes) if token_type == "access"
        else timedelta(days=settings.refresh_token_ttl_days)
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": secrets.token_urlsafe(12),
        "iss": "repolens",
        **(extra_claims or {}),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], issuer="repolens",
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("token is invalid") from exc
    if expected_type and payload.get("type") != expected_type:
        raise TokenError(f"expected a {expected_type} token")
    return payload


# -- credential encryption ---------------------------------------------------

def _cipher() -> Fernet:
    return Fernet(get_settings().fernet_key)


def encrypt_secret(value: str) -> str:
    return _cipher().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _cipher().decrypt(value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        # A rotated ENCRYPTION_KEY invalidates stored tokens. Surfacing None lets
        # the caller ask the user to reconnect instead of crashing.
        return None


def constant_time_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())
