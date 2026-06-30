from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class Owner:
    """Domain Entity: An owner of cars, linked to a User."""

    id: int | None = None
    uuid: str | None = None
    user_id: int = 0
    address: str = ""
    date_of_birth: date | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
