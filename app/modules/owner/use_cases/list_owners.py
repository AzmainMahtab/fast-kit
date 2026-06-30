from app.core.pagination import Page
from app.modules.owner.cqrs.query import ListOwnersQuery
from app.modules.owner.cqrs.result import ListOwnersResult
from app.modules.owner.domain.interfaces import IOwnerRepository


class ListOwnersUseCase:
    def __init__(self, owner_repo: IOwnerRepository):
        self.owner_repo = owner_repo

    async def execute(self, query: ListOwnersQuery) -> ListOwnersResult:
        owners, total = await self.owner_repo.list_all(pagination=query.pagination)
        page = Page(items=owners, total=total, offset=query.pagination.offset, limit=query.pagination.limit)
        return ListOwnersResult(page=page)
