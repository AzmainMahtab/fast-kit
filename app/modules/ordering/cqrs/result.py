"""Ordering result DTOs."""

from dataclasses import dataclass

from app.modules.ordering.domain.entities import Job, Order


@dataclass
class JobResult:
    job: Job


@dataclass
class OrderResult:
    order: Order
