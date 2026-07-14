"""Transition job status use case."""

from app.core.event_bus import IEventBus
from app.modules.ordering.cqrs.command import TransitionJobStatusCommand
from app.modules.ordering.cqrs.result import JobResult
from app.modules.ordering.domain.events import JobStatusChanged
from app.modules.ordering.domain.exceptions import JobNotFoundError
from app.modules.ordering.domain.interfaces import IJobRepository


class TransitionJobStatusUseCase:
    """Transition a job through the state machine and publish a domain event."""

    def __init__(
        self,
        job_repo: IJobRepository,
        event_bus: IEventBus,
    ):
        self.job_repo = job_repo
        self.event_bus = event_bus

    async def execute(self, command: TransitionJobStatusCommand) -> JobResult:
        job = await self.job_repo.get_by_id(command.job_id)
        if job is None:
            raise JobNotFoundError()

        old_status = job.job_status
        job.transition_to(command.new_status)
        updated_job = await self.job_repo.update(job)
        await self.job_repo.commit()

        await self.event_bus.publish(
            JobStatusChanged(
                job_id=updated_job.id,
                job_uuid=updated_job.job_id,
                old_status=old_status,
                new_status=updated_job.job_status,
                user_id=command.user_id,
                reason=command.reason or f"Status: {old_status} -> {updated_job.job_status}",
            )
        )

        return JobResult(job=updated_job)
