"""List orders use case."""

from app.core.pagination import Page, PaginationParams
from app.modules.ordering.cqrs.result import OrderResult
from app.modules.ordering.domain.interfaces import IOrderRepository


class ListOrdersUseCase:
    """Read a paginated list of orders."""

    def __init__(self, order_repo: IOrderRepository):
        self.order_repo = order_repo

    async def execute(
        self, pagination: PaginationParams = PaginationParams()
    ) -> Page[OrderResult]:
        orders, total = await self.order_repo.list_all(pagination)
        return Page(
            items=[OrderResult(order=o) for o in orders],
            total=total,
            offset=pagination.offset,
            limit=pagination.limit,
        )
