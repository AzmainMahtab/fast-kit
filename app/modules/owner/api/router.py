from fastapi import APIRouter, Depends, Query

from app.core.exceptions import AppException
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PaginationParams
from app.core.response import CleanRoute, ErrorEnvelope, SuccessEnvelope
from app.modules.owner.api.dependencies import (
    get_create_owner_use_case,
    get_get_owner_use_case,
    get_list_owners_use_case,
)
from app.modules.owner.api.schemas import CreateOwnerRequest, OwnerListResponse, OwnerResponse
from app.modules.owner.cqrs.command import CreateOwnerCommand
from app.modules.owner.cqrs.query import GetOwnerByUserIdQuery, GetOwnerByUuidQuery, ListOwnersQuery
from app.modules.owner.domain.exception import OwnerAlreadyExistsError, OwnerNotFoundError
from app.modules.owner.use_cases.create_owner import CreateOwnerUseCase
from app.modules.owner.use_cases.get_owner import GetOwnerUseCase
from app.modules.owner.use_cases.list_owners import ListOwnersUseCase

router = APIRouter(prefix="/owners", tags=["owners"], route_class=CleanRoute)

DOMAIN_TO_APP = {
    OwnerNotFoundError: ("OWNER_NOT_FOUND", 404),
    OwnerAlreadyExistsError: ("OWNER_ALREADY_EXISTS", 409),
}


def _map_error(exc: Exception) -> AppException:
    exc_class = type(exc)
    if exc_class in DOMAIN_TO_APP:
        code, status = DOMAIN_TO_APP[exc_class]
        return AppException(code=code, status_code=status, detail=str(exc))
    return AppException(code="UNKNOWN_ERROR", status_code=500, detail=str(exc))


@router.post(
    "",
    response_model=SuccessEnvelope[OwnerResponse],
    status_code=201,
    responses={
        409: {"model": ErrorEnvelope, "description": "Owner already exists for user"},
    },
    summary="Create a new owner",
)
async def create_owner(request: CreateOwnerRequest, use_case: CreateOwnerUseCase = Depends(get_create_owner_use_case)):
    command = CreateOwnerCommand(
        user_id=request.user_id,
        address=request.address,
        date_of_birth=request.date_of_birth,
    )
    try:
        result = await use_case.execute(command)
    except OwnerAlreadyExistsError as e:
        raise _map_error(e) from e

    return SuccessEnvelope(statusCode=201, data=OwnerResponse.from_entity(result.owner))


@router.get(
    "/{uuid}",
    response_model=SuccessEnvelope[OwnerResponse],
    responses={404: {"model": ErrorEnvelope, "description": "Owner not found"}},
    summary="Get owner by UUID",
)
async def get_by_uuid(uuid: str, use_case: GetOwnerUseCase = Depends(get_get_owner_use_case)):
    query = GetOwnerByUuidQuery(uuid=uuid)
    try:
        owner = await use_case.by_uuid(query)
    except OwnerNotFoundError as e:
        raise _map_error(e) from e

    return SuccessEnvelope(statusCode=200, data=OwnerResponse.from_entity(owner))


@router.get(
    "/by-user/{user_id}",
    response_model=SuccessEnvelope[OwnerResponse],
    responses={404: {"model": ErrorEnvelope, "description": "Owner not found"}},
    summary="Get owner by user ID",
)
async def get_by_user_id(user_id: int, use_case: GetOwnerUseCase = Depends(get_get_owner_use_case)):
    query = GetOwnerByUserIdQuery(user_id=user_id)
    try:
        owner = await use_case.by_user_id(query)
    except OwnerNotFoundError as e:
        raise _map_error(e) from e

    return SuccessEnvelope(statusCode=200, data=OwnerResponse.from_entity(owner))


@router.get("", response_model=SuccessEnvelope[OwnerListResponse], summary="List all owners")
async def list_owners(
    offset: int = Query(default=0, ge=0, description="Number of records to skip for pagination."),
    limit: int = Query(
        default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Maximum number of records to return."
    ),
    use_case: ListOwnersUseCase = Depends(get_list_owners_use_case),
):
    query = ListOwnersQuery(pagination=PaginationParams(offset=offset, limit=limit))
    result = await use_case.execute(query)

    return SuccessEnvelope(
        statusCode=200,
        data=OwnerListResponse(
            items=[OwnerResponse.from_entity(o) for o in result.page.items],
            total=result.page.total,
            offset=result.page.offset,
            limit=result.page.limit,
        ),
    )
