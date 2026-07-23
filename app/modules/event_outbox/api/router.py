"""Admin API for event store audit and dead-letter replay.

Endpoints are protected by the ``admin:access`` RBAC permission and are
intended for operations staff to inspect and recover events.
"""

import uuid
from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.event_bus import IEventBus
from app.core.event_serializer import EventSerializationError, SerializedEvent, deserialize, serialize
from app.core.nats_bus import _subject_for_event_type
from app.core.response import SuccessEnvelope
from app.modules.event_outbox.api.dependencies import get_event_bus, get_outbox_repo, require_admin_access
from app.modules.event_outbox.api.schemas import (
    DeadLetterDetail,
    DeadLetterListItem,
    EventStoreDetail,
    EventStoreListItem,
    ReplayResponse,
    ResolveResponse,
)
from app.modules.event_outbox.domain.interfaces import IOutboxRepository

router = APIRouter(prefix="/admin", tags=["Event Operations"], dependencies=[Depends(require_admin_access)])


@router.get("/events", response_model=SuccessEnvelope[list[EventStoreListItem]])
async def list_events(
    event_type: str | None = None,
    aggregate_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
    repo: IOutboxRepository = Depends(get_outbox_repo),
) -> SuccessEnvelope[list[EventStoreListItem]]:
    rows = await repo.list_event_store(
        session,
        event_type=event_type,
        aggregate_id=aggregate_id,
        limit=limit,
        offset=offset,
    )
    return SuccessEnvelope(
        statusCode=200,
        data=[
            EventStoreListItem(
                id=row.id,
                event_type=row.event_type,
                event_class_path=row.event_class_path,
                aggregate_id=row.aggregate_id,
                published_at=row.published_at,
            )
            for row in rows
        ],
    )


@router.get("/events/{event_id}", response_model=SuccessEnvelope[EventStoreDetail])
async def get_event(
    event_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    repo: IOutboxRepository = Depends(get_outbox_repo),
) -> SuccessEnvelope[EventStoreDetail]:
    row = await repo.get_event_store(session, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")

    return SuccessEnvelope(
        statusCode=200,
        data=EventStoreDetail(
            id=row.id,
            event_type=row.event_type,
            event_class_path=row.event_class_path,
            aggregate_id=row.aggregate_id,
            published_at=row.published_at,
            payload=row.payload,
            correlation_id=row.correlation_id,
        ),
    )


@router.post("/events/{event_id}/replay", response_model=SuccessEnvelope[ReplayResponse])
async def replay_event(
    event_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    repo: IOutboxRepository = Depends(get_outbox_repo),
    event_bus: IEventBus = Depends(get_event_bus),
) -> SuccessEnvelope[ReplayResponse]:
    row = await repo.get_event_store(session, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")

    try:
        event = deserialize(SerializedEvent(event_class=row.event_class_path, payload=row.payload))
        serialize(event)
    except EventSerializationError as exc:
        raise HTTPException(status_code=422, detail=f"Cannot replay event: {exc}") from exc

    subject = _subject_for_event_type(type(event))
    serialized = SerializedEvent(event_class=row.event_class_path, payload=row.payload)
    await event_bus.publish_raw(subject, serialized.to_json())

    return SuccessEnvelope(
        statusCode=200,
        data=ReplayResponse(republished=True, subject=subject),
    )


@router.get("/dead-letter-events", response_model=SuccessEnvelope[list[DeadLetterListItem]])
async def list_dead_letter_events(
    resolved: bool | None = None,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
    repo: IOutboxRepository = Depends(get_outbox_repo),
) -> SuccessEnvelope[list[DeadLetterListItem]]:
    rows = await repo.list_dead_letter(session, resolved=resolved, limit=limit, offset=offset)
    return SuccessEnvelope(
        statusCode=200,
        data=[
            DeadLetterListItem(
                id=row.id,
                event_class_path=row.event_class_path,
                subject=row.subject,
                error_message=row.error_message,
                attempts=row.attempts,
                created_at=cast(datetime, row.created_at),
                resolved_at=row.resolved_at,
            )
            for row in rows
        ],
    )


@router.get("/dead-letter-events/{dead_letter_id}", response_model=SuccessEnvelope[DeadLetterDetail])
async def get_dead_letter_event(
    dead_letter_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    repo: IOutboxRepository = Depends(get_outbox_repo),
) -> SuccessEnvelope[DeadLetterDetail]:
    row = await repo.get_dead_letter(session, dead_letter_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Dead letter event not found")

    return SuccessEnvelope(
        statusCode=200,
        data=DeadLetterDetail(
            id=row.id,
            event_class_path=row.event_class_path,
            subject=row.subject,
            error_message=row.error_message,
            attempts=row.attempts,
            created_at=cast(datetime, row.created_at),
            resolved_at=row.resolved_at,
            payload=row.payload,
        ),
    )


@router.post("/dead-letter-events/{dead_letter_id}/replay", response_model=SuccessEnvelope[ReplayResponse])
async def replay_dead_letter_event(
    dead_letter_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    repo: IOutboxRepository = Depends(get_outbox_repo),
    event_bus: IEventBus = Depends(get_event_bus),
) -> SuccessEnvelope[ReplayResponse]:
    row = await repo.get_dead_letter(session, dead_letter_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Dead letter event not found")

    try:
        event = deserialize(SerializedEvent(event_class=row.event_class_path, payload=row.payload))
        serialize(event)
    except EventSerializationError as exc:
        raise HTTPException(status_code=422, detail=f"Cannot replay event: {exc}") from exc

    subject = _subject_for_event_type(type(event))
    serialized = SerializedEvent(event_class=row.event_class_path, payload=row.payload)
    await event_bus.publish_raw(subject, serialized.to_json())

    resolved = await repo.mark_dead_letter_resolved(session, dead_letter_id)
    await session.commit()
    if resolved is None:
        raise HTTPException(status_code=404, detail="Dead letter event not found")

    return SuccessEnvelope(
        statusCode=200,
        data=ReplayResponse(republished=True, subject=row.subject),
    )


@router.post("/dead-letter-events/{dead_letter_id}/resolve", response_model=SuccessEnvelope[ResolveResponse])
async def resolve_dead_letter_event(
    dead_letter_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    repo: IOutboxRepository = Depends(get_outbox_repo),
) -> SuccessEnvelope[ResolveResponse]:
    resolved = await repo.mark_dead_letter_resolved(session, dead_letter_id)
    await session.commit()
    if resolved is None:
        raise HTTPException(status_code=404, detail="Dead letter event not found")

    return SuccessEnvelope(
        statusCode=200,
        data=ResolveResponse(resolved=True),
    )
