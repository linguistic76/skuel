"""
Calendar API Routes
===================

JSON endpoints for calendar operations.

Routes:
    GET /api/v2/calendar/items/{item_id}    — Get item details
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.result_helpers import require_found
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports import CalendarServiceOperations


def create_calendar_api_routes(
    app: Any, rt: Any, calendar_service: "CalendarServiceOperations"
) -> None:
    """Register calendar API routes."""

    @rt("/api/v2/calendar/items/{item_id}")
    @boundary_handler()
    async def get_calendar_item(request: Request, item_id: str) -> Result[dict[str, Any]]:
        """Get details for a specific calendar item (scoped to the owner)."""
        user_uid = require_authenticated_user(request)
        found = require_found(
            await calendar_service.get_item(user_uid, item_id),
            "CalendarItem",
            item_id,
        )
        if found.is_error:
            return Result.fail(found)
        item = found.value
        return Result.ok(
            {
                "uid": item.uid,
                "source_uid": item.source_uid,
                "item_type": item.item_type.value,
                "title": item.title,
                "description": item.description,
                "start_time": item.start_time.isoformat(),
                "end_time": item.end_time.isoformat(),
                "all_day": item.all_day,
                # Due-STATE of a task (one Task kind — periodic-notes arc E1):
                # without it, API consumers can't tell due-only from scheduled.
                "is_due": item.is_due,
                "color": item.color,
                "icon": item.icon,
                "priority": item.priority,
                "category": item.category,
                "is_recurring": item.is_recurring,
                "recurrence_pattern": item.recurrence_pattern,
                "tags": item.tags,
                "related_uids": item.related_uids,
                "project_uid": item.project_uid,
                "streak_count": item.streak_count,
                # The habit's slot (habit-rhythm arc M1): without it a consumer
                # would read the representative hour on start_time as a clock
                # commitment the habit never made.
                "time_of_day": item.time_of_day.value if item.time_of_day else None,
                "occurrence_data": item.occurrence_data,
                "attendee_emails": list(item.attendee_emails),
                "attendee_count": len(item.attendee_emails),
                "max_attendees": item.max_attendees,
                "location": item.location,
                "is_online": item.is_online,
                "metadata": item.metadata,
            }
        )
