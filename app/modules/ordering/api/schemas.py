"""Ordering Pydantic schemas."""

from pydantic import BaseModel, Field

from app.modules.ordering.domain.state_machine import JobStateMachine


class JobInputSchema(BaseModel):
    job_id: str = Field(..., max_length=32)


class OrderCreateSchema(BaseModel):
    user_id: int = Field(..., gt=0)
    order_number: str = Field(..., max_length=32)
    jobs: list[JobInputSchema] = Field(..., min_length=1)


class JobStatusTransitionSchema(BaseModel):
    new_status: str = Field(..., max_length=32)
    reason: str | None = Field(None, max_length=255)


class JobResponse(BaseModel):
    id: int
    job_id: str
    job_status: str
    file_editable: bool
    order_id: int | None

    @classmethod
    def from_domain(cls, job) -> "JobResponse":
        return cls(
            id=job.id,
            job_id=job.job_id,
            job_status=job.job_status,
            file_editable=job.file_editable,
            order_id=job.order_id,
        )


class OrderResponse(BaseModel):
    id: int
    order_number: str
    user_id: int
    status: str
    jobs: list[JobResponse]

    @classmethod
    def from_domain(cls, order) -> "OrderResponse":
        return cls(
            id=order.id,
            order_number=order.order_number,
            user_id=order.user_id,
            status=order.status,
            jobs=[JobResponse.from_domain(j) for j in order.jobs],
        )
