"""Scheduled task publisher that emits domain events to NATS JetStream.

Usage:
    uv run python -m app.scheduler

The scheduler runs a simple loop and publishes a
``JobStatusCheckScheduled`` event every ``SCHEDULER_INTERVAL_SECONDS``.
Workers consume these events and react to them.
"""

import asyncio
import logging
from datetime import UTC, datetime

from app.core.nats_bus import NatsEventBus
from app.core.settings import settings
from app.modules.ordering.domain.events import JobStatusCheckScheduled

logger = logging.getLogger(__name__)

SCHEDULER_INTERVAL_SECONDS = 60


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if not settings.NATS_ENABLED:
        logger.error("NATS_ENABLED is false; the scheduler requires NATS JetStream.")
        return

    bus = NatsEventBus()
    await bus.connect()
    logger.info("Scheduler started; publishing every %s seconds", SCHEDULER_INTERVAL_SECONDS)

    try:
        while True:
            event = JobStatusCheckScheduled(
                checked_at=datetime.now(UTC).isoformat(),
            )
            await bus.publish(event)
            logger.info("Published scheduled event: %s", event.checked_at)
            await asyncio.sleep(SCHEDULER_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        logger.info("Scheduler shutting down...")
    finally:
        await bus.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user.")
