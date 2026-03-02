"""
Shared UI helpers for inbound route factories.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from starlette.requests import Request
from starlette.responses import Response


@dataclass
class CalendarParams:
    """Typed params for calendar view."""

    calendar_view: str
    current_date: date


def parse_calendar_params(request: Request) -> CalendarParams:
    """Extract calendar view parameters from request query params."""
    calendar_view = request.query_params.get("calendar_view", "month")
    date_str = request.query_params.get("date", "")

    # Parse date or use today
    try:
        current_date = date.fromisoformat(date_str) if date_str else date.today()
    except ValueError:
        current_date = date.today()

    return CalendarParams(calendar_view=calendar_view, current_date=current_date)


def render_safe_error_response(
    user_message: str,
    error_context: Any,
    logger_instance: Any,  # boundary: Logger has no type stubs
    log_extra: dict[str, Any],
    status_code: int = 500,
) -> Response:
    """
    Return sanitized error to client, log detailed error server-side.

    Args:
        user_message: Safe message for client
        error_context: Detailed error (logged but NOT sent to client)
        logger_instance: Logger instance for structured logging
        log_extra: Additional context for logs (user_uid, entity_uid, etc.)
        status_code: HTTP status code

    Returns:
        Response with sanitized message
    """
    # Log detailed error server-side
    logger_instance.error(
        user_message,
        extra={
            **log_extra,
            "error_type": type(error_context).__name__,
            "error_detail": str(error_context),
        },
    )

    # Return safe message to client
    return Response(user_message, status_code=status_code)
