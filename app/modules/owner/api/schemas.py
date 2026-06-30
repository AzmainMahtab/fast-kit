from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.pagination import PaginatedResponse


class CreateOwnerRequest(BaseModel):
    user_id: int = Field(description="ID of the associated user.")
    address: str = Field(description="Owner's address.")
    date_of_birth: date | None = Field(default=None, description="Optional date of birth.")


class OwnerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: str = Field(description="Universally unique identifier (UUID v7).")
    user_id: int = Field(description="ID of the associated user.")
    address: str = Field(description="Owner's address.")
    date_of_birth: date | None = Field(default=None, description="Date of birth.")
    created_at: datetime | None = Field(default=None, description="Timestamp of creation.")
    updated_at: datetime | None = Field(default=None, description="Timestamp of last update.")
    deleted_at: datetime | None = Field(default=None, description="Timestamp of soft deletion, if applicable.")

    @classmethod
    def from_entity(cls, owner) -> OwnerResponse:
        return cls(
            uuid=owner.uuid or "",
            user_id=owner.user_id,
            address=owner.address,
            date_of_birth=owner.date_of_birth,
            created_at=owner.created_at,
            updated_at=owner.updated_at,
            deleted_at=owner.deleted_at,
        )


OwnerListResponse = PaginatedResponse[OwnerResponse]
