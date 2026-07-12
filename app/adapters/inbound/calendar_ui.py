"""
Calendar UI Routes
==================

Page views and HTMX fragment endpoints for the calendar.

Routes:
    GET /events/calendar                                    — Redirect to current month
    GET /events/month/{year}/{month}                       — Month view shell
    GET /events/month/{year}/{month}/content               — Month grid fragment
    GET /events/week/{date_str}                            — Week view shell
    GET /events/week/{date_str}/content                    — Week grid fragment
    GET /events/day/{date_str}                             — Day view shell
    GET /events/day/{date_str}/content                     — Day timeline fragment
    GET /events/calendar/quick-create                      — HTMX quick-create form
    GET /events/calendar/habit/{habit_uid}/record/{status} — HTMX habit recording
    GET /events/calendar/item-details/{item_id}            — HTMX item-details modal
"""

import calendar as cal
from calendar import monthrange
from datetime import date, datetime
from typing import Any

from fasthtml.common import (
    H2,
    Div,
    P,
    Script,
)
from starlette.responses import RedirectResponse

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import safe_form_int, safe_form_string
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
from ui.activities.nav import render_activity_sidebar_page
from ui.calendar.components import (
    create_day_timeline,
    create_item_details_modal,
    create_month_grid,
    create_reschedule_form,
    create_view_switcher,
    create_week_grid,
    error_response,
)
from ui.components import Button, ButtonT
from ui.feedback import Alert, AlertT
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.modal import AlpineModal
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink

logger = get_logger("skuel.routes.calendar")


# ============================================================================
# PAGE WRAPPER HELPER
# ============================================================================


async def _wrap_calendar_page(request: Request, content: Any, title: str = "Calendar") -> Any:
    """Wrap calendar content in the activity sidebar page layout.

    title is intentionally not forwarded to render_activity_sidebar_page — that
    param controls the sidebar heading, which should stay "Tasks+" for consistency
    with the other activity domain pages. The period-specific title is already
    rendered by PageHeader inside content.
    """
    return await render_activity_sidebar_page(
        content=Div(content, **{"x-data": "calendarPage()"}),
        active="events",
        request=request,
        extra_css=["/static/css/calendar.css"],
        # Fluid width: the calendar grid should fill the content area and
        # absorb the space freed when the sidebar collapses.
        content_max_width="max-w-none",
    )


