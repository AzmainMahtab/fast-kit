"""Ordering domain exceptions."""

from app.core.exceptions import AppException


class OrderNotFoundError(AppException):
    """Raised when an order cannot be found."""

    def __init__(self, detail: str = "Order not found."):
        super().__init__(code="ORDER_NOT_FOUND", status_code=404, detail=detail)


class JobNotFoundError(AppException):
    """Raised when a job cannot be found."""

    def __init__(self, detail: str = "Job not found."):
        super().__init__(code="JOB_NOT_FOUND", status_code=404, detail=detail)


class InvalidStatusTransitionError(AppException):
    """Raised when a job status transition is invalid."""

    def __init__(self, detail: str = "Invalid job status transition."):
        super().__init__(code="INVALID_STATUS_TRANSITION", status_code=400, detail=detail)
