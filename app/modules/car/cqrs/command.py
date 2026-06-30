from dataclasses import dataclass


@dataclass(frozen=True)
class CreateCarCommand:
    owner_id: int
    make: str
    model: str
    year: int
    color: str
    license_plate: str
