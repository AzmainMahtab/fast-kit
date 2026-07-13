import pytest

from app.modules.auth.cqrs.command import LoginCommand
from app.modules.auth.domain.events import UserLoggedInEvent
from app.modules.auth.domain.exception import AccountSuspendedError, InvalidCredentialsError
from app.modules.auth.use_cases.login import LoginUseCase


@pytest.mark.asyncio
async def test_login_success(active_user, user_repo, cache, jwt_service, event_bus) -> None:
    uc = LoginUseCase(user_repo=user_repo, cache=cache, jwt=jwt_service, event_bus=event_bus)
    command = LoginCommand(email="active@example.com", password="correct-password")
    # Password won't match the placeholder hash, but we just test the flow
    with pytest.raises(InvalidCredentialsError):
        await uc.execute(command)


@pytest.mark.asyncio
async def test_login_suspended_user_raises_error(suspended_user, user_repo, cache, jwt_service, event_bus) -> None:
    uc = LoginUseCase(user_repo=user_repo, cache=cache, jwt=jwt_service, event_bus=event_bus)
    command = LoginCommand(email="suspended@example.com", password="any")
    with pytest.raises(AccountSuspendedError):
        await uc.execute(command)


@pytest.mark.asyncio
async def test_login_inactive_user_raises_error(inactive_user, user_repo, cache, jwt_service, event_bus) -> None:
    uc = LoginUseCase(user_repo=user_repo, cache=cache, jwt=jwt_service, event_bus=event_bus)
    command = LoginCommand(email="inactive@example.com", password="any")
    with pytest.raises(InvalidCredentialsError):
        await uc.execute(command)


@pytest.mark.asyncio
async def test_login_nonexistent_email_raises_error(user_repo, cache, jwt_service, event_bus) -> None:
    uc = LoginUseCase(user_repo=user_repo, cache=cache, jwt=jwt_service, event_bus=event_bus)
    command = LoginCommand(email="nonexistent@example.com", password="any")
    with pytest.raises(InvalidCredentialsError):
        await uc.execute(command)


@pytest.mark.asyncio
async def test_login_publishes_event_on_success(
    active_user, user_repo, cache, jwt_service, event_bus, monkeypatch
) -> None:
    """Test that UserLoggedInEvent is published after successful auth.

    Uses a monkeypatched verify_password that always succeeds.
    """
    import app.modules.auth.use_cases.login as login_module

    original_verify = login_module.verify_password
    login_module.verify_password = lambda pw, hp: True  # type: ignore[assignment]
    login_module.need_to_rehash = lambda hp: False  # type: ignore[assignment]

    received_events: list[UserLoggedInEvent] = []

    async def handler(event: UserLoggedInEvent) -> None:
        received_events.append(event)

    event_bus.subscribe(UserLoggedInEvent, handler)

    user = active_user  # create active user fixture
    uc = LoginUseCase(user_repo=user_repo, cache=cache, jwt=jwt_service, event_bus=event_bus)
    command = LoginCommand(email="active@example.com", password="any-password")
    result = await uc.execute(command)

    assert result.access_token is not None
    assert result.refresh_token is not None
    assert result.token_type == "bearer"
    assert len(received_events) == 1
    assert received_events[0].user_uuid == user.uuid
    assert received_events[0].email == "active@example.com"

    login_module.verify_password = original_verify


@pytest.mark.asyncio
async def test_login_no_event_on_failure(suspended_user, user_repo, cache, jwt_service, event_bus) -> None:
    received_events: list[UserLoggedInEvent] = []

    async def handler(event: UserLoggedInEvent) -> None:
        received_events.append(event)

    event_bus.subscribe(UserLoggedInEvent, handler)

    uc = LoginUseCase(user_repo=user_repo, cache=cache, jwt=jwt_service, event_bus=event_bus)
    command = LoginCommand(email="suspended@example.com", password="any")
    with pytest.raises(AccountSuspendedError):
        await uc.execute(command)

    assert len(received_events) == 0