# Navigation aliases for internal use
_get_prev_month = prev_month
_get_next_month = next_month
_get_prev_week = prev_week
_get_next_week = next_week
_get_prev_day = prev_day
_get_next_day = next_day


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
        content = Div(
            Div(
                PageHeader(f"{month_name} {year}"),
                create_view_switcher("month", first_day),
                Div(
                    ButtonLink(
                        "← Previous",
                        href=f"/events/month/{prev_y}/{prev_m}",
                        cls=ButtonT.ghost,
                        size="sm",
                    ),
                    ButtonLink(
                        "Today",
                        href="/events/calendar",
                        cls=(ButtonT.primary, "mx-2"),
                        size="sm",
                    ),
                    ButtonLink(
                        "Next →",
                        href=f"/events/month/{next_y}/{next_m}",
                        cls=ButtonT.ghost,
                        size="sm",
                    ),
                    ButtonLink(
                        "📝",
                        href=f"/journals/monthly/{year}/{month}",
                        cls=(ButtonT.ghost, "ml-4"),
                        size="sm",
                        title="Monthly Note",
                    ),
                    cls="flex justify-center items-center mb-6",
                ),
                cls="mb-6",
            ),
            content_loading_placeholder(
                f"/events/month/{year}/{month}/content",
                "calendar-month-content",
                loading_text="Loading calendar...",
            ),
            create_reschedule_form(),
            cls="w-full",
        )
        return await _wrap_calendar_page(request, content, f"{month_name} {year}")

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
        week_start, _ = week_bounds(target_date)
        content = Div(
            Div(
                PageHeader(f"Week of {week_start.strftime('%B %d, %Y')}"),
                create_view_switcher("week", week_start),
                Div(
                    ButtonLink(
                        "← Previous Week",
                        href=f"/events/week/{_get_prev_week(week_start)}",
                        cls=ButtonT.ghost,
                        size="sm",
                    ),
                    ButtonLink(
                        "This Week",
                        href=f"/events/week/{date.today().isoformat()}",
                        cls=(ButtonT.primary, "mx-2"),
                        size="sm",
                    ),
                    ButtonLink(
                        "Next Week →",
                        href=f"/events/week/{_get_next_week(week_start)}",
                        cls=ButtonT.ghost,
                        size="sm",
                    ),
                    cls="flex justify-center mb-6",
                ),
                cls="mb-6",
            ),
            content_loading_placeholder(
                f"/events/week/{date_str}/content",
                "calendar-week-content",
                loading_text="Loading calendar...",
            ),
            create_reschedule_form(),
            cls="w-full",
        )
        return await _wrap_calendar_page(
            request, content, f"Week of {week_start.strftime('%B %d, %Y')}"
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
        """Day view shell — renders chrome immediately, timeline loads via HTMX."""
        require_authenticated_user(request)
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            target_date = date.today()
        # Day view is a vertical timeline of text cards — unlike the month/week
        # grids it reads better with a centered cap than at full fluid width.
        content = Div(
            Div(
                PageHeader(target_date.strftime("%A, %B %d, %Y")),
                create_view_switcher("day", target_date),
                Div(
                    ButtonLink(
                        "← Previous Day",
                        href=f"/events/day/{_get_prev_day(target_date)}",
                        cls=ButtonT.ghost,
                        size="sm",
                    ),
                    ButtonLink(
                        "Today",
                        href=f"/events/day/{date.today().isoformat()}",
                        cls=(ButtonT.primary, "mx-2"),
                        size="sm",
                    ),
                    ButtonLink(
                        "Next Day →",
                        href=f"/events/day/{_get_next_day(target_date)}",
                        cls=ButtonT.ghost,
                        size="sm",
                    ),
                    cls="flex justify-center mb-6",
                ),
                cls="mb-6",
            ),
            content_loading_placeholder(
                f"/events/day/{date_str}/content",
                "calendar-day-content",
                loading_text="Loading calendar...",
            ),
            create_reschedule_form(),
            cls="w-full max-w-5xl mx-auto",
        )
        return await _wrap_calendar_page(request, content, target_date.strftime("%A, %B %d, %Y"))

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

    @rt("/events/calendar/quick-create")
    @csrf_protected
    async def calendar_quick_create_htmx(request: Request) -> Any:
        """
        HTMX endpoint for quick create form.

        Accepts form data and returns HTML fragment for status display.
        """
        user_uid = require_authenticated_user(request)
        try:
            form_data = await request.form()

            item_type = safe_form_string(form_data.get("type"), "task")
            title = safe_form_string(form_data.get("title"))
            start_time_str = safe_form_string(form_data.get("start_time"))
            duration = safe_form_int(form_data.get("duration"), 60)

            # Validation
            if not title:
                return Alert(
                    P("Please enter a title", cls="text-sm"),
                    variant=AlertT.error,
                )

            if not start_time_str:
                return Alert(
                    P("Please select a date and time", cls="text-sm"),
                    variant=AlertT.error,
                )

            # Parse datetime
            start_time = datetime.fromisoformat(start_time_str)

            # Create the item
            result = await calendar_service.quick_create(
                user_uid=user_uid,
                item_type=item_type,
                title=title,
                start_time=start_time,
                duration=duration,
            )

            if result.is_ok:
                # Success - show message and trigger page reload
                return Div(
                    Alert(
                        P(
                            f"✓ {item_type.title()} created successfully!",
                            cls="font-medium",
                        ),
                        P("Refreshing calendar...", cls="text-sm opacity-70"),
                        variant=AlertT.success,
                        cls="mb-4",
                    ),
                    # Auto-reload after brief delay
                    Script("setTimeout(() => window.location.reload(), 1000);"),
                )
            else:
                return Alert(
                    P(f"Failed to create: {result.error}", cls="text-sm"),
                    variant=AlertT.error,
                )

        except ValueError as e:
            return Alert(
                P(f"Invalid input: {e}", cls="text-sm"),
                variant=AlertT.error,
            )
        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Quick create error: {e}")
            return Alert(
                P(f"Error: {e}", cls="text-sm"),
                variant=AlertT.error,
            )

    @rt("/events/calendar/habit/{habit_uid}/record/{status}")
    @csrf_protected
    async def calendar_habit_record(request: Request, habit_uid: str, status: str) -> Any:
        """
        HTMX endpoint for recording habit occurrences.

        Args:
            habit_uid: The habit UID
            status: One of 'done', 'skipped', 'missed'
        """
        user_uid = require_authenticated_user(request)
        try:
            form_data = await request.form()
            notes = safe_form_string(form_data.get("notes"))

            # Validate status
            valid_statuses = {"done", "skipped", "missed"}
            if status.lower() not in valid_statuses:
                return Alert(
                    P(f"Invalid status: {status}", cls="text-sm"),
                    variant=AlertT.error,
                )

            # Get today's date
            today = date.today().isoformat()

            # Record the occurrence via calendar service
            result = await calendar_service.record_habit_occurrence(
                user_uid=user_uid,
                habit_uid=habit_uid,
                on_date=today,
                status=status.upper(),
                notes=notes or None,
            )

            if result.is_ok:
                status_icons = {"done": "✅", "skipped": "⏭️", "missed": "❌"}
                status_variants = {
                    "done": AlertT.success,
                    "skipped": AlertT.warning,
                    "missed": AlertT.error,
                }
                icon = status_icons.get(status.lower(), "✓")
                variant = status_variants.get(status.lower(), AlertT.info)

                return Alert(
                    P(
                        f"{icon} Recorded as {status}!",
                        cls="text-sm font-medium",
                    ),
                    variant=variant,
                )
            else:
                return Alert(
                    P(f"Failed: {result.error}", cls="text-sm"),
                    variant=AlertT.error,
                )

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Habit record error: {e}")
            return Alert(
                P(f"Error: {e}", cls="text-sm"),
                variant=AlertT.error,
            )

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
