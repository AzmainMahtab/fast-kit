import uuid_utils
from sqlalchemy import UUID, Date, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, BaseModelMixin


class OwnerModel(BaseModelMixin, Base):
    __tablename__ = "owners"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid_utils.uuid7,
        server_default=func.uuid_generate_v7(),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False, index=True)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    date_of_birth: Mapped[Date] = mapped_column(Date, nullable=True)

    # Relationship to cars (one-to-many)
    cars: Mapped[list["CarModel"]] = relationship("CarModel", back_populates="owner", lazy="selectin")  # noqa: F821
