from fastapi import APIRouter, Depends, Query

from app.core.exceptions import AppException
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PaginationParams
from app.core.response import CleanRoute, ErrorEnvelope, SuccessEnvelope
from app.modules.car.api.dependencies import get_create_car_use_case, get_get_car_use_case, get_list_cars_use_case
from app.modules.car.api.schemas import CarListResponse, CarResponse, CreateCarRequest
from app.modules.car.cqrs.command import CreateCarCommand
from app.modules.car.cqrs.query import GetCarByUuidQuery, ListCarsByOwnerQuery, ListCarsQuery
from app.modules.car.domain.exception import CarNotFoundError
from app.modules.car.use_cases.create_car import CreateCarUseCase
from app.modules.car.use_cases.get_car import GetCarUseCase
from app.modules.car.use_cases.list_cars import ListCarsUseCase

router = APIRouter(prefix="/cars", tags=["cars"], route_class=CleanRoute)

DOMAIN_TO_APP = {
    CarNotFoundError: ("CAR_NOT_FOUND", 404),
}


def _map_error(exc: Exception) -> AppException:
    exc_class = type(exc)
    if exc_class in DOMAIN_TO_APP:
        code, status = DOMAIN_TO_APP[exc_class]
        return AppException(code=code, status_code=status, detail=str(exc))
    return AppException(code="UNKNOWN_ERROR", status_code=500, detail=str(exc))


@router.post(
    "",
    response_model=SuccessEnvelope[CarResponse],
    status_code=201,
    summary="Create a new car",
)
async def create_car(request: CreateCarRequest, use_case: CreateCarUseCase = Depends(get_create_car_use_case)):
    command = CreateCarCommand(
        owner_id=request.owner_id,
        make=request.make,
        model=request.model,
        year=request.year,
        color=request.color,
        license_plate=request.license_plate,
    )
    result = await use_case.execute(command)
    return SuccessEnvelope(statusCode=201, data=CarResponse.from_entity(result.car))


@router.get(
    "/{uuid}",
    response_model=SuccessEnvelope[CarResponse],
    responses={404: {"model": ErrorEnvelope, "description": "Car not found"}},
    summary="Get car by UUID",
)
async def get_by_uuid(uuid: str, use_case: GetCarUseCase = Depends(get_get_car_use_case)):
    query = GetCarByUuidQuery(uuid=uuid)
    try:
        car = await use_case.by_uuid(query)
    except CarNotFoundError as e:
        raise _map_error(e) from e

    return SuccessEnvelope(statusCode=200, data=CarResponse.from_entity(car))


@router.get(
    "/by-owner/{owner_id}",
    response_model=SuccessEnvelope[CarListResponse],
    summary="List cars by owner ID",
)
async def list_by_owner(
    owner_id: int,
    offset: int = Query(default=0, ge=0, description="Number of records to skip for pagination."),
    limit: int = Query(
        default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Maximum number of records to return."
    ),
    use_case: ListCarsUseCase = Depends(get_list_cars_use_case),
):
    query = ListCarsByOwnerQuery(owner_id=owner_id, pagination=PaginationParams(offset=offset, limit=limit))
    result = await use_case.by_owner(query)

    return SuccessEnvelope(
        statusCode=200,
        data=CarListResponse(
            items=[CarResponse.from_entity(c) for c in result.page.items],
            total=result.page.total,
            offset=result.page.offset,
            limit=result.page.limit,
        ),
    )


@router.get("", response_model=SuccessEnvelope[CarListResponse], summary="List all cars")
async def list_cars(
    offset: int = Query(default=0, ge=0, description="Number of records to skip for pagination."),
    limit: int = Query(
        default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Maximum number of records to return."
    ),
    use_case: ListCarsUseCase = Depends(get_list_cars_use_case),
):
    query = ListCarsQuery(pagination=PaginationParams(offset=offset, limit=limit))
    result = await use_case.all_cars(query)

    return SuccessEnvelope(
        statusCode=200,
        data=CarListResponse(
            items=[CarResponse.from_entity(c) for c in result.page.items],
            total=result.page.total,
            offset=result.page.offset,
            limit=result.page.limit,
        ),
    )
