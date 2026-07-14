import pytest

from app.core.event_bus import InMemoryEventBus
from app.modules.ordering.domain.entities import Job, Order
from app.modules.ordering.domain.interfaces import IJobRepository, IOrderRepository
from app.modules.ordering.domain.state_machine import JobStateMachine


class InMemoryOrderRepository(IOrderRepository):
    def __init__(self):
        self._orders: dict[int, Order] = {}
        self._next_id = 1

    async def commit(self) -> None:
        return

    async def get_by_id(self, order_id: int) -> Order | None:
        return self._orders.get(order_id)

    async def list_all(self, pagination=None):
        return list(self._orders.values()), len(self._orders)

    async def create(self, order: Order) -> Order:
        order.id = self._next_id
        self._next_id += 1
        self._orders[order.id] = order
        return order


class InMemoryJobRepository(IJobRepository):
    def __init__(self):
        self._jobs: dict[int, Job] = {}
        self._next_id = 1

    async def commit(self) -> None:
        return

    async def get_by_id(self, job_id: int) -> Job | None:
        return self._jobs.get(job_id)

    async def create(self, job: Job) -> Job:
        job.id = self._next_id
        self._next_id += 1
        self._jobs[job.id] = job
        return job

    async def update(self, job: Job) -> Job:
        self._jobs[job.id] = job
        return job


@pytest.fixture
def order_repo():
    return InMemoryOrderRepository()


@pytest.fixture
def job_repo():
    return InMemoryJobRepository()


@pytest.fixture
def event_bus():
    return InMemoryEventBus()


@pytest.fixture
def sample_order(order_repo, job_repo):
    order = Order(order_number="ORD-001", user_id=1)

    async def _create():
        saved = await order_repo.create(order)
        job = Job(
            order_id=saved.id,
            job_id="JOB-001",
            job_status=JobStateMachine.PENDING,
            file_editable=True,
        )
        saved_job = await job_repo.create(job)
        saved.jobs = [saved_job]
        return saved, saved_job

    return _create
