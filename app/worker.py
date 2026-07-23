"""Background worker that consumes domain events from NATS JetStream.

Usage:
    uv run python -m app.worker

The worker connects to NATS, subscribes to all handlers registered by the
application's event wiring function, and runs forever.
"""

import asyncio
import logging

from app.core.database import AsyncSessionLocal
from app.core.event_bus import IEventBus
from app.core.nats_bus import NatsEventBus
from app.core.settings import settings
from app.modules.notification.infrastructure.event_handlers import (
    create_session_repository_factory,
    subscribe_notification_handlers,
)

logger = logging.getLogger(__name__)


async def wire_handlers(bus: IEventBus) -> None:
    """Subscribe all domain-event handlers.

    This mirrors the wiring in ``main.py`` lifespan but is intended for the
    worker process. Any module that reacts to events should be wired here.
    """
    subscribe_notification_handlers(
        bus,
        create_session_repository_factory(AsyncSessionLocal),
    )


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if not settings.NATS_ENABLED:
        logger.error("NATS_ENABLED is false; the worker requires NATS JetStream.")
        return

    bus = NatsEventBus()
    await bus.connect()
    await wire_handlers(bus)
    logger.info("Worker started; waiting for events on %s", settings.NATS_URL)

    try:
        await asyncio.gather(
            bus.start_consuming(),
            bus.start_dlq_consuming(),
        )
    except asyncio.CancelledError:
        logger.info("Worker shutting down...")
    finally:
        await bus.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user.")
