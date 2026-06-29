from dataclasses import dataclass


@dataclass(frozen=True)
class LoginCommand:
    email: str
    password: str


@dataclass(frozen=True)
class RefreshTokenCommand:
    refresh_token: str


@dataclass(frozen=True)
class LogoutCommand:
    refresh_token: str
    access_token: str = ""


@dataclass(frozen=True)
class SendActivationOtpCommand:
    user_uuid: str


@dataclass(frozen=True)
class ActivateAccountCommand:
    user_uuid: str
    code: str
