"""GitHub REST client.

Handles the three things that break naive GitHub integrations: rate limits,
pagination and conditional requests. A pluggable cache stores ETags so repeated
metadata reads cost no rate-limit budget.

Tokens are held by this object and never serialised into responses.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from .models import GitHubRepository, GitHubUser, RateLimitState

logger = logging.getLogger(__name__)

API_ROOT = "https://api.github.com"
DEFAULT_TIMEOUT = 20.0
MAX_RETRIES = 3

#: The minimum scopes RepoLens requests. Nothing here grants write access.
OAUTH_SCOPES_PUBLIC = "read:user user:email"
OAUTH_SCOPES_PRIVATE = "read:user user:email repo"


class GitHubError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None,
                 documentation_url: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.documentation_url = documentation_url


class RateLimitedError(GitHubError):
    def __init__(self, message: str, reset_at: datetime | None) -> None:
        super().__init__(message, status_code=429)
        self.reset_at = reset_at


class CacheBackend(Protocol):
    """Minimal cache contract so Redis or an in-memory dict both fit."""

    def get(self, key: str) -> dict[str, Any] | None: ...
    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None: ...


@dataclass
class InMemoryCache:
    """Process-local cache used in tests and when Redis is unavailable."""

    _store: dict[str, tuple[float, dict[str, Any]]] | None = None

    def __post_init__(self) -> None:
        self._store = {}

    def get(self, key: str) -> dict[str, Any] | None:
        entry = (self._store or {}).get(key)
        if not entry:
            return None
        expires_at, value = entry
        if expires_at < time.time():
            (self._store or {}).pop(key, None)
            return None
        return value

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        (self._store if self._store is not None else {})[key] = (time.time() + ttl_seconds, value)


class GitHubClient:
    """Async GitHub REST client scoped to one access token."""

    def __init__(
        self,
        token: str | None = None,
        cache: CacheBackend | None = None,
        api_root: str = API_ROOT,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str = "RepoLens/0.1",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._cache = cache or InMemoryCache()
        self._api_root = api_root.rstrip("/")
        self.rate_limit = RateLimitState()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": user_agent,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url=self._api_root, headers=headers, timeout=timeout, transport=transport,
        )

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- internals -----------------------------------------------------------

    def _record_rate_limit(self, response: httpx.Response) -> None:
        headers = response.headers
        try:
            self.rate_limit = RateLimitState(
                limit=int(headers.get("x-ratelimit-limit", 0) or 0),
                remaining=int(headers.get("x-ratelimit-remaining", 0) or 0),
                reset_at=datetime.fromtimestamp(
                    int(headers.get("x-ratelimit-reset", 0) or 0), tz=timezone.utc
                ) if headers.get("x-ratelimit-reset") else None,
                resource=headers.get("x-ratelimit-resource", "core"),
            )
        except (TypeError, ValueError):  # pragma: no cover - malformed headers
            pass

    async def request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None,
        cache_ttl: int = 300, json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Issue a request with ETag revalidation, retry and rate-limit handling."""
        cache_key = f"gh:{method}:{path}:{sorted((params or {}).items())}"
        cached = self._cache.get(cache_key) if method == "GET" else None
        headers: dict[str, str] = {}
        if cached and cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = await self._client.request(
                    method, path, params=params, headers=headers, json=json_body
                )
            except httpx.HTTPError as exc:
                last_error = exc
                await asyncio.sleep(0.5 * (2**attempt))
                continue

            self._record_rate_limit(response)

            if response.status_code == 304 and cached:
                return cached["payload"]

            if response.status_code in (403, 429):
                remaining = response.headers.get("x-ratelimit-remaining")
                retry_after = response.headers.get("retry-after")
                if remaining == "0" or retry_after:
                    raise RateLimitedError(
                        "GitHub API rate limit exceeded. "
                        f"Resets at {self.rate_limit.reset_at.isoformat() if self.rate_limit.reset_at else 'unknown'}.",
                        self.rate_limit.reset_at,
                    )
                raise GitHubError(_error_message(response), response.status_code)

            if response.status_code == 404:
                raise GitHubError(f"GitHub resource not found: {path}", 404)
            if response.status_code == 401:
                raise GitHubError("GitHub rejected the access token (401).", 401)
            if response.status_code >= 500:
                last_error = GitHubError(_error_message(response), response.status_code)
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            if response.status_code >= 400:
                raise GitHubError(_error_message(response), response.status_code)

            payload = response.json() if response.content else None
            if method == "GET" and cache_ttl > 0:
                self._cache.set(
                    cache_key,
                    {"etag": response.headers.get("etag"), "payload": payload},
                    cache_ttl,
                )
            return payload

        raise GitHubError(f"GitHub request failed after {MAX_RETRIES} attempts: {last_error}")

    async def paginate(
        self, path: str, *, params: dict[str, Any] | None = None,
        per_page: int = 100, max_pages: int = 10, cache_ttl: int = 300,
    ) -> list[Any]:
        items: list[Any] = []
        for page in range(1, max_pages + 1):
            payload = await self.request(
                "GET", path, params={**(params or {}), "per_page": per_page, "page": page},
                cache_ttl=cache_ttl,
            )
            if not payload:
                break
            batch = payload if isinstance(payload, list) else payload.get("items", [])
            items.extend(batch)
            if len(batch) < per_page:
                break
        return items

    # -- API surface ---------------------------------------------------------

    async def get_authenticated_user(self) -> GitHubUser:
        return GitHubUser.from_api(await self.request("GET", "/user", cache_ttl=60))

    async def get_user(self, login: str) -> GitHubUser:
        return GitHubUser.from_api(await self.request("GET", f"/users/{login}", cache_ttl=900))

    async def get_user_emails(self) -> list[str]:
        """Verified addresses for the authenticated user, used for commit attribution."""
        try:
            payload = await self.request("GET", "/user/emails", cache_ttl=900)
        except GitHubError:
            return []
        return [e["email"].lower() for e in payload or [] if e.get("verified")]

    async def list_repositories(
        self, visibility: str = "all", affiliation: str = "owner,collaborator", max_pages: int = 5
    ) -> list[GitHubRepository]:
        payload = await self.paginate(
            "/user/repos",
            params={"visibility": visibility, "affiliation": affiliation, "sort": "pushed"},
            max_pages=max_pages, cache_ttl=180,
        )
        return [GitHubRepository.from_api(item) for item in payload]

    async def list_public_repositories(self, login: str, max_pages: int = 3) -> list[GitHubRepository]:
        payload = await self.paginate(
            f"/users/{login}/repos", params={"sort": "pushed", "type": "owner"},
            max_pages=max_pages, cache_ttl=300,
        )
        return [GitHubRepository.from_api(item) for item in payload]

    async def get_repository(self, owner: str, repo: str) -> GitHubRepository:
        return GitHubRepository.from_api(
            await self.request("GET", f"/repos/{owner}/{repo}", cache_ttl=300)
        )

    async def get_languages(self, owner: str, repo: str) -> dict[str, int]:
        return await self.request("GET", f"/repos/{owner}/{repo}/languages", cache_ttl=900) or {}

    async def get_readme(self, owner: str, repo: str) -> str | None:
        import base64

        try:
            payload = await self.request("GET", f"/repos/{owner}/{repo}/readme", cache_ttl=900)
        except GitHubError:
            return None
        if not payload or payload.get("encoding") != "base64":
            return None
        try:
            return base64.b64decode(payload["content"]).decode("utf-8", errors="replace")
        except (KeyError, ValueError):  # pragma: no cover - malformed payload
            return None

    async def list_branches(self, owner: str, repo: str) -> list[dict[str, Any]]:
        return await self.paginate(f"/repos/{owner}/{repo}/branches", max_pages=2, cache_ttl=600)

    async def list_contributors(self, owner: str, repo: str) -> list[dict[str, Any]]:
        try:
            return await self.paginate(f"/repos/{owner}/{repo}/contributors", max_pages=2, cache_ttl=600)
        except GitHubError:
            return []

    async def list_releases(self, owner: str, repo: str) -> list[dict[str, Any]]:
        return await self.paginate(f"/repos/{owner}/{repo}/releases", max_pages=2, cache_ttl=900)

    async def list_pull_requests(self, owner: str, repo: str, state: str = "all") -> list[dict[str, Any]]:
        return await self.paginate(
            f"/repos/{owner}/{repo}/pulls", params={"state": state}, max_pages=2, cache_ttl=600
        )

    async def list_issues(self, owner: str, repo: str, state: str = "all") -> list[dict[str, Any]]:
        issues = await self.paginate(
            f"/repos/{owner}/{repo}/issues", params={"state": state}, max_pages=2, cache_ttl=600
        )
        # The issues endpoint also returns pull requests; filter them out.
        return [i for i in issues if "pull_request" not in i]

    async def get_rate_limit(self) -> dict[str, Any]:
        return await self.request("GET", "/rate_limit", cache_ttl=0) or {}


def _error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
        return f"GitHub API error {response.status_code}: {payload.get('message', response.text[:200])}"
    except ValueError:
        return f"GitHub API error {response.status_code}: {response.text[:200]}"
