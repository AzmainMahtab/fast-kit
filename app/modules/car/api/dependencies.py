from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.car.domain.interfaces import ICarRepository
from app.modules.car.infrastructure.persistence.repository import SQLAlchemyCarRepository
from app.modules.car.use_cases.create_car import CreateCarUseCase
from app.modules.car.use_cases.get_car import GetCarUseCase
from app.modules.car.use_cases.list_cars import ListCarsUseCase


async def get_car_repo(db: AsyncSession = Depends(get_db)) -> ICarRepository:
    return SQLAlchemyCarRepository(db)


async def get_create_car_use_case(repo: ICarRepository = Depends(get_car_repo)) -> CreateCarUseCase:
    return CreateCarUseCase(car_repo=repo)


async def get_get_car_use_case(repo: ICarRepository = Depends(get_car_repo)) -> GetCarUseCase:
    return GetCarUseCase(car_repo=repo)


async def get_list_cars_use_case(repo: ICarRepository = Depends(get_car_repo)) -> ListCarsUseCase:
    return ListCarsUseCase(car_repo=repo)
