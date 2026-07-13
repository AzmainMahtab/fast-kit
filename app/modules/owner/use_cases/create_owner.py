from app.modules.owner.cqrs.command import CreateOwnerCommand
from app.modules.owner.cqrs.result import OwnerActionResult
from app.modules.owner.domain.entities import Owner
from app.modules.owner.domain.exception import OwnerAlreadyExistsError
from app.modules.owner.domain.interfaces import IOwnerRepository


class CreateOwnerUseCase:
    def __init__(self, owner_repo: IOwnerRepository):
        self.owner_repo = owner_repo

    async def execute(self, command: CreateOwnerCommand) -> OwnerActionResult:
        existing = await self.owner_repo.get_by_user_id(command.user_id)
        if existing:
            raise OwnerAlreadyExistsError(f"Owner for user {command.user_id} already exists.")

        new_owner = Owner(user_id=command.user_id, address=command.address, date_of_birth=command.date_of_birth)

        saved_owner = await self.owner_repo.create(new_owner)
        await self.owner_repo.commit()
        return OwnerActionResult(owner=saved_owner)
