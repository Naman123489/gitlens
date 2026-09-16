"""RepoLens GitHub integration."""

from .client import (
    OAUTH_SCOPES_PRIVATE,
    OAUTH_SCOPES_PUBLIC,
    CacheBackend,
    GitHubClient,
    GitHubError,
    InMemoryCache,
    RateLimitedError,
)
from .fetcher import (
    FetchError,
    FetchedRepository,
    RemoteProbe,
    clone_repository,
    probe_public_repository,
)
from .models import GitHubRepository, GitHubUser, RateLimitState
from .oauth import OAuthConfig, OAuthToken, build_authorize_url, exchange_code, generate_state

__all__ = [
    "CacheBackend", "FetchError", "FetchedRepository", "GitHubClient", "GitHubError",
    "GitHubRepository", "GitHubUser", "InMemoryCache", "OAUTH_SCOPES_PRIVATE",
    "RemoteProbe", "probe_public_repository",
    "OAUTH_SCOPES_PUBLIC", "OAuthConfig", "OAuthToken", "RateLimitState", "RateLimitedError",
    "build_authorize_url", "clone_repository", "exchange_code", "generate_state",
]
