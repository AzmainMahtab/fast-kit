from dataclasses import dataclass, field

from app.core.pagination import PaginationParams


@dataclass(frozen=True)
class GetOwnerByUuidQuery:
    uuid: str


@dataclass(frozen=True)
class GetOwnerByUserIdQuery:
    user_id: int


@dataclass(frozen=True)
class ListOwnersQuery:
    pagination: PaginationParams = field(default_factory=PaginationParams)
