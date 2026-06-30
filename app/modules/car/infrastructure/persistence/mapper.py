from app.modules.car.domain.entities import Car
from app.modules.car.infrastructure.persistence.models import CarModel


def map_to_domain(orm_model: CarModel) -> Car:
    return Car(
        id=orm_model.id,
        uuid=str(orm_model.uuid) if orm_model.uuid else None,
        owner_id=orm_model.owner_id,
        make=orm_model.make,
        model=orm_model.model,
        year=orm_model.year,
        color=orm_model.color,
        license_plate=orm_model.license_plate,
        created_at=orm_model.created_at,
        updated_at=orm_model.updated_at,
        deleted_at=orm_model.deleted_at,
    )


def map_to_persistence(entity: Car) -> CarModel:
    return CarModel(
        id=entity.id,
        uuid=entity.uuid,
        owner_id=entity.owner_id,
        make=entity.make,
        model=entity.model,
        year=entity.year,
        color=entity.color,
        license_plate=entity.license_plate,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        deleted_at=entity.deleted_at,
    )
