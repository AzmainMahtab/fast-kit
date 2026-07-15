"""Ordering command DTOs."""

from dataclasses import dataclass
from uuid import UUID


@dataclass
class CreateOrderCommand:
    user_id: UUID | None
    order_number: str
    jobs: list[dict]


@dataclass
class TransitionJobStatusCommand:
    job_id: int
    new_status: str
    user_id: UUID | None = None
    reason: str | None = None
