"""Dependency providers for event store and dead-letter admin APIs."""

from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.event_bus import IEventBus
from app.modules.auth.api.dependencies import require_permission
from app.modules.event_outbox.domain.interfaces import IOutboxRepository
from app.modules.event_outbox.infrastructure.persistence.repository import SQLAlchemyOutboxRepository


def get_event_bus(request: Request) -> IEventBus:
    return cast(IEventBus, request.app.state.event_bus)


async def get_outbox_repo(db: AsyncSession = Depends(get_db)) -> IOutboxRepository:
    return SQLAlchemyOutboxRepository()


require_admin_access = require_permission("admin:access")
