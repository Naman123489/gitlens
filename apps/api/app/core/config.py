"""Application configuration.

All configuration comes from the environment. Nothing here has a production-safe
default that would let the service start insecurely by accident: the JWT secret
and encryption key are validated on startup when ``environment`` is not
``development``.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"), env_file_encoding="utf-8", extra="ignore",
    )

    # -- application ---------------------------------------------------------
    app_name: str = "RepoLens"
    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    frontend_url: str = "http://localhost:3000"
    #: Accepts a comma-separated list or a JSON array. `NoDecode` is required
    #: because pydantic-settings would otherwise try to JSON-decode the value
    #: before the validator below runs, so a bare URL would fail to parse.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # -- database ------------------------------------------------------------
    database_url: str = "postgresql+psycopg://repolens:repolens@localhost:5432/repolens"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_echo: bool = False

    # -- redis / queue -------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "repolens-analysis"
    #: When Redis is unavailable, run jobs on a local thread pool instead of
    #: failing. Exercised in development and tests; production uses workers.
    allow_inline_worker: bool = True

    # -- auth ----------------------------------------------------------------
    jwt_secret: str = "dev-insecure-jwt-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60
    refresh_token_ttl_days: int = 14
    #: Key used to encrypt stored GitHub tokens at rest.
    encryption_key: str = "dev-insecure-encryption-key-change-me"

    # -- github --------------------------------------------------------------
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:8000/api/v1/auth/github/callback"
    github_request_private_repos: bool = False

    # -- llm (optional) ------------------------------------------------------
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-5"
    llm_base_url: str = "https://api.anthropic.com"
    llm_max_output_tokens: int = 1600
    llm_timeout_seconds: float = 45.0

    # -- vector store --------------------------------------------------------
    vector_database_url: str = ""
    embedding_dimensions: int = 256

    # -- limits --------------------------------------------------------------
    max_repository_mb: int = 256
    max_files_per_repository: int = 12000
    max_file_kb: int = 1024
    analysis_timeout_seconds: int = 900
    clone_timeout_seconds: int = 300
    rate_limit_per_minute: int = 120
    rate_limit_analysis_per_hour: int = 20
    max_upload_bytes: int = 5 * 1024 * 1024

    # -- demo ----------------------------------------------------------------
    enable_demo_seed: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                import json

                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in text.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment in ("production", "staging")

    @property
    def github_oauth_configured(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret)

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def fernet_key(self) -> bytes:
        """Derive a stable 32-byte key from the configured secret."""
        return base64.urlsafe_b64encode(hashlib.sha256(self.encryption_key.encode()).digest())

    def validate_for_runtime(self) -> list[str]:
        """Return configuration problems. Fatal in production, warnings elsewhere."""
        problems: list[str] = []
        if self.is_production:
            if self.jwt_secret.startswith("dev-insecure"):
                problems.append("JWT_SECRET must be set to a strong random value in production")
            if self.encryption_key.startswith("dev-insecure"):
                problems.append("ENCRYPTION_KEY must be set to a strong random value in production")
            if self.debug:
                problems.append("DEBUG must be false in production")
            if "*" in self.cors_origins:
                problems.append("CORS_ORIGINS must not be '*' in production")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


def generate_secret() -> str:
    return secrets.token_urlsafe(48)
