from typing import Any

from fastapi.routing import APIRoute
from pydantic import BaseModel


class ErrorItem(BaseModel):
    """A single error detail returned in ErrorEnvelope.errors.

    Attributes:
        code: Machine-readable error code (e.g. "USER_ALREADY_EXISTS").
        field: The request field that caused the error, if applicable.
        message: Human-readable description of the error.
    """

    code: str | None = None
    field: str | None = None
    message: str | None = None


class SuccessEnvelope[DataT](BaseModel):
    """Response envelope for 2xx success responses.

    The generic type parameter ``DataT`` resolves to the actual response
    model in Swagger (e.g. ``SuccessEnvelope[UserResponse]`` shows
    ``UserResponse`` inside the ``data`` field).

    Attributes:
        success: Always ``true`` for success responses.
        status: Always ``"success"`` (matches JSEND convention).
        statusCode: HTTP status code of the response.
        data: The actual response payload.
        meta: Optional metadata (e.g. request ID, processing time).
    """

    success: bool = True
    status: str = "success"
    statusCode: int
    data: DataT
    meta: dict[str, Any] | None = None


class ErrorEnvelope(BaseModel):
    """Response envelope for 4xx/5xx error responses.

    Fields that only make sense on success (``data``, ``meta``) are
    intentionally omitted so they don't pollute the Swagger schema.

    Attributes:
        success: Always ``false`` for error responses.
        status: ``"fail"`` for client errors, ``"error"`` for server errors.
        statusCode: HTTP status code.
        errors: List of ``ErrorItem`` with machine-readable codes and
            human-readable messages.
    """

    success: bool = False
    status: str
    statusCode: int
    errors: list[ErrorItem]


class CleanRoute(APIRoute):
    """Custom route class that strips ``null`` fields from all responses.

    FastAPI's ``jsonable_encoder`` includes ``null`` for optional fields
    by default. This route class sets ``response_model_exclude_none = True``
    so that optional fields like ``meta`` are omitted from the JSON when
    they are not explicitly set.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.response_model_exclude_none = True
