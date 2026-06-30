from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.pagination import PaginatedResponse


class CreateCarRequest(BaseModel):
    owner_id: int = Field(description="ID of the owner.")
    make: str = Field(description="Car make (manufacturer).")
    model: str = Field(description="Car model.")
    year: int = Field(description="Year of manufacture.", ge=1900, le=2100)
    color: str = Field(description="Car color.")
    license_plate: str = Field(description="License plate number. Must be unique.")


class CarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: str = Field(description="Universally unique identifier (UUID v7).")
    owner_id: int = Field(description="ID of the owner.")
    make: str = Field(description="Car make.")
    model: str = Field(description="Car model.")
    year: int = Field(description="Year of manufacture.")
    color: str = Field(description="Car color.")
    license_plate: str = Field(description="License plate number.")
    created_at: datetime | None = Field(default=None, description="Timestamp of creation.")
    updated_at: datetime | None = Field(default=None, description="Timestamp of last update.")
    deleted_at: datetime | None = Field(default=None, description="Timestamp of soft deletion, if applicable.")

    @classmethod
    def from_entity(cls, car) -> CarResponse:
        return cls(
            uuid=car.uuid or "",
            owner_id=car.owner_id,
            make=car.make,
            model=car.model,
            year=car.year,
            color=car.color,
            license_plate=car.license_plate,
            created_at=car.created_at,
            updated_at=car.updated_at,
            deleted_at=car.deleted_at,
        )


CarListResponse = PaginatedResponse[CarResponse]
