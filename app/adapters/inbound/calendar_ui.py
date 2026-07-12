"""
Calendar UI Routes
==================

Page views and HTMX fragment endpoints for the calendar.

Routes:
    GET /events/calendar                                    — Redirect to current month
    GET /events/month/{year}/{month}                       — Month view shell
    GET /events/month/{year}/{month}/content               — Month grid fragment
    GET /events/week/{date_str}                            — Week view shell
    GET /events/week/{date_str}/content                    — Week agenda fragment
    GET /events/day/{date_str}                             — Day view shell
    GET /events/day/{date_str}/content                     — Day agenda fragment
    GET /events/calendar/item-details/{item_id}            — HTMX item-details modal
"""

import calendar as cal
from calendar import monthrange
from datetime import date
from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H2,
    Div,
    P,
)
from starlette.responses import RedirectResponse

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request

if TYPE_CHECKING:
    from fasthtml.common import FT
from core.models.event.calendar_models import CalendarView
from core.utils.logging import get_logger
from core.utils.timestamp_helpers import (
    next_day,
    next_month,
    next_week,
    prev_day,
    prev_month,
    prev_week,
    week_bounds,
)
from ui.calendar.components import (
    create_calendar_header,
    create_calendar_toolbar,
    create_day_timeline,
    create_item_details_modal,
    create_month_grid,
    create_week_grid,
    error_response,
)
from ui.components import Button, ButtonT
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.modal import AlpineModal

logger = get_logger("skuel.routes.calendar")


# ============================================================================
# PAGE WRAPPER HELPER
# ============================================================================


async def _wrap_calendar_page(request: Request, content: Any, title: str = "Calendar") -> Any:
    """Wrap calendar content in a navbar-only, full-width page.

    Calendar views skip the activity sidebar — the legend/chips already surface
    the activity domains, and the freed width goes to the grid. BasePage(CUSTOM)
    provides no container padding, so the wrapper supplies the same padding the
    sidebar layout used to.
    """
    return await BasePage(
        content=Div(content, cls="w-full px-4 sm:px-6 lg:px-8 py-4 lg:py-6"),
        title=title,
        page_type=PageType.CUSTOM,
        request=request,
        # "tasks" lights the Tasks+ navbar item — the calendar's nav family now
        # that the sidebar no longer carries the active state ("activity"
        # matched no top-nav key).
        active_page="tasks",
        extra_css=["/static/css/calendar.css"],
    )


# Navigation aliases for internal use
_get_prev_month = prev_month
_get_next_month = next_month
_get_prev_week = prev_week
_get_next_week = next_week
_get_prev_day = prev_day
_get_next_day = next_day


def _week_title(week_start: date, week_end: date) -> str:
    """Range label: 'Week of Jul 6 - 12' same month, 'Week of Jun 30 - Jul 6' across."""
    start = f"{week_start.strftime('%b')} {week_start.day}"
    end = (
        str(week_end.day)
        if week_start.month == week_end.month
        else f"{week_end.strftime('%b')} {week_end.day}"
    )
    return f"Week of {start} – {end}"


async def _calendar_shell(
    request: Request,
    *,
    current_view: str,
    title: str,
    target_date: date,
    prev_href: str,
    next_href: str,
    today_href: str,
    monthly_note_href: str,
    content_route: str,
    content_id: str,
    max_width: str = "",
) -> "FT":
    """Assemble the shared calendar chrome (header + toolbar) around an HTMX-loaded grid.

    The grid loads lazily via ``content_loading_placeholder`` so each view renders its
    chrome immediately. ``max_width`` narrows/centers the inner content (Day agenda);
    Month/Week stay fluid at full page width.
    """
    # calendarLegend (skuel.js) owns the legend's type filters: it toggles
    # cal-hide-*/cal-spot-* classes here, on the persistent shell, so the pure-CSS
    # hiding (calendar.css) survives HTMX grid swaps without any re-init.
    content = Div(
        create_calendar_header(title),
        create_calendar_toolbar(
            current_view,
            target_date,
            prev_href,
            next_href,
            today_href,
            monthly_note_href,
        ),
        content_loading_placeholder(
            content_route,
            content_id,
            loading_text="Loading calendar...",
        ),
        cls=f"w-full {max_width}".strip(),
        x_data="calendarLegend",
        **{":class": "filterClasses()"},
    )
    return await _wrap_calendar_page(request, content, title)


# ============================================================================
# ROUTE FACTORY
# ============================================================================


