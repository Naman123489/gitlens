"""Background job dispatch.

Redis + RQ is the supported production path. When Redis is unavailable the
dispatcher falls back to a bounded thread pool so a developer can run the whole
product with ``uvicorn`` alone. The fallback is reported honestly through
:func:`backend_status` and on the admin health endpoint — it is not a silent
substitution.

Either way the HTTP request returns immediately; analysis never runs inside a
request handler.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("repolens.queue")

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()
_inline_jobs: dict[str, str] = {}


@dataclass(frozen=True, slots=True)
class Dispatch:
    job_id: str
    backend: str


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="repolens-inline")
        return _executor


def get_redis() -> Any | None:
    """Return a live Redis connection, or ``None`` if Redis is unreachable."""
    settings = get_settings()
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001 - any failure means "no redis"
        logger.warning("redis_unavailable", error=str(exc)[:200])
        return None


def worker_status(redis_client: Any | None = None) -> dict[str, Any]:
    """Count workers actually listening on the queue.

    A reachable Redis is not enough: if nothing is consuming the queue, jobs sit
    at QUEUED forever. Reporting this explicitly turns a silent stall into a
    visible operational problem.
    """
    settings = get_settings()
    redis_client = redis_client or get_redis()
    if redis_client is None:
        return {"workers": 0, "queued": 0, "reachable": False}
    try:
        from rq import Queue, Worker

        queue = Queue(settings.queue_name, connection=redis_client)
        workers = [
            w for w in Worker.all(connection=redis_client)
            if settings.queue_name in [q.name for q in w.queues]
        ]
        return {
            "workers": len(workers),
            "busy_workers": sum(1 for w in workers if w.get_state() == "busy"),
            "queued": queue.count,
            "failed": queue.failed_job_registry.count,
            "reachable": True,
        }
    except Exception as exc:  # noqa: BLE001 - diagnostics must not raise
        logger.warning("worker_status_failed", error=str(exc)[:200])
        return {"workers": None, "queued": None, "reachable": True, "error": str(exc)[:200]}


def backend_status() -> dict[str, Any]:
    settings = get_settings()
    redis_client = get_redis()
    workers = worker_status(redis_client)

    note: str | None = None
    if redis_client is None:
        note = (
            "Redis is not reachable. Analyses run on an in-process thread pool, which does not "
            "survive a restart and does not scale beyond this instance."
        )
    elif workers.get("workers") == 0:
        note = (
            f"Redis is reachable but no worker is listening on '{settings.queue_name}'. Queued "
            "analyses will not start until one is running: `python -m app.workers.run_worker`."
        )

    return {
        "backend": "redis-rq" if redis_client else (
            "in-process-threads" if settings.allow_inline_worker else "unavailable"
        ),
        "redis_reachable": redis_client is not None,
        "queue_name": settings.queue_name,
        "inline_allowed": settings.allow_inline_worker,
        "healthy": bool(redis_client) and bool(workers.get("workers")) or (
            redis_client is None and settings.allow_inline_worker
        ),
        **{k: v for k, v in workers.items() if k != "reachable"},
        "note": note,
    }


def enqueue(func: Callable[..., Any], *args: Any, job_timeout: int | None = None, **kwargs: Any) -> Dispatch:
    """Dispatch work to a worker.

    Raises ``RuntimeError`` when neither Redis nor the inline fallback is
    available, so the caller can return a clear 503 instead of silently
    dropping the job.
    """
    settings = get_settings()
    redis_client = get_redis()
    if redis_client is not None:
        from rq import Queue

        queue = Queue(settings.queue_name, connection=redis_client)
        job = queue.enqueue(
            func, *args, job_timeout=job_timeout or settings.analysis_timeout_seconds, **kwargs
        )
        return Dispatch(job_id=job.id, backend="redis-rq")

    if not settings.allow_inline_worker:
        raise RuntimeError(
            "Redis is unavailable and the in-process worker is disabled "
            "(ALLOW_INLINE_WORKER=false). Analysis cannot be scheduled."
        )

    import uuid

    job_id = uuid.uuid4().hex
    _inline_jobs[job_id] = "queued"

    def _run() -> None:
        _inline_jobs[job_id] = "running"
        try:
            func(*args, **kwargs)
            _inline_jobs[job_id] = "finished"
        except Exception as exc:  # noqa: BLE001 - recorded, never swallowed silently
            _inline_jobs[job_id] = "failed"
            logger.exception("inline_job_failed", job_id=job_id, error=str(exc)[:300])

    _get_executor().submit(_run)
    return Dispatch(job_id=job_id, backend="in-process-threads")


def job_state(job_id: str) -> str | None:
    """Best-effort state of a dispatched job, for diagnostics."""
    if job_id in _inline_jobs:
        return _inline_jobs[job_id]
    redis_client = get_redis()
    if redis_client is None:
        return None
    try:
        from rq.job import Job

        return Job.fetch(job_id, connection=redis_client).get_status()
    except Exception:  # noqa: BLE001 - job expired or Redis gone
        return None
