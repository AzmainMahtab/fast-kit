from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.owner.domain.interfaces import IOwnerRepository
from app.modules.owner.infrastructure.persistence.repository import SQLAlchemyOwnerRepository
from app.modules.owner.use_cases.create_owner import CreateOwnerUseCase
from app.modules.owner.use_cases.get_owner import GetOwnerUseCase
from app.modules.owner.use_cases.list_owners import ListOwnersUseCase


async def get_owner_repo(db: AsyncSession = Depends(get_db)) -> IOwnerRepository:
    return SQLAlchemyOwnerRepository(db)


async def get_create_owner_use_case(repo: IOwnerRepository = Depends(get_owner_repo)) -> CreateOwnerUseCase:
    return CreateOwnerUseCase(owner_repo=repo)


async def get_get_owner_use_case(repo: IOwnerRepository = Depends(get_owner_repo)) -> GetOwnerUseCase:
    return GetOwnerUseCase(owner_repo=repo)


async def get_list_owners_use_case(repo: IOwnerRepository = Depends(get_owner_repo)) -> ListOwnersUseCase:
    return ListOwnersUseCase(owner_repo=repo)
