from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials

from app.core.exceptions import AppException
from app.core.rate_limit import rate_limit
from app.core.response import CleanRoute, ErrorEnvelope, SuccessEnvelope
from app.modules.auth.api.dependencies import (
    get_activate_account_use_case,
    get_login_use_case,
    get_logout_use_case,
    get_profile_use_case,
    get_refresh_use_case,
    get_send_activation_otp_use_case,
    require_authenticated,
    security,
)
from app.modules.auth.api.schemas import (
    ActivateAccountRequest,
    ActivateAccountResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    SendActivationOtpResponse,
    TokenResponse,
    UserProfileResponse,
)
from app.modules.auth.cqrs.command import (
    ActivateAccountCommand,
    LoginCommand,
    LogoutCommand,
    RefreshTokenCommand,
    SendActivationOtpCommand,
)
from app.modules.auth.cqrs.query import GetProfileQuery
from app.modules.auth.domain.exception import AUTH_EXCEPTIONS, AuthenticationError
from app.modules.auth.use_cases.activate_account import ActivateAccountUseCase
from app.modules.auth.use_cases.login import LoginUseCase
from app.modules.auth.use_cases.logout import LogoutUseCase
from app.modules.auth.use_cases.profile import GetProfileUseCase
from app.modules.auth.use_cases.refresh import RefreshTokenUseCase
from app.modules.auth.use_cases.send_activation_otp import SendActivationOtpUseCase
from app.modules.otp.domain.exceptions import InvalidOtpError, OtpAlreadyUsedError, OtpExpiredError

router = APIRouter(prefix="/auth", tags=["auth"], route_class=CleanRoute)


def _map_auth_error(exc: AuthenticationError) -> AppException:
    """Convert a domain exception into an ``AppException`` with a machine-readable code.

    Args:
        exc: The domain exception raised during authentication.

    Returns:
        An ``AppException`` with the appropriate HTTP status and error code.
    """
    exc_class = type(exc)
    if exc_class in AUTH_EXCEPTIONS:
        code, status = AUTH_EXCEPTIONS[exc_class]
        return AppException(code=code, status_code=status, detail=str(exc))
    return AppException(code="AUTH_ERROR", status_code=401, detail=str(exc))


@router.post(
    "/login",
    response_model=SuccessEnvelope[TokenResponse],
    status_code=200,
    responses={
        401: {"model": ErrorEnvelope, "description": "Invalid credentials"},
        403: {"model": ErrorEnvelope, "description": "Account suspended"},
        429: {"model": ErrorEnvelope, "description": "Too many requests"},
    },
    summary="Authenticate and receive JWT tokens",
    dependencies=[Depends(rate_limit(5, 60))],
)
async def login(request: LoginRequest, use_case: LoginUseCase = Depends(get_login_use_case)):
    """Authenticate a user with email and password.

    Validates credentials against Argon2id, caches the result in Redis
    for faster subsequent logins, and returns an access + refresh token pair.
    """
    command = LoginCommand(email=request.email, password=request.password)
    try:
        result = await use_case.execute(command)
    except AuthenticationError as e:
        raise _map_auth_error(e) from e

    return SuccessEnvelope(
        statusCode=200, data=TokenResponse(access_token=result.access_token, refresh_token=result.refresh_token)
    )


@router.post(
    "/refresh",
    response_model=SuccessEnvelope[TokenResponse],
    responses={
        401: {"model": ErrorEnvelope, "description": "Invalid or expired refresh token"},
        429: {"model": ErrorEnvelope, "description": "Too many requests"},
    },
    summary="Obtain a new access token using a refresh token",
    dependencies=[Depends(rate_limit(10, 60))],
)
async def refresh(request: RefreshRequest, use_case: RefreshTokenUseCase = Depends(get_refresh_use_case)):
    """Exchange a valid refresh token for a new token pair.

    The old refresh token is blacklisted immediately (rotation) so it
    cannot be reused. Both tokens are returned with fresh lifetimes.
    """
    command = RefreshTokenCommand(refresh_token=request.refresh_token)
    try:
        result = await use_case.execute(command)
    except AuthenticationError as e:
        raise _map_auth_error(e) from e

    return SuccessEnvelope(
        statusCode=200, data=TokenResponse(access_token=result.access_token, refresh_token=result.refresh_token)
    )


