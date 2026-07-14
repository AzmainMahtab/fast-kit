"""Ordering repository ports."""

from abc import ABC, abstractmethod

from app.core.pagination import PaginationParams
from app.modules.ordering.domain.entities import Job, Order


class IOrderRepository(ABC):
    """Port for order persistence."""

    @abstractmethod
    async def get_by_id(self, order_id: int) -> Order | None: ...

    @abstractmethod
    async def list_all(
        self, pagination: PaginationParams = PaginationParams()
    ) -> tuple[list[Order], int]: ...

    @abstractmethod
    async def create(self, order: Order) -> Order: ...

    @abstractmethod
    async def commit(self) -> None: ...


class IJobRepository(ABC):
    """Port for job persistence."""

    @abstractmethod
    async def get_by_id(self, job_id: int) -> Job | None: ...

    @abstractmethod
    async def create(self, job: Job) -> Job: ...

    @abstractmethod
    async def update(self, job: Job) -> Job: ...

    @abstractmethod
    async def commit(self) -> None: ...
