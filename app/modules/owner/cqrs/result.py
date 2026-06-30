from dataclasses import dataclass

from app.core.pagination import Page
from app.modules.owner.domain.entities import Owner


@dataclass(frozen=True)
class OwnerActionResult:
    owner: Owner


@dataclass(frozen=True)
class ListOwnersResult:
    page: Page[Owner]
