"""Users, organizations, membership, candidates and GitHub accounts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="STUDENT", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    memberships: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    github_accounts: Mapped[list["GitHubAccount"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    candidate_profile: Mapped["Candidate | None"] = relationship(
        back_populates="user", uselist=False,
        primaryjoin="User.id == foreign(Candidate.user_id)",
    )


class Organization(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    members: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class OrganizationMember(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
    )

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Role *within* the organization: OWNER | INTERVIEWER | VIEWER
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="INTERVIEWER")

    organization: Mapped[Organization] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class GitHubAccount(UUIDMixin, TimestampMixin, Base):
    """A linked GitHub identity.

    ``access_token_encrypted`` is ciphertext; the plaintext token is never
    returned by the API and never reaches the frontend.
    """

    __tablename__ = "github_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "github_user_id", name="uq_github_account"),
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    github_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    login: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    profile_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    verified_emails: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="github_accounts")

    @property
    def can_read_private(self) -> bool:
        return "repo" in {s.strip() for s in self.scopes.split(",")}


class Candidate(UUIDMixin, TimestampMixin, Base):
    """A person being evaluated.

    A candidate may exist without a user account (added by an interviewer), or be
    linked to a student's own account.
    """

    __tablename__ = "candidates"
    __table_args__ = (
        Index("ix_candidates_org_email", "organization_id", "email"),
    )

    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    github_login: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    headline: Mapped[str | None] = mapped_column(String(300), nullable=True)
    resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    resume_parsed: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    ai_disclosure: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    user: Mapped[User | None] = relationship(
        back_populates="candidate_profile",
        primaryjoin="foreign(Candidate.user_id) == User.id",
    )
