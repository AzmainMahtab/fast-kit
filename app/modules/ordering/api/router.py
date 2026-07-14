"""Ordering API router."""

from fastapi import APIRouter, Depends

from app.core.response import SuccessEnvelope
from app.modules.ordering.api.dependencies import (
    get_create_order_use_case,
    get_get_order_use_case,
    get_list_orders_use_case,
    get_transition_job_status_use_case,
)
from app.modules.ordering.api.schemas import (
    JobResponse,
    JobStatusTransitionSchema,
    OrderCreateSchema,
    OrderResponse,
)
from app.modules.ordering.cqrs.command import (
    CreateOrderCommand,
    TransitionJobStatusCommand,
)
from app.modules.ordering.use_cases.create_order import CreateOrderUseCase
from app.modules.ordering.use_cases.get_order import GetOrderUseCase
from app.modules.ordering.use_cases.list_orders import ListOrdersUseCase
from app.modules.ordering.use_cases.transition_job_status import (
    TransitionJobStatusUseCase,
)

router = APIRouter(prefix="/orders", tags=["Ordering"])


@router.post("", response_model=SuccessEnvelope[OrderResponse])
async def create_order(
    payload: OrderCreateSchema,
    use_case: CreateOrderUseCase = Depends(get_create_order_use_case),
) -> SuccessEnvelope[OrderResponse]:
    command = CreateOrderCommand(
        user_id=payload.user_id,
        order_number=payload.order_number,
        jobs=[{"job_id": j.job_id} for j in payload.jobs],
    )
    result = await use_case.execute(command)
    return SuccessEnvelope(
        statusCode=201,
        data=OrderResponse.from_domain(result.order),
    )


@router.get("", response_model=SuccessEnvelope[list[OrderResponse]])
async def list_orders(
    use_case: ListOrdersUseCase = Depends(get_list_orders_use_case),
) -> SuccessEnvelope[list[OrderResponse]]:
    page = await use_case.execute()
    return SuccessEnvelope(
        statusCode=200,
        data=[OrderResponse.from_domain(r.order) for r in page.items],
        meta={"total": page.total, "page": page.page, "page_size": page.page_size},
    )


@router.get("/{order_id}", response_model=SuccessEnvelope[OrderResponse])
async def get_order(
    order_id: int,
    use_case: GetOrderUseCase = Depends(get_get_order_use_case),
) -> SuccessEnvelope[OrderResponse]:
    result = await use_case.execute(order_id)
    return SuccessEnvelope(
        statusCode=200,
        data=OrderResponse.from_domain(result.order),
    )


@router.post("/jobs/{job_id}/transition", response_model=SuccessEnvelope[JobResponse])
async def transition_job_status(
    job_id: int,
    payload: JobStatusTransitionSchema,
    use_case: TransitionJobStatusUseCase = Depends(get_transition_job_status_use_case),
) -> SuccessEnvelope[JobResponse]:
    command = TransitionJobStatusCommand(
        job_id=job_id,
        new_status=payload.new_status,
        reason=payload.reason,
    )
    result = await use_case.execute(command)
    return SuccessEnvelope(
        statusCode=200,
        data=JobResponse.from_domain(result.job),
    )
