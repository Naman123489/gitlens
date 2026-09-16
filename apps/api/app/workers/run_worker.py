"""RQ worker entry point: ``python -m app.workers.run_worker``."""

from __future__ import annotations

import sys

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services.queue import get_redis


def main() -> int:
    settings = get_settings()
    configure_logging(settings.environment)
    logger = get_logger("repolens.worker")

    redis_client = get_redis()
    if redis_client is None:
        logger.error("worker_cannot_start", reason="Redis is not reachable", url=settings.redis_url)
        return 1

    from rq import Queue, Worker

    queue = Queue(settings.queue_name, connection=redis_client)
    logger.info("worker_starting", queue=settings.queue_name)
    Worker([queue], connection=redis_client).work(with_scheduler=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
