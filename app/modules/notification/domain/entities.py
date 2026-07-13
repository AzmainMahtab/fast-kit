"""Notification domain entities."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Notification:
    id: int | None = None
    event_type: str = ""
    aggregate_type: str = ""
    aggregate_id: int | None = None
    message: str = ""
    created_at: datetime | None = None