def create_calendar_ui_routes(_app, rt, calendar_service):
    """Register calendar page and HTMX fragment routes."""

    @rt("/events/calendar")
    async def calendar_today(request: Request) -> Any:
        """Entry point — redirect to current month calendar view."""
        require_authenticated_user(request)
        today = date.today()
        return RedirectResponse(f"/events/month/{today.year}/{today.month}", status_code=302)

    @rt("/events/month/{year}/{month}")
    async def calendar_month(request: Request, year: int, month: int) -> Any:
        """Month view shell — renders chrome immediately, grid loads via HTMX."""
        require_authenticated_user(request)
        first_day = date(year, month, 1)
        month_name = cal.month_name[month]
        prev_y, prev_m = _get_prev_month(year, month)
        next_y, next_m = _get_next_month(year, month)
        return await _calendar_shell(
            request,
            current_view="month",
            title=f"{month_name} {year}",
            target_date=first_day,
            prev_href=f"/events/month/{prev_y}/{prev_m}",
            next_href=f"/events/month/{next_y}/{next_m}",
            today_href="/events/calendar",
            monthly_note_href=f"/journals/monthly/{year}/{month}",
            content_route=f"/events/month/{year}/{month}/content",
            content_id="calendar-month-content",
        )

    @rt("/events/month/{year}/{month}/content")
    async def calendar_month_content(request: Request, year: int, month: int) -> Any:
        """HTMX fragment: month grid."""
        user_uid = require_authenticated_user(request)
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])
        result = await calendar_service.get_calendar_view(
            user_uid=user_uid,
            start_date=first_day,
            end_date=last_day,
            view_type=CalendarView.MONTH,
        )
        if not result.is_ok:
            return Div(error_response(result.error), id="calendar-month-content")
        return Div(create_month_grid(result.value), id="calendar-month-content")

    @rt("/events/week/{date_str}")
    async def calendar_week(request: Request, date_str: str) -> Any:
        """Week view shell — renders chrome immediately, grid loads via HTMX."""
        require_authenticated_user(request)
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            target_date = date.today()
        week_start, week_end = week_bounds(target_date)
        return await _calendar_shell(
            request,
            current_view="week",
            title=_week_title(week_start, week_end),
            target_date=week_start,
            prev_href=f"/events/week/{_get_prev_week(week_start)}",
            next_href=f"/events/week/{_get_next_week(week_start)}",
            today_href=f"/events/week/{date.today().isoformat()}",
            monthly_note_href=f"/journals/monthly/{week_start.year}/{week_start.month}",
            content_route=f"/events/week/{date_str}/content",
            content_id="calendar-week-content",
        )

    @rt("/events/week/{date_str}/content")
    async def calendar_week_content(request: Request, date_str: str) -> Any:
        """HTMX fragment: week grid."""
        user_uid = require_authenticated_user(request)
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            target_date = date.today()
        week_start, week_end = week_bounds(target_date)
        result = await calendar_service.get_calendar_view(
            user_uid=user_uid,
            start_date=week_start,
            end_date=week_end,
            view_type=CalendarView.WEEK,
        )
        if not result.is_ok:
            return Div(error_response(result.error), id="calendar-week-content")
        return Div(create_week_grid(result.value), id="calendar-week-content")

    @rt("/events/day/{date_str}")
    async def calendar_day(request: Request, date_str: str) -> Any:
        """Day view shell — renders chrome immediately, agenda loads via HTMX."""
        require_authenticated_user(request)
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            target_date = date.today()
        # Day view is a vertical agenda list — it reads better with a centered cap
        # than at full fluid width.
        return await _calendar_shell(
            request,
            current_view="day",
            title=f"{target_date.strftime('%A, %B')} {target_date.day}",
            target_date=target_date,
            prev_href=f"/events/day/{_get_prev_day(target_date)}",
            next_href=f"/events/day/{_get_next_day(target_date)}",
            today_href=f"/events/day/{date.today().isoformat()}",
            monthly_note_href=f"/journals/monthly/{target_date.year}/{target_date.month}",
            content_route=f"/events/day/{date_str}/content",
            content_id="calendar-day-content",
            max_width="max-w-3xl mx-auto",
        )

    @rt("/events/day/{date_str}/content")
    async def calendar_day_content(request: Request, date_str: str) -> Any:
        """HTMX fragment: day timeline."""
        user_uid = require_authenticated_user(request)
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            target_date = date.today()
        result = await calendar_service.get_calendar_view(
            user_uid=user_uid,
            start_date=target_date,
            end_date=target_date,
            view_type=CalendarView.DAY,
        )
        if not result.is_ok:
            return Div(error_response(result.error), id="calendar-day-content")
        return Div(create_day_timeline(result.value), id="calendar-day-content")

    # =========================================================================
    # HTMX Fragment Routes
    # =========================================================================

    @rt("/events/calendar/item-details/{item_id}")
    async def calendar_item_details_modal(request: Request, item_id: str) -> Any:
        """
        HTMX endpoint for calendar item details modal.

        Returns HTML fragment instead of JSON for direct DOM insertion.
        """
        user_uid = require_authenticated_user(request)
        result = await calendar_service.get_item(user_uid, item_id)

        if result.is_ok and result.value:
            return create_item_details_modal(result.value)

        # Error state
        close_expr = (
            "open = false; $nextTick(() => document.getElementById('item-details-modal')?.remove())"
        )
        return Div(
            AlpineModal(
                H2("Error", cls="text-xl font-bold text-error mb-2"),
                P("Calendar item not found", cls="text-muted-foreground"),
                Button(
                    "Close",
                    cls=(ButtonT.ghost, "mt-4"),
                    **{
                        "x-on:click": close_expr
                    },  # fasthtml dynamic-attr splat: Alpine colon attr has no underscore-kwarg form
                ),
                show="open",
                close=close_expr,
                max_width="max-w-md",
            ),
            x_data="{ open: true }",
            id="item-details-modal",
        )
