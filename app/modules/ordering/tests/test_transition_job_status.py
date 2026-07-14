import pytest

from app.modules.ordering.cqrs.command import TransitionJobStatusCommand
from app.modules.ordering.domain.events import JobStatusChanged
from app.modules.ordering.domain.exceptions import InvalidStatusTransitionError
from app.modules.ordering.domain.state_machine import JobStateMachine
from app.modules.ordering.use_cases.transition_job_status import (
    TransitionJobStatusUseCase,
)


@pytest.mark.asyncio
async def test_valid_transition(job_repo, event_bus, sample_order):
    order, job = await sample_order()
    use_case = TransitionJobStatusUseCase(
        job_repo=job_repo,
        event_bus=event_bus,
    )

    received = []

    async def handler(event):
        received.append(event)

    event_bus.subscribe(JobStatusChanged, handler)

    result = await use_case.execute(
        TransitionJobStatusCommand(
            job_id=job.id,
            new_status=JobStateMachine.RECEIVED_ARTWORK,
            user_id=1,
            reason="Artwork received",
        )
    )

    assert result.job.job_status == JobStateMachine.RECEIVED_ARTWORK
    assert result.job.file_editable is False
    assert len(received) == 1
    assert received[0].new_status == JobStateMachine.RECEIVED_ARTWORK


@pytest.mark.asyncio
async def test_invalid_transition_raises(job_repo, event_bus, sample_order):
    order, job = await sample_order()
    use_case = TransitionJobStatusUseCase(
        job_repo=job_repo,
        event_bus=event_bus,
    )

    with pytest.raises(InvalidStatusTransitionError):
        await use_case.execute(
            TransitionJobStatusCommand(
                job_id=job.id,
                new_status=JobStateMachine.BATCHED,
            )
        )
