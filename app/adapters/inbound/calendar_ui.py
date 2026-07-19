"""
Calendar UI Routes
==================

Page views and HTMX fragment endpoints for the calendar.

The calendar is a cross-cutting system (it aggregates Tasks, Events, Habits,
and Milestones), so it lives under its own ``/cal/`` prefix — not under the
Events activity domain's ``/events/`` routes.

Routes:
    GET  /cal                                — Redirect to current month
    GET  /cal/month                          — Redirect to current month (sidebar link)
    GET  /cal/month/{year}/{month}           — Month view shell
    GET  /cal/month/{year}/{month}/content   — Month grid fragment
    GET  /cal/week                           — Redirect to current week (sidebar link)
    GET  /cal/week/{date_str}                — Week view shell
    GET  /cal/week/{date_str}/content        — Week agenda fragment
    GET  /cal/item-details/{item_id}         — HTMX item-details modal
    POST /cal/habit/{habit_uid}/complete     — Record today's habit completion
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
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.route_factories import require_owned_entity

if TYPE_CHECKING:
    from fasthtml.common import FT
from core.models.event.calendar_models import CalendarView
from core.utils.logging import get_logger
from core.utils.timestamp_helpers import (
    next_month,
    next_week,
    prev_month,
    prev_week,
    week_bounds,
)
from ui.activities.nav import render_activity_sidebar_page
from ui.calendar.components import (
    create_calendar_header,
    create_calendar_toolbar,
    create_item_details_modal,
    create_month_grid,
    create_week_grid,
    error_response,
)
from ui.components import Button, ButtonT
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.modal import AlpineModal

logger = get_logger("skuel.routes.calendar")


# ============================================================================
# PAGE WRAPPER HELPER
# ============================================================================


def _wrap_calendar_page(request: Request, content: Any, title: str, active: str) -> Any:
    """Wrap calendar content in the shared activity sidebar page (same as Today).

    ``active`` highlights the view's sidebar link ("weekly" / "monthly");
    ``max-w-none`` lets the grid use the full width freed by a collapsed sidebar.
    """
    return render_activity_sidebar_page(
        content=content,
        active=active,
        request=request,
        extra_css=["/static/css/calendar.css"],
        title=title,
        # "calendar" lights the navbar calendar icon.
        active_page="calendar",
        content_max_width="max-w-none",
    )


# Navigation aliases for internal use
_get_prev_month = prev_month
_get_next_month = next_month
_get_prev_week = prev_week
_get_next_week = next_week


def _week_title(week_start: date, week_end: date) -> str:
    """Range label: 'Week of Jul 6 - 12' same month, 'Week of Jun 30 - Jul 6' across."""
    start = f"{week_start.strftime('%b')} {week_start.day}"
    end = (
        str(week_end.day)
        if week_start.month == week_end.month
        else f"{week_end.strftime('%b')} {week_end.day}"
    )
    return f"Week of {start} – {end}"


def _calendar_shell(
    request: Request,
    *,
    active: str,
    title: str,
    prev_href: str,
    next_href: str,
    today_href: str,
    note_href: str,
    note_label: str,
    content_route: str,
    content_id: str,
) -> "FT":
    """Assemble the shared calendar chrome (header + toolbar) around an HTMX-loaded grid.

    The grid loads lazily via ``content_loading_placeholder`` so each view renders its
    chrome immediately.
    """
    # calendarLegend (skuel.js) owns the legend's type filters: it toggles
    # cal-hide-*/cal-spot-* classes here, on the persistent shell, so the pure-CSS
    # hiding (calendar.css) survives HTMX grid swaps without any re-init.
    content = Div(
        create_calendar_header(title),
        create_calendar_toolbar(
            prev_href,
            next_href,
            today_href,
            note_href,
            note_label,
        ),
        content_loading_placeholder(
            content_route,
            content_id,
            loading_text="Loading calendar...",
        ),
        cls="w-full",
        x_data="calendarLegend",
        **{":class": "filterClasses()"},
    )
    return _wrap_calendar_page(request, content, title, active)


# ============================================================================
# ROUTE FACTORY
# ============================================================================


def create_calendar_ui_routes(_app, rt, calendar_service, habits_service):
    """Register calendar page and HTMX fragment routes."""

    @rt("/cal")
    def calendar_today(
        request: Request,
    ) -> Any:
        """Entry point — redirect to current month calendar view."""
        require_authenticated_user(request)
        today = date.today()
        return RedirectResponse(f"/cal/month/{today.year}/{today.month}", status_code=302)

    @rt("/cal/month")
    def calendar_month_current(request: Request) -> Any:
        """Sidebar "Monthly" link — redirect to the current month."""
        require_authenticated_user(request)
        today = date.today()
        return RedirectResponse(f"/cal/month/{today.year}/{today.month}", status_code=302)

    @rt("/cal/week")
    def calendar_week_current(request: Request) -> Any:
        """Sidebar "Weekly" link — redirect to the current week."""
        require_authenticated_user(request)
        return RedirectResponse(f"/cal/week/{date.today().isoformat()}", status_code=302)

    @rt("/cal/month/{year}/{month}")
    def calendar_month(request: Request, year: int, month: int) -> Any:
        """Month view shell — renders chrome immediately, grid loads via HTMX."""
        require_authenticated_user(request)
        month_name = cal.month_name[month]
        prev_y, prev_m = _get_prev_month(year, month)
        next_y, next_m = _get_next_month(year, month)
        return _calendar_shell(
            request,
            active="monthly",
            title=f"{month_name} {year}",
            prev_href=f"/cal/month/{prev_y}/{prev_m}",
            next_href=f"/cal/month/{next_y}/{next_m}",
            today_href="/cal",
            note_href=f"/journals/monthly/{year}/{month}",
            note_label="Monthly note",
            content_route=f"/cal/month/{year}/{month}/content",
            content_id="calendar-month-content",
        )

    @rt("/cal/month/{year}/{month}/content")
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

    @rt("/cal/week/{date_str}")
    def calendar_week(request: Request, date_str: str) -> Any:
        """Week view shell — renders chrome immediately, grid loads via HTMX."""
        require_authenticated_user(request)
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            target_date = date.today()
        week_start, week_end = week_bounds(target_date)
        iso_year, iso_week, _ = week_start.isocalendar()
        return _calendar_shell(
            request,
            active="weekly",
            title=_week_title(week_start, week_end),
            prev_href=f"/cal/week/{_get_prev_week(week_start)}",
            next_href=f"/cal/week/{_get_next_week(week_start)}",
            today_href=f"/cal/week/{date.today().isoformat()}",
            note_href=f"/journals/weekly/{iso_year}/{iso_week}",
            note_label="Weekly note",
            content_route=f"/cal/week/{date_str}/content",
            content_id="calendar-week-content",
        )

    @rt("/cal/week/{date_str}/content")
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

    # =========================================================================
    # HTMX Fragment Routes
    # =========================================================================

    @rt("/cal/item-details/{item_id}")
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

    @rt("/cal/habit/{habit_uid}/complete", methods=["POST"])
    @csrf_protected
    async def calendar_habit_complete(request: Request, habit_uid: str) -> Any:
        """Record today's completion for a habit from the item-details modal.

        Backend: HabitsCompletionService.record_completion. The response swaps
        the modal's "Mark Complete" button (hx_swap="outerHTML").
        """
        user_uid = require_authenticated_user(request)
        _habit, error = await require_owned_entity(
            habits_service and habits_service.core, habit_uid, user_uid, "Habit"
        )
        if error:
            return error
        result = await habits_service.completions.record_completion(habit_uid, user_uid)
        if result.is_error:
            # Keep the hx attrs so the swapped-in button can retry.
            return Button(
                "Completion failed — try again",
                cls=(ButtonT.secondary, "mr-2"),
                hx_post=f"/cal/habit/{habit_uid}/complete",
                hx_swap="outerHTML",
            )
        return Button("Completed ✓", disabled=True, cls=(ButtonT.secondary, "mr-2"))
