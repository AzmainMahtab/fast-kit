from app.core.event_bus import IEventBus
from app.core.hasher import get_password_hash
from app.core.settings import settings
from app.modules.user.cqrs.command import RegisterUserCommand
from app.modules.user.cqrs.result import RegisterUserResult
from app.modules.user.domain.entities import User
from app.modules.user.domain.events import UserRegisteredEvent
from app.modules.user.domain.exception import (
    InvalidPhoneNumberError,
    PasswordsDoNotMatchError,
    UserAlreadyExistsError,
    WeakPasswordError,
)
from app.modules.user.domain.interfaces import IUserRepository
from app.modules.user.domain.value_objects import Email, HashedPassword, PhoneNumber, PlainPassword


class RegisterUserUseCase:
    def __init__(self, user_repo: IUserRepository, event_bus: IEventBus):
        self.user_repo = user_repo
        self.event_bus = event_bus

    async def execute(self, command: RegisterUserCommand) -> RegisterUserResult:
        if command.password != command.password2:
            raise PasswordsDoNotMatchError("Passwords do not match.")

        try:
            PlainPassword(command.password)
        except ValueError as e:
            raise WeakPasswordError(str(e)) from e

        try:
            phone_number_vo = PhoneNumber(command.phone_number)
        except ValueError as e:
            raise InvalidPhoneNumberError(str(e)) from e

        email_vo = Email(command.email)

        existing_user = await self.user_repo.get_by_email(email_vo)
        if existing_user:
            raise UserAlreadyExistsError(f"User with {command.email} already exists.")

        hashed_pw = HashedPassword(get_password_hash(command.password))

        new_user = User(
            email=email_vo,
            hashed_password=hashed_pw,
            username=command.username,
            phone_number=phone_number_vo,
            first_name=command.first_name,
            last_name=command.last_name,
        )

        # First superuser gets automatic superuser privileges
        if settings.FIRST_SUPERUSER_EMAIL and command.email == str(settings.FIRST_SUPERUSER_EMAIL):
            new_user.is_superuser = True

        saved_user = await self.user_repo.create(new_user)
        await self.user_repo.commit()

        event = UserRegisteredEvent(
            email=email_vo,
            username=command.username,
            phone_number=phone_number_vo,
            first_name=command.first_name,
            last_name=command.last_name,
        )
        await self.event_bus.publish(event)

        return RegisterUserResult(user=saved_user)
