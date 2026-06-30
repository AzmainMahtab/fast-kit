from app.modules.car.cqrs.query import GetCarByUuidQuery
from app.modules.car.domain.entities import Car
from app.modules.car.domain.exception import CarNotFoundError
from app.modules.car.domain.interfaces import ICarRepository


class GetCarUseCase:
    def __init__(self, car_repo: ICarRepository):
        self.car_repo = car_repo

    async def by_uuid(self, query: GetCarByUuidQuery) -> Car:
        car = await self.car_repo.get_by_uuid(query.uuid)
        if not car:
            raise CarNotFoundError(f"Car with uuid {query.uuid} not found.")
        return car
