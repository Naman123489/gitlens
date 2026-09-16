"""Typed views over the GitHub REST payloads RepoLens consumes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(slots=True)
class GitHubUser:
    id: int
    login: str
    name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    html_url: str | None = None
    company: str | None = None
    bio: str | None = None
    public_repos: int = 0
    followers: int = 0
    created_at: datetime | None = None

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "GitHubUser":
        return cls(
            id=payload["id"], login=payload["login"], name=payload.get("name"),
            email=payload.get("email"), avatar_url=payload.get("avatar_url"),
            html_url=payload.get("html_url"), company=payload.get("company"),
            bio=payload.get("bio"), public_repos=payload.get("public_repos", 0),
            followers=payload.get("followers", 0), created_at=_parse_dt(payload.get("created_at")),
        )


@dataclass(slots=True)
class GitHubRepository:
    id: int
    name: str
    full_name: str
    private: bool
    html_url: str
    clone_url: str
    default_branch: str
    description: str | None = None
    language: str | None = None
    stargazers_count: int = 0
    forks_count: int = 0
    open_issues_count: int = 0
    size_kb: int = 0
    fork: bool = False
    archived: bool = False
    topics: list[str] = field(default_factory=list)
    license_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pushed_at: datetime | None = None
    owner_login: str = ""

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "GitHubRepository":
        return cls(
            id=payload["id"], name=payload["name"], full_name=payload["full_name"],
            private=payload.get("private", False), html_url=payload.get("html_url", ""),
            clone_url=payload.get("clone_url", ""), default_branch=payload.get("default_branch", "main"),
            description=payload.get("description"), language=payload.get("language"),
            stargazers_count=payload.get("stargazers_count", 0),
            forks_count=payload.get("forks_count", 0),
            open_issues_count=payload.get("open_issues_count", 0),
            size_kb=payload.get("size", 0), fork=payload.get("fork", False),
            archived=payload.get("archived", False), topics=payload.get("topics") or [],
            license_name=((payload.get("license") or {}) or {}).get("name"),
            created_at=_parse_dt(payload.get("created_at")),
            updated_at=_parse_dt(payload.get("updated_at")),
            pushed_at=_parse_dt(payload.get("pushed_at")),
            owner_login=(payload.get("owner") or {}).get("login", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "full_name": self.full_name,
            "private": self.private, "html_url": self.html_url, "description": self.description,
            "language": self.language, "stars": self.stargazers_count, "forks": self.forks_count,
            "open_issues": self.open_issues_count, "size_kb": self.size_kb, "fork": self.fork,
            "archived": self.archived, "topics": self.topics, "license": self.license_name,
            "default_branch": self.default_branch,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "pushed_at": self.pushed_at.isoformat() if self.pushed_at else None,
            "owner": self.owner_login,
        }


@dataclass(slots=True)
class RateLimitState:
    limit: int = 0
    remaining: int = 0
    reset_at: datetime | None = None
    resource: str = "core"

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0 and self.limit > 0
