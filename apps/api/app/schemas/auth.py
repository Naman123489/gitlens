"""Authentication payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel

ROLES = ("STUDENT", "INTERVIEWER", "ADMIN")


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
        if value.lower() in ("password12", "letmein123", "changeme123"):
            raise ValueError("password is too common")
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
