from fastapi import APIRouter, Depends, status

from app.core.cache import ICacheService, get_security_cache_service
from app.core.exceptions import AppException
from app.core.rate_limit import RateLimiter, rate_limit
from app.core.response import CleanRoute, ErrorEnvelope, SuccessEnvelope
from app.modules.otp.api.dependencies import get_validate_otp_use_case
from app.modules.otp.api.schemas import ValidateOtpRequest, ValidateOtpResponse
from app.modules.otp.domain.exceptions import InvalidOtpError, OtpAlreadyUsedError, OtpExpiredError
from app.modules.otp.use_cases.validate_otp import ValidateOtpUseCase

router = APIRouter(prefix="/auth/otp", tags=["otp"], route_class=CleanRoute)


class OtpValidateUserRateLimiter:
    """Per-user rate limiter for OTP validation attempts.

    Brute-forcing a 6-digit OTP is feasible if an attacker can make enough
    requests. This limiter caps attempts per user UUID independently of the
    calling IP address.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self._max = max_requests
        self._window = window_seconds

    async def __call__(
        self,
        request: ValidateOtpRequest,
        cache: ICacheService = Depends(get_security_cache_service),
    ) -> None:
        key = f"rate_limit:otp_validate:user:{request.user_uuid}"
        limiter = RateLimiter(cache, self._max, self._window)
        await limiter.check(key)

OTP_EXCEPTIONS: dict[type[Exception], tuple[str, int]] = {
    InvalidOtpError: ("INVALID_OTP", status.HTTP_401_UNAUTHORIZED),
    OtpExpiredError: ("OTP_EXPIRED", status.HTTP_401_UNAUTHORIZED),
    OtpAlreadyUsedError: ("OTP_ALREADY_USED", status.HTTP_401_UNAUTHORIZED),
}


def _map_otp_error(exc: Exception) -> AppException:
    exc_class = type(exc)
    if exc_class in OTP_EXCEPTIONS:
        code, http_status = OTP_EXCEPTIONS[exc_class]
        return AppException(code=code, status_code=http_status, detail=str(exc))
    return AppException(code="OTP_ERROR", status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/validate",
    response_model=SuccessEnvelope[ValidateOtpResponse],
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorEnvelope, "description": "Invalid, expired, or already-used OTP"},
        429: {"model": ErrorEnvelope, "description": "Too many validation attempts"},
    },
    summary="Validate an OTP code",
    dependencies=[
        Depends(rate_limit(20, 900)),  # IP-based: 20 attempts per 15 minutes
        Depends(OtpValidateUserRateLimiter(5, 900)),  # user-based: 5 attempts per 15 minutes
    ],
)
async def validate_otp(
    request: ValidateOtpRequest, use_case: ValidateOtpUseCase = Depends(get_validate_otp_use_case)
) -> SuccessEnvelope[ValidateOtpResponse]:
    """Validate a one-time password (OTP) for a user.

    Checks the cache first for fast validation; falls back to the database
    hash check. The OTP is marked as used on success.
    """
    command = request.to_command()
    try:
        result = await use_case.execute(command)
    except (InvalidOtpError, OtpExpiredError, OtpAlreadyUsedError) as e:
        raise _map_otp_error(e) from e

    return SuccessEnvelope(statusCode=200, data=ValidateOtpResponse(success=result.success))
