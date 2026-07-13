"""Notification API router."""

from fastapi import APIRouter, Depends

from app.core.response import SuccessEnvelope
from app.modules.notification.api.dependencies import get_list_notifications_use_case
from app.modules.notification.api.schemas import NotificationResponse
from app.modules.notification.use_cases.list_notifications import ListNotificationsUseCase

router = APIRouter(prefix="/notifications", tags=["Notification"])


@router.get("", response_model=SuccessEnvelope[list[NotificationResponse]])
async def list_notifications(
    use_case: ListNotificationsUseCase = Depends(get_list_notifications_use_case),
) -> SuccessEnvelope[list[NotificationResponse]]:
    notifications = await use_case.execute()
    return SuccessEnvelope(
        statusCode=200,
        data=[NotificationResponse.from_domain(n) for n in notifications],
    )
