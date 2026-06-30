from dataclasses import dataclass

from app.core.pagination import Page
from app.modules.car.domain.entities import Car


@dataclass(frozen=True)
class CarActionResult:
    car: Car


@dataclass(frozen=True)
class ListCarsResult:
    page: Page[Car]
