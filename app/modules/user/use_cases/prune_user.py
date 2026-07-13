from app.core.event_bus import IEventBus
from app.modules.user.cqrs.command import PruneUserCommand
from app.modules.user.cqrs.result import UserActionResult
from app.modules.user.domain.events import UserUpdatedEvent
from app.modules.user.domain.exception import UserNotFoundError
from app.modules.user.domain.interfaces import IUserRepository


class PruneUserUseCase:
    def __init__(self, user_repo: IUserRepository, event_bus: IEventBus):
        self.user_repo = user_repo
        self._event_bus = event_bus

    async def execute(self, command: PruneUserCommand) -> UserActionResult:
        user = await self.user_repo.get_by_uuid(command.uuid)
        if not user:
            raise UserNotFoundError(f"User with uuid {command.uuid} not found.")

        await self.user_repo.delete(command.uuid)
        await self.user_repo.commit()
        await self._event_bus.publish(UserUpdatedEvent(user_uuid=str(user.uuid), email=user.email.value))
        return UserActionResult(user=user)
