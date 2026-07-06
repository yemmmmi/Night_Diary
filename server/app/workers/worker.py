"""RQ worker entry point — run with: python -m app.workers.worker

Starts an RQ worker that processes background tasks (entity extraction,
consolidation, night talk generation, etc.).
"""
from __future__ import annotations

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    from app.infrastructure.redis_client import is_redis_available, _redis_client
    if not is_redis_available():
        logger.error("Redis is not available. Workers require Redis.")
        sys.exit(1)
    from rq import Connection, Worker
    with Connection(_redis_client):
        worker = Worker(["default"])
        logger.info("Starting RQ worker on queue 'default'...")
        worker.work()


if __name__ == "__main__":
    main()
