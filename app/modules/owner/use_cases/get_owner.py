from app.modules.owner.cqrs.query import GetOwnerByUserIdQuery, GetOwnerByUuidQuery
from app.modules.owner.domain.entities import Owner
from app.modules.owner.domain.exception import OwnerNotFoundError
from app.modules.owner.domain.interfaces import IOwnerRepository


class GetOwnerUseCase:
    def __init__(self, owner_repo: IOwnerRepository):
        self.owner_repo = owner_repo

    async def by_uuid(self, query: GetOwnerByUuidQuery) -> Owner:
        owner = await self.owner_repo.get_by_uuid(query.uuid)
        if not owner:
            raise OwnerNotFoundError(f"Owner with uuid {query.uuid} not found.")
        return owner

    async def by_user_id(self, query: GetOwnerByUserIdQuery) -> Owner:
        owner = await self.owner_repo.get_by_user_id(query.user_id)
        if not owner:
            raise OwnerNotFoundError(f"Owner for user {query.user_id} not found.")
        return owner
