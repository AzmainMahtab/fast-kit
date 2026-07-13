from datetime import UTC, datetime

from app.core.event_bus import IEventBus
from app.modules.user.cqrs.command import DeleteUserCommand
from app.modules.user.cqrs.result import UserActionResult
from app.modules.user.domain.events import UserUpdatedEvent
from app.modules.user.domain.exception import UserNotFoundError
from app.modules.user.domain.interfaces import IUserRepository


class DeleteUserUseCase:
    def __init__(self, user_repo: IUserRepository, event_bus: IEventBus):
        self.user_repo = user_repo
        self._event_bus = event_bus

    async def execute(self, command: DeleteUserCommand) -> UserActionResult:
        user = await self.user_repo.get_by_uuid(command.uuid)
        if not user:
            raise UserNotFoundError(f"User with uuid {command.uuid} not found.")

        deleted_at = datetime.now(UTC)
        user.soft_delete(deleted_at)
        updated_user = await self.user_repo.update(user)
        await self.user_repo.commit()
        await self._event_bus.publish(
            UserUpdatedEvent(user_uuid=str(updated_user.uuid), email=updated_user.email.value)
        )
        return UserActionResult(user=updated_user)
