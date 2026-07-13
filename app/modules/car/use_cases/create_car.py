from app.modules.car.cqrs.command import CreateCarCommand
from app.modules.car.cqrs.result import CarActionResult
from app.modules.car.domain.entities import Car
from app.modules.car.domain.interfaces import ICarRepository


class CreateCarUseCase:
    def __init__(self, car_repo: ICarRepository):
        self.car_repo = car_repo

    async def execute(self, command: CreateCarCommand) -> CarActionResult:
        new_car = Car(
            owner_id=command.owner_id,
            make=command.make,
            model=command.model,
            year=command.year,
            color=command.color,
            license_plate=command.license_plate,
        )

        saved_car = await self.car_repo.create(new_car)
        await self.car_repo.commit()
        return CarActionResult(car=saved_car)
