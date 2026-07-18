"""
Shared UI helpers for inbound route factories.
"""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import date
from logging import Logger
from typing import Any

from starlette.responses import Response

from adapters.inbound.fasthtml_types import Request
from core.models.type_hints import UserUID
from core.utils.result_simplified import Errors, Result


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


def render_entity_not_found_page(
    entity_label: str,
    uid: str,
    domain_slug: str,
    request: Request,
) -> Any:
    """Render a standard "Entity Not Found" full page for detail views.

    Args:
        entity_label: Display name, e.g. "Task", "Goal"
        uid: The entity UID that was not found
        domain_slug: URL path segment, e.g. "tasks", "goals"
        request: The Starlette request (passed to BasePage)
    """
    from fasthtml.common import P

    from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle
    from ui.layouts.base_page import BasePage
    from ui.layouts.page_types import PageType

    return BasePage(
        content=Card(
            CardHeader(CardTitle(f"{entity_label} Not Found", cls="text-error")),
            CardBody(
                P(f"Could not find {entity_label.lower()}: {uid}", cls="text-muted-foreground"),
                Button(
                    f"← Back to {entity_label}s",
                    hx_get=f"/{domain_slug}",
                    hx_target="body",
                    cls=(ButtonT.primary, "mt-4"),
                ),
            ),
        ),
        title=f"{entity_label} Not Found",
        page_type=PageType.STANDARD,
        request=request,
        active_page=domain_slug,
    )


async def render_dashboard_error_page(
    title: str,
    subtitle: str,
    error_message: str,
    view: str,
    render_view_tabs: Callable[..., Any],
    page_creator: Callable[..., Coroutine[Any, Any, Any]],
    request: Request,
) -> Any:
    """Render a standard error page for activity domain dashboards.

    Builds the standard error layout (PageHeader + view tabs + error banner)
    and passes it to the domain's page_creator.

    Args:
        title: Page title, e.g. "Tasks"
        subtitle: Page subtitle, e.g. "Manage your daily tasks"
        error_message: Error message for the banner, e.g. "Failed to load tasks"
        view: Active view tab, e.g. "list"
        render_view_tabs: Domain's view tab renderer (called with active_view kwarg)
        page_creator: Domain's page creator coroutine (called with content + request)
        request: The Starlette request
    """
    from fasthtml.common import Div

    from ui.patterns.error_banner import render_error_banner
    from ui.patterns.page_header import PageHeader
    from ui.tokens import Container, Spacing

    error_content = Div(
        PageHeader(title, subtitle=subtitle),
        render_view_tabs(active_view=view),
        render_error_banner(error_message),
        cls=f"{Spacing.PAGE} {Container.WIDE}",
    )
    return await page_creator(error_content, request=request)


async def fetch_user_entities(
    service_method: Callable[[str], Coroutine[Any, Any, Result[list[Any]]]] | None,
    domain_name: str,
    user_uid: UserUID,
    logger: Logger,
) -> Result[list[Any]]:
    """Fetch all entities for a user with consistent error handling.

    Args:
        service_method: Bound method like ``service.get_user_goals``, or None
        domain_name: For log messages, e.g. "goals"
        user_uid: Authenticated user UID
        logger: Logger instance for structured error logging
    """
    try:
        if service_method is None:
            return Result.ok([])
        result = await service_method(user_uid)
        if result.is_error:
            logger.warning(f"Failed to fetch {domain_name}: {result.error}")
            return result
        return Result.ok(result.value or [])
    except Exception as e:  # safety-net: service call may raise unexpected errors
        logger.error(
            f"Error fetching all {domain_name}",
            extra={
                "user_uid": user_uid,
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
        )
        return Result.fail(Errors.system(f"Failed to fetch {domain_name}: {e}"))
