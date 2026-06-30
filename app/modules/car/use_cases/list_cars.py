from app.core.pagination import Page
from app.modules.car.cqrs.query import ListCarsByOwnerQuery, ListCarsQuery
from app.modules.car.cqrs.result import ListCarsResult
from app.modules.car.domain.interfaces import ICarRepository


class ListCarsUseCase:
    def __init__(self, car_repo: ICarRepository):
        self.car_repo = car_repo

    async def by_owner(self, query: ListCarsByOwnerQuery) -> ListCarsResult:
        cars, total = await self.car_repo.list_by_owner(owner_id=query.owner_id, pagination=query.pagination)
        page = Page(items=cars, total=total, offset=query.pagination.offset, limit=query.pagination.limit)
        return ListCarsResult(page=page)

    async def all_cars(self, query: ListCarsQuery) -> ListCarsResult:
        cars, total = await self.car_repo.list_all(pagination=query.pagination)
        page = Page(items=cars, total=total, offset=query.pagination.offset, limit=query.pagination.limit)
        return ListCarsResult(page=page)
