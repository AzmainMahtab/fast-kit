from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CreateOwnerCommand:
    user_id: int
    address: str
    date_of_birth: date | None = None
