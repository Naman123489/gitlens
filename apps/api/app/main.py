"""RepoLens API application."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from repolens_shared.versioning import ANALYZER_VERSION, SCORING_ENGINE_VERSION

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.errors import RateLimitError, register_error_handlers
from app.core.logging import configure_logging, get_logger, request_id_var
from app.services.queue import backend_status
from app.services.ratelimit_dep import global_rate_limit

settings = get_settings()
configure_logging(settings.environment)
logger = get_logger("repolens.api")

DESCRIPTION = """
RepoLens evaluates GitHub repositories against a target job description and produces an
evidence-backed engineering evaluation.

**What this API does not do.** It does not decide hiring outcomes, it does not claim that code
was written by an AI, and it never returns a value that was not derived from analysed evidence.
Every probabilistic conclusion carries a confidence and a list of limitations, and an analyzer
that fails reports its dimension as unavailable rather than substituting an estimate.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    problems = settings.validate_for_runtime()
    for problem in problems:
        logger.error("configuration_problem", problem=problem)
    if problems and settings.is_production:
        raise RuntimeError(
            "Refusing to start with insecure configuration: " + "; ".join(problems)
        )
    queue = backend_status()
    logger.info(
        "api_starting", environment=settings.environment, queue_backend=queue["backend"],
        analyzer_version=ANALYZER_VERSION, github_oauth=settings.github_oauth_configured,
        llm_configured=settings.llm_configured,
    )
    if queue["note"]:
        logger.warning("queue_degraded", note=queue["note"])
    yield
    logger.info("api_stopping")


app = FastAPI(
    title="RepoLens API",
    description=DESCRIPTION,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request id, time the request, and apply the global rate limit."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        if request.url.path.startswith(settings.api_prefix):
            try:
                global_rate_limit(request)
            except RateLimitError as exc:
                return JSONResponse(
                    status_code=429,
                    content={"error": {"code": exc.code, "message": exc.message,
                                       "detail": exc.detail, "request_id": request_id}},
                    headers={"Retry-After": str(exc.detail.get("retry_after", 60))},
                )
        response = await call_next(request)
    finally:
        duration_ms = (time.perf_counter() - started) * 1000
        request_id_var.reset(token)
    response.headers["x-request-id"] = request_id
    response.headers["x-response-time-ms"] = f"{duration_ms:.1f}"
    if duration_ms > 2000:
        logger.warning("slow_request", path=request.url.path, duration_ms=round(duration_ms, 1))
    return response


register_error_handlers(app)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health", tags=["system"])
def health() -> dict:
    """Unauthenticated liveness probe."""
    return {
        "status": "ok",
        "service": "repolens-api",
        "version": app.version,
        "analyzer_version": ANALYZER_VERSION,
        "scoring_engine_version": SCORING_ENGINE_VERSION,
        "environment": settings.environment,
    }


@app.get("/", tags=["system"])
def root() -> dict:
    return {
        "service": "RepoLens API",
        "documentation": "/docs",
        "api": settings.api_prefix,
        "principle": (
            "RepoLens determines whether a candidate demonstrates real engineering ability, "
            "ownership, relevance and understanding — regardless of the tools they used."
        ),
    }