@router.post(
    "/logout",
    status_code=200,
    response_model=SuccessEnvelope[dict],
    responses={
        401: {"model": ErrorEnvelope, "description": "Invalid token"},
        429: {"model": ErrorEnvelope, "description": "Too many requests"},
    },
    summary="Revoke tokens",
    dependencies=[Depends(rate_limit(10, 60))],
)
async def logout(
    request: LogoutRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    use_case: LogoutUseCase = Depends(get_logout_use_case),
):
    """Revoke both the refresh token and the current access token.

    The refresh token (from the request body) and the access token
    (from the ``Authorization`` header) are both required and blacklisted
    for the remainder of their natural lifetimes.
    """
    command = LogoutCommand(refresh_token=request.refresh_token, access_token=credentials.credentials)
    try:
        result = await use_case.execute(command)
    except AuthenticationError as e:
        raise _map_auth_error(e) from e

    return SuccessEnvelope(statusCode=200, data={"message": result.message})


@router.get(
    "/profile",
    response_model=SuccessEnvelope[UserProfileResponse],
    responses={401: {"model": ErrorEnvelope, "description": "Missing, expired, or invalid access token"}},
    summary="Get the authenticated user's profile",
)
async def profile(
    identity: str = Depends(require_authenticated), use_case: GetProfileUseCase = Depends(get_profile_use_case)
):
    """Return the authenticated user's profile details.

    Requires a valid **access token** in the ``Authorization`` header.
    Results are cached in Redis for 5 minutes to accelerate repeated
    profile fetches.
    """
    query = GetProfileQuery(user_uuid=identity)
    result = await use_case.execute(query)
    return SuccessEnvelope(statusCode=200, data=UserProfileResponse.from_entity(result.user))


@router.post(
    "/activate/send-otp",
    response_model=SuccessEnvelope[SendActivationOtpResponse],
    status_code=200,
    responses={
        401: {"model": ErrorEnvelope, "description": "Invalid or missing access token"},
        409: {"model": ErrorEnvelope, "description": "Account is already active"},
        429: {"model": ErrorEnvelope, "description": "Too many requests"},
    },
    summary="Send an account activation OTP to the user's email",
    dependencies=[Depends(rate_limit(3, 300))],
)
async def send_activation_otp(
    identity: str = Depends(require_authenticated),
    use_case: SendActivationOtpUseCase = Depends(get_send_activation_otp_use_case),
):
    command = SendActivationOtpCommand(user_uuid=identity)
    try:
        result = await use_case.execute(command)
    except AuthenticationError as e:
        raise _map_auth_error(e) from e

    return SuccessEnvelope(statusCode=200, data=SendActivationOtpResponse(message=result.message))


@router.post(
    "/activate/verify",
    response_model=SuccessEnvelope[ActivateAccountResponse],
    status_code=200,
    responses={
        401: {"model": ErrorEnvelope, "description": "Invalid, expired, or already-used OTP"},
        409: {"model": ErrorEnvelope, "description": "Account is already active"},
        429: {"model": ErrorEnvelope, "description": "Too many requests"},
    },
    summary="Verify activation OTP and activate the account",
    dependencies=[Depends(rate_limit(5, 60))],
)
async def activate_account(
    request: ActivateAccountRequest,
    identity: str = Depends(require_authenticated),
    use_case: ActivateAccountUseCase = Depends(get_activate_account_use_case),
):
    command = ActivateAccountCommand(user_uuid=identity, code=request.code)
    try:
        result = await use_case.execute(command)
    except AuthenticationError as e:
        raise _map_auth_error(e) from e
    except (InvalidOtpError, OtpExpiredError, OtpAlreadyUsedError) as e:
        otp_map = {
            InvalidOtpError: ("INVALID_OTP", 401),
            OtpExpiredError: ("OTP_EXPIRED", 401),
            OtpAlreadyUsedError: ("OTP_ALREADY_USED", 401),
        }
        code, status_code = otp_map[type(e)]
        raise AppException(code=code, status_code=status_code, detail=str(e)) from e

    return SuccessEnvelope(statusCode=200, data=ActivateAccountResponse(message=result.message))
