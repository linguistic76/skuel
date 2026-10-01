"""
``optimize_recurring_schedule`` returns the read's own failure.

The method counts the user's events per day before proposing dates. When that read
fails there is nothing to count, and the caller is told what failed: the backend's
error, not a second error raised by reading a failed result's value.
"""

from unittest.mock import AsyncMock, Mock

from core.models.enums.scheduling_enums import RecurrencePattern
from core.models.event.event import Event
from core.services.events.events_scheduling_service import EventsSchedulingService
from core.utils.result_simplified import Errors, Result


async def test_a_failed_event_read_is_the_result():
    backend = Mock()
    failure: Result[list[Event]] = Result.fail(
        Errors.database(message="events unavailable", operation="find_by")
    )
    backend.find_by = AsyncMock(return_value=failure)
    service = EventsSchedulingService(backend=backend)

    result = await service.optimize_recurring_schedule("user_1", RecurrencePattern.WEEKLY)

    assert result.is_error
    assert result.expect_error().message == "events unavailable"
