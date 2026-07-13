"""Get order use case."""

from app.modules.ordering.cqrs.result import OrderResult
from app.modules.ordering.domain.exceptions import OrderNotFoundError
from app.modules.ordering.domain.interfaces import IOrderRepository


class GetOrderUseCase:
    """Read a single order by id."""

    def __init__(self, order_repo: IOrderRepository):
        self.order_repo = order_repo

    async def execute(self, order_id: int) -> OrderResult:
        order = await self.order_repo.get_by_id(order_id)
        if order is None:
            raise OrderNotFoundError()
        return OrderResult(order=order)
