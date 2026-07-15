"""Ordering domain entities."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.modules.ordering.domain.state_machine import JobStateMachine


@dataclass
class Job:
    id: int | None = None
    job_id: str = ""
    job_status: str = JobStateMachine.PENDING
    file_editable: bool = True
    order_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def transition_to(self, new_status: str) -> None:
        JobStateMachine.assert_transition(self.job_status, new_status)
        self.job_status = new_status
        self.file_editable = JobStateMachine.is_file_editable(new_status)


@dataclass
class Order:
    id: int | None = None
    order_number: str = ""
    user_id: UUID | None = None
    status: str = "PENDING"
    jobs: list[Job] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
