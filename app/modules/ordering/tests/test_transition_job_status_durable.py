"""Tests for durable (outbox-aware) job status transition."""

from unittest.mock import AsyncMock

import pytest

from app.modules.ordering.cqrs.command import TransitionJobStatusCommand
from app.modules.ordering.domain.events import JobStatusChanged
from app.modules.ordering.domain.state_machine import JobStateMachine
from app.modules.ordering.tests.conftest import InMemoryJobRepository
from app.modules.ordering.use_cases.transition_job_status import TransitionJobStatusUseCase


@pytest.mark.asyncio
async def test_transition_with_session_stages_event_durably(sample_order) -> None:
    """When a session is passed, the event is staged in the outbox."""
    _order, job = await sample_order()
    event_bus = AsyncMock()
    session = AsyncMock()

    job_repo = InMemoryJobRepository()
    job_repo._jobs[job.id] = job
    use_case = TransitionJobStatusUseCase(
        job_repo=job_repo,
        event_bus=event_bus,
        session=session,
    )

    result = await use_case.execute(
        TransitionJobStatusCommand(
            job_id=job.id,
            new_status=JobStateMachine.RECEIVED_ARTWORK,
            reason="artwork received",
        )
    )

    assert result.job.job_status == JobStateMachine.RECEIVED_ARTWORK
    event_bus.publish_durable.assert_awaited_once()
    event_bus.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_transition_durable_event_payload(sample_order) -> None:
    """The staged event contains the correct domain payload."""
    _order, job = await sample_order()
    event_bus = AsyncMock()
    session = AsyncMock()

    job_repo = InMemoryJobRepository()
    job_repo._jobs[job.id] = job
    use_case = TransitionJobStatusUseCase(
        job_repo=job_repo,
        event_bus=event_bus,
        session=session,
    )

    await use_case.execute(
        TransitionJobStatusCommand(
            job_id=job.id,
            new_status=JobStateMachine.RECEIVED_ARTWORK,
            reason="artwork received",
        )
    )

    event = event_bus.publish_durable.await_args.args[0]
    assert isinstance(event, JobStatusChanged)
    assert event.job_id == job.id
    assert event.old_status == JobStateMachine.PENDING
    assert event.new_status == JobStateMachine.RECEIVED_ARTWORK
