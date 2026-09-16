"""GitHub OAuth (web application flow).

The access token never leaves the backend: the frontend receives a RepoLens
session token, and the GitHub token is stored encrypted server-side.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from .client import OAUTH_SCOPES_PRIVATE, OAUTH_SCOPES_PUBLIC, GitHubError

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"


@dataclass(frozen=True, slots=True)
class OAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    request_private_repos: bool = False

    @property
    def scopes(self) -> str:
        return OAUTH_SCOPES_PRIVATE if self.request_private_repos else OAUTH_SCOPES_PUBLIC


@dataclass(frozen=True, slots=True)
class OAuthToken:
    access_token: str
    token_type: str
    scope: str

    def granted_scopes(self) -> set[str]:
        return {s.strip() for s in self.scope.split(",") if s.strip()}

    def can_read_private(self) -> bool:
        return "repo" in self.granted_scopes()


def generate_state() -> str:
    """CSRF state for the authorization request."""
    return secrets.token_urlsafe(32)


def build_authorize_url(config: OAuthConfig, state: str) -> str:
    query = urlencode(
        {
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "scope": config.scopes,
            "state": state,
            "allow_signup": "true",
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


async def exchange_code(
    config: OAuthConfig, code: str, transport: httpx.AsyncBaseTransport | None = None
) -> OAuthToken:
    """Exchange an authorization code for an access token."""
    async with httpx.AsyncClient(timeout=20.0, transport=transport) as client:
        response = await client.post(
            TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "code": code,
                "redirect_uri": config.redirect_uri,
            },
        )
    if response.status_code >= 400:
        raise GitHubError(f"OAuth token exchange failed ({response.status_code})", response.status_code)
    payload = response.json()
    if "error" in payload:
        raise GitHubError(
            f"OAuth token exchange failed: {payload.get('error_description', payload['error'])}"
        )
    if "access_token" not in payload:
        raise GitHubError("OAuth token exchange returned no access token")
    return OAuthToken(
        access_token=payload["access_token"],
        token_type=payload.get("token_type", "bearer"),
        scope=payload.get("scope", ""),
    )
