from app.modules.owner.domain.entities import Owner
from app.modules.owner.infrastructure.persistence.models import OwnerModel


def map_to_domain(orm_model: OwnerModel) -> Owner:
    return Owner(
        id=orm_model.id,
        uuid=str(orm_model.uuid) if orm_model.uuid else None,
        user_id=orm_model.user_id,
        address=orm_model.address,
        date_of_birth=orm_model.date_of_birth,
        created_at=orm_model.created_at,
        updated_at=orm_model.updated_at,
        deleted_at=orm_model.deleted_at,
    )


def map_to_persistence(entity: Owner) -> OwnerModel:
    return OwnerModel(
        id=entity.id,
        uuid=entity.uuid,
        user_id=entity.user_id,
        address=entity.address,
        date_of_birth=entity.date_of_birth,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        deleted_at=entity.deleted_at,
    )
