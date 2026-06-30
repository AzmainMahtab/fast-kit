import uuid_utils
from sqlalchemy import UUID, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, BaseModelMixin


class CarModel(BaseModelMixin, Base):
    __tablename__ = "cars"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid_utils.uuid7,
        server_default=func.uuid_generate_v7(),
    )

    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), nullable=False, index=True)
    make: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[str] = mapped_column(String(30), nullable=False)
    license_plate: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)

    # Relationship to owner (many-to-one)
    owner: Mapped["OwnerModel"] = relationship("OwnerModel", back_populates="cars")  # noqa: F821
