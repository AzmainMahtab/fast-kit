from dataclasses import dataclass, field

from app.core.pagination import PaginationParams


@dataclass(frozen=True)
class GetCarByUuidQuery:
    uuid: str


@dataclass(frozen=True)
class ListCarsByOwnerQuery:
    owner_id: int
    pagination: PaginationParams = field(default_factory=PaginationParams)


@dataclass(frozen=True)
class ListCarsQuery:
    pagination: PaginationParams = field(default_factory=PaginationParams)
