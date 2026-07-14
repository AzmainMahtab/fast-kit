"""Production job state machine."""

from app.modules.ordering.domain.exceptions import InvalidStatusTransitionError


class JobStateMachine:
    """Single source of truth for valid job status transitions."""

    PENDING = "PENDING"
    RECEIVED_ARTWORK = "RECEIVED_ARTWORK"
    PREPRESS = "PREPRESS"
    BATCHED = "BATCHED"
    HOLD = "HOLD"
    CANCELED = "CANCELED"
    COMPLETE = "COMPLETE"

    TRANSITIONS = {
        PENDING: [RECEIVED_ARTWORK, HOLD, CANCELED],
        RECEIVED_ARTWORK: [PREPRESS, HOLD, CANCELED],
        PREPRESS: [BATCHED, HOLD, CANCELED],
        BATCHED: [COMPLETE, HOLD, CANCELED],
        HOLD: [PENDING, CANCELED],
        CANCELED: [],
        COMPLETE: [],
    }

    FILE_EDITABLE_STATUSES = {PENDING, HOLD}

    @classmethod
    def can_transition(cls, from_status: str, to_status: str) -> bool:
        return to_status in cls.TRANSITIONS.get(from_status, [])

    @classmethod
    def assert_transition(cls, from_status: str, to_status: str) -> None:
        if not cls.can_transition(from_status, to_status):
            allowed = cls.TRANSITIONS.get(from_status, [])
            raise InvalidStatusTransitionError(
                f"Cannot transition from '{from_status}' to '{to_status}'. "
                f"Allowed: {allowed}"
            )

    @classmethod
    def is_file_editable(cls, status: str) -> bool:
        return status in cls.FILE_EDITABLE_STATUSES
