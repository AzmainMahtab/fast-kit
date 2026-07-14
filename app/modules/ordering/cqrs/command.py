"""Ordering command DTOs."""

from dataclasses import dataclass


@dataclass
class CreateOrderCommand:
    user_id: int
    order_number: str
    jobs: list[dict]


@dataclass
class TransitionJobStatusCommand:
    job_id: int
    new_status: str
    user_id: int | None = None
    reason: str | None = None
