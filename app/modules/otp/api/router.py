from fastapi import APIRouter, Depends, status

from app.core.exceptions import AppException
from app.core.response import CleanRoute, ErrorEnvelope, SuccessEnvelope
from app.modules.otp.api.dependencies import get_validate_otp_use_case
from app.modules.otp.api.schemas import ValidateOtpRequest, ValidateOtpResponse
from app.modules.otp.domain.exceptions import InvalidOtpError, OtpAlreadyUsedError, OtpExpiredError
from app.modules.otp.use_cases.validate_otp import ValidateOtpUseCase

router = APIRouter(prefix="/auth/otp", tags=["otp"], route_class=CleanRoute)

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
    responses={401: {"model": ErrorEnvelope, "description": "Invalid, expired, or already-used OTP"}},
    summary="Validate an OTP code",
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
