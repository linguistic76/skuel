"""
Calendar API Routes
===================

JSON and action endpoints for calendar operations.

Routes:
    POST  /api/calendar/quick-create          — Create a calendar item
    GET   /api/v2/calendar/items/{item_id}    — Get item details
    PATCH /api/events/calendar/reschedule     — Reschedule via drag-drop
"""

from datetime import datetime
from typing import Any

from fasthtml.common import Div, P
from starlette.requests import Request

from components.calendar_components import calendar_item_to_dict
from core.utils.error_boundary import boundary_handler
from core.utils.result_simplified import Errors, Result


def create_calendar_api_routes(app, rt, calendar_service):
    """Register calendar API routes."""

    @app.post("/api/calendar/quick-create")
    async def quick_create(request) -> Any:
        """Quick create a calendar item."""
        data = await request.json()

        result = await calendar_service.quick_create(
            item_type=data.get("type"),
            title=data.get("title"),
            start_time=datetime.fromisoformat(data.get("start_time")),
            **data.get("extras", {}),
        )

        if result.is_ok:
            return {"success": True, "item": calendar_item_to_dict(result.value)}
        else:
            return ({"success": False, "error": str(result.error)}, 400)

    @rt("/api/v2/calendar/items/{item_id}")
    @boundary_handler()
    async def get_calendar_item(_request, item_id: str) -> Result[Any]:
        """Get details for a specific calendar item."""
        result = await calendar_service.get_item(item_id)

        if result.is_ok and result.value:
            item = result.value
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
                    "occurrence_data": item.occurrence_data,
                    "attendee_emails": list(item.attendee_emails),
                    "attendee_count": len(item.attendee_emails),
                    "max_attendees": item.max_attendees,
                    "location": item.location,
                    "is_online": item.is_online,
                    "metadata": item.metadata,
                }
            )
        else:
            return Result.fail(Errors.not_found(resource="CalendarItem", identifier=item_id))

    @rt("/api/events/calendar/reschedule", methods=["PATCH"])
    async def reschedule_item(request: Request) -> Any:
        """
        Reschedule a calendar item via HTMX drag-drop.

        Reads uid and new_start from form data (HTMX hidden form submission).
        Returns HX-Refresh header to trigger page reload after successful reschedule.

        Args:
            request: FastHTML request with form data (uid, new_start)

        Returns:
            Empty response with HX-Refresh header on success, error message on failure
        """
        from starlette.responses import Response

        form_data = await request.form()
        uid = str(form_data.get("uid", ""))
        new_start_str = str(form_data.get("new_start", ""))

        if not uid:
            return Div(
                P("Missing item uid in request", cls="text-error"),
                id="reschedule-error",
            )

        if not new_start_str:
            return Div(
                P("Missing new_start in request", cls="text-error"),
                id="reschedule-error",
            )

        result = await calendar_service.reschedule_item(
            item_uid=uid,
            new_start=datetime.fromisoformat(new_start_str),
        )

        if result.is_ok:
            return Response(
                content="",
                headers={"HX-Refresh": "true"},
            )
        else:
            return Div(
                P(f"Failed to reschedule: {result.error}", cls="text-error"),
                id="reschedule-error",
            )
