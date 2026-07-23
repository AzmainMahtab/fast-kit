"""Pydantic schemas for event store and dead-letter admin APIs."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EventStoreListItem(BaseModel):
    id: uuid.UUID
    event_type: str
    event_class_path: str
    aggregate_id: str | None
    published_at: datetime


class EventStoreDetail(EventStoreListItem):
    payload: dict[str, Any]
    correlation_id: str | None


class DeadLetterListItem(BaseModel):
    id: uuid.UUID
    event_class_path: str
    subject: str
    error_message: str
    attempts: int
    created_at: datetime
    resolved_at: datetime | None


class DeadLetterDetail(DeadLetterListItem):
    payload: dict[str, Any]


class ReplayResponse(BaseModel):
    republished: bool
    subject: str


class ResolveResponse(BaseModel):
    resolved: bool
