"""Ordering domain events."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OrderCreated:
    """Fired when a new order is created."""

    order_id: int
    order_number: str
    user_id: int
    job_ids: list[str]


@dataclass(frozen=True)
class JobStatusChanged:
    """Fired when a job status is transitioned."""

    job_id: int
    job_uuid: str
    old_status: str
    new_status: str
    user_id: int | None
    reason: str
