from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.event_bus import IEventBus
from app.modules.user.domain.interfaces import IUserRepository
from app.modules.user.infrastructure.persistence.repository import SQLAlchemyUserRepository
from app.modules.user.use_cases.delete_user import DeleteUserUseCase
from app.modules.user.use_cases.get_user import GetUserUseCase
from app.modules.user.use_cases.list_users import ListUsersUseCase
from app.modules.user.use_cases.prune_user import PruneUserUseCase
from app.modules.user.use_cases.register_user import RegisterUserUseCase
from app.modules.user.use_cases.restore_user import RestoreUserUseCase
from app.modules.user.use_cases.update_user_status import UpdateUserStatusUseCase


async def get_user_repo(db: AsyncSession = Depends(get_db)) -> IUserRepository:
    return SQLAlchemyUserRepository(db)


def get_event_bus(request: Request) -> IEventBus:
    return cast(IEventBus, request.app.state.event_bus)


async def get_register_use_case(
    repo: IUserRepository = Depends(get_user_repo), event_bus: IEventBus = Depends(get_event_bus)
) -> RegisterUserUseCase:
    return RegisterUserUseCase(user_repo=repo, event_bus=event_bus)


async def get_update_status_use_case(
    repo: IUserRepository = Depends(get_user_repo), event_bus: IEventBus = Depends(get_event_bus)
) -> UpdateUserStatusUseCase:
    return UpdateUserStatusUseCase(user_repo=repo, event_bus=event_bus)


async def get_delete_use_case(
    repo: IUserRepository = Depends(get_user_repo), event_bus: IEventBus = Depends(get_event_bus)
) -> DeleteUserUseCase:
    return DeleteUserUseCase(user_repo=repo, event_bus=event_bus)


async def get_prune_use_case(
    repo: IUserRepository = Depends(get_user_repo), event_bus: IEventBus = Depends(get_event_bus)
) -> PruneUserUseCase:
    return PruneUserUseCase(user_repo=repo, event_bus=event_bus)


async def get_user_query_use_case(repo: IUserRepository = Depends(get_user_repo)) -> GetUserUseCase:
    return GetUserUseCase(user_repo=repo)


async def get_list_users_use_case(repo: IUserRepository = Depends(get_user_repo)) -> ListUsersUseCase:
    return ListUsersUseCase(user_repo=repo)


async def get_restore_user_use_case(
    repo: IUserRepository = Depends(get_user_repo), event_bus: IEventBus = Depends(get_event_bus)
) -> RestoreUserUseCase:
    return RestoreUserUseCase(user_repo=repo, event_bus=event_bus)
