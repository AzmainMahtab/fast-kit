"""Tests for the durable unit of work context manager."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.database import durable_unit_of_work
from app.core.event_bus import InMemoryEventBus


def _create_mock_session() -> AsyncMock:
    """Return an AsyncMock that can also be used as an async context manager."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


@pytest.mark.asyncio
async def test_durable_unit_of_work_commits_and_relays() -> None:
    """The context manager commits the business session and relays via the event bus."""
    event_bus = InMemoryEventBus()
    relay_spy = AsyncMock()
    event_bus.relay_pending_outbox = relay_spy

    business_session = _create_mock_session()
    relay_session = _create_mock_session()
    sessions = [business_session, relay_session]
    call_count = 0

    def mock_session_maker():
        nonlocal call_count
        session = sessions[call_count]
        call_count += 1
        return session

    with patch("app.core.database.AsyncSessionLocal", mock_session_maker):
        async with durable_unit_of_work(event_bus) as session:
            assert session is business_session

    business_session.commit.assert_awaited_once()
    business_session.close.assert_awaited_once()
    relay_spy.assert_awaited_once_with(relay_session)
    relay_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_durable_unit_of_work_rolls_back_on_business_error() -> None:
    """If the caller raises, the business session is rolled back and relay is skipped."""
    event_bus = InMemoryEventBus()
    relay_spy = AsyncMock()
    event_bus.relay_pending_outbox = relay_spy

    business_session = _create_mock_session()

    def mock_session_maker():
        return business_session

    with patch("app.core.database.AsyncSessionLocal", mock_session_maker), pytest.raises(RuntimeError, match="boom"):
        async with durable_unit_of_work(event_bus):
            raise RuntimeError("boom")

    business_session.rollback.assert_awaited_once()
    business_session.commit.assert_not_awaited()
    relay_spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_durable_unit_of_work_swallows_relay_error() -> None:
    """A relay failure does not fail the already-committed business transaction."""
    event_bus = InMemoryEventBus()
    relay_spy = AsyncMock(side_effect=ConnectionError("nats down"))
    event_bus.relay_pending_outbox = relay_spy

    business_session = _create_mock_session()
    relay_session = _create_mock_session()
    sessions = [business_session, relay_session]
    call_count = 0

    def mock_session_maker():
        nonlocal call_count
        session = sessions[call_count]
        call_count += 1
        return session

    with patch("app.core.database.AsyncSessionLocal", mock_session_maker):
        async with durable_unit_of_work(event_bus) as session:
            assert session is business_session

    business_session.commit.assert_awaited_once()
    relay_session.rollback.assert_awaited_once()
    relay_session.commit.assert_not_awaited()
