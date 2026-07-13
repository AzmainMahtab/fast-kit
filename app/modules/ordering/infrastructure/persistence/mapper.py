"""Map between ordering domain entities and SQLAlchemy models."""

from app.modules.ordering.domain.entities import Job, Order
from app.modules.ordering.infrastructure.persistence.models import JobModel, OrderModel


def map_job_to_domain(model: JobModel) -> Job:
    return Job(
        id=model.id,
        job_id=model.job_id,
        job_status=model.job_status,
        file_editable=model.file_editable,
        order_id=model.order_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def map_job_to_model(entity: Job, existing: JobModel | None = None) -> JobModel:
    if existing is not None:
        existing.job_status = entity.job_status
        existing.file_editable = entity.file_editable
        return existing
    return JobModel(
        id=entity.id,
        order_id=entity.order_id,
        job_id=entity.job_id,
        job_status=entity.job_status,
        file_editable=entity.file_editable,
    )


def map_order_to_domain(model: OrderModel) -> Order:
    return Order(
        id=model.id,
        order_number=model.order_number,
        user_id=model.user_id,
        status=model.status,
        jobs=[map_job_to_domain(j) for j in model.jobs],
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def map_order_to_model(entity: Order) -> OrderModel:
    return OrderModel(
        id=entity.id,
        order_number=entity.order_number,
        user_id=entity.user_id,
        status=entity.status,
        jobs=[map_job_to_model(j) for j in entity.jobs],
    )
