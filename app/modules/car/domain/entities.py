from dataclasses import dataclass
from datetime import datetime


@dataclass
class Car:
    """Domain Entity: A car belonging to an Owner."""

    id: int | None = None
    uuid: str | None = None
    owner_id: int = 0
    make: str = ""
    model: str = ""
    year: int = 0
    color: str = ""
    license_plate: str = ""

    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
