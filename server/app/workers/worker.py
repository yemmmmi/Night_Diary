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
    from app.infrastructure.redis_client import _redis_client, is_redis_available

    if not is_redis_available():
        logger.error("Redis is not available. Workers require Redis.")
        sys.exit(1)
    from rq import Worker

    worker = Worker(["default"], connection=_redis_client)
    logger.info("Starting RQ worker on queue 'default'...")
    worker.work()


if __name__ == "__main__":
    main()
