"""Authentication payloads."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel

ROLES = ("STUDENT", "INTERVIEWER", "ADMIN")

#: Passwords whose base word is guessed first in any credential-stuffing list.
#: Checked after stripping trailing digits and common leetspeak, so `password123`
#: and `p4ssw0rd!` are rejected along with `password`.
_COMMON_BASES: frozenset[str] = frozenset(
    {
        "password", "passwd", "letmein", "changeme", "welcome", "qwerty", "qwertyuiop",
        "abc", "abcdef", "iloveyou", "admin", "administrator", "root", "login",
        "monkey", "dragon", "football", "baseball", "sunshine", "princess", "shadow",
        "master", "superman", "trustno", "starwars", "whatever", "freedom", "secret",
        "test", "testing", "demo", "sample", "default", "user", "guest", "repolens",
    }
)

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})

_TRAILING_NOISE = re.compile(r"[^a-z]+$")
_LEADING_NOISE = re.compile(r"^[^a-z]+")


def _base_words(password: str) -> set[str]:
    """Candidate base words a password is built from.

    Trailing and leading digits and punctuation are stripped *before* leetspeak
    is folded, because folding first turns `password123` into `passwordize` and
    hides the base word entirely. Both the folded and unfolded forms are
    returned, so `p4ssw0rd` and `password99` are both caught.
    """
    lowered = password.lower()
    candidates: set[str] = set()
    for variant in (lowered, lowered.translate(_LEET)):
        trimmed = _TRAILING_NOISE.sub("", _LEADING_NOISE.sub("", variant))
        if trimmed:
            candidates.add(trimmed)
            candidates.add(re.sub(r"[^a-z]", "", trimmed))
    return {candidate for candidate in candidates if candidate}


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    #: Admin accounts are never self-service; the value is validated below.
    role: Literal["STUDENT", "INTERVIEWER"] = "STUDENT"
    organization_name: str | None = Field(default=None, max_length=200)

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        if value.isdigit() or value.isalpha():
            raise ValueError("password must mix letters with numbers or symbols")
        if len(set(value)) < 5:
            raise ValueError("password repeats too few distinct characters")
        for base in _base_words(value):
            if base in _COMMON_BASES or any(
                base.startswith(common) and len(base) - len(common) <= 3
                for common in _COMMON_BASES
            ):
                raise ValueError(
                    "password is based on a commonly guessed word; choose something unrelated to it"
                )
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class GitHubAccountOut(ORMModel):
    id: str
    login: str
    name: str | None = None
    avatar_url: str | None = None
    profile_url: str | None = None
    scopes: str
    can_read_private: bool = False
    connected_at: datetime | None = None


class UserOut(ORMModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    is_demo: bool
    avatar_url: str | None = None
    created_at: datetime
    last_login_at: datetime | None = None


class MeOut(BaseModel):
    user: UserOut
    organizations: list[dict] = []
    github_accounts: list[GitHubAccountOut] = []
    candidate_id: str | None = None


class AuthResponse(BaseModel):
    user: UserOut
    tokens: TokenPair


class GitHubAuthorizeOut(BaseModel):
    authorize_url: str
    state: str
    scopes: str
    configured: bool
    note: str | None = None
