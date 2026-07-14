import pytest

from app.modules.notification.use_cases.record_notification import (
    RecordNotificationUseCase,
)


@pytest.mark.asyncio
async def test_record_notification(notification_repo):
    use_case = RecordNotificationUseCase(notification_repo=notification_repo)

    result = await use_case.execute(
        event_type="ordering.job_status_changed",
        aggregate_type="job",
        aggregate_id=42,
        message="Job moved to PREPRESS",
    )

    assert result.event_type == "ordering.job_status_changed"
    assert result.message == "Job moved to PREPRESS"
