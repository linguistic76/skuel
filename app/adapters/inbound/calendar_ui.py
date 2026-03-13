"""
Calendar UI Routes
==================

Page views and HTMX fragment endpoints for the calendar.

Routes:
    GET /events                                            — Default (current month)
    GET /events/month/{year}/{month}                       — Month view
    GET /events/week/{date_str}                            — Week view
    GET /events/day/{date_str}                             — Day view
    GET /events/calendar/quick-create                      — HTMX quick-create form
    GET /events/calendar/habit/{habit_uid}/record/{status} — HTMX habit recording
    GET /events/calendar/item-details/{item_id}            — HTMX item-details modal
"""

import calendar as cal
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any

from fasthtml.common import (
    H1,
    H2,
    Body,
    Container,
    Div,
    Head,
    Html,
    Link,
    Meta,
    NotStr,
    P,
    Script,
    Span,
    Title,
)
from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from core.models.event.calendar_models import CalendarView
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonLink, ButtonT
from ui.calendar.components import (
    create_day_timeline,
    create_month_grid,
    create_reschedule_form,
    create_view_switcher,
    create_week_grid,
    error_response,
)
from ui.feedback import Alert, AlertT, Badge, BadgeT
from ui.layout import Size
from ui.layouts.navbar import create_navbar_for_request

logger = get_logger("skuel.routes.calendar")


# ============================================================================
# PAGE WRAPPER HELPER
# ============================================================================


def _wrap_calendar_page(navbar: Any, content: Any, title: str = "Calendar") -> Any:
    """Wrap calendar content in complete HTML document.

    This ensures proper document structure for navigation to work correctly.
    """
    return Html(
        Head(
            Meta(charset="UTF-8"),
            Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
            Title(f"{title} - SKUEL"),
            Link(rel="stylesheet", href="/static/css/output.css"),
            Link(rel="stylesheet", href="/static/css/calendar.css"),
            Script(src="https://unpkg.com/htmx.org@1.9.6/dist/htmx.min.js"),
            Script(src="/static/vendor/alpinejs/alpine.3.14.8.min.js", defer=True),
            Script(src="/static/js/skuel.js"),
        ),
        Body(
            navbar,
            content,
            cls="bg-background min-h-screen",
            **{"x-data": "calendarPage()"},
        ),
    )


# ============================================================================
# NAVIGATION HELPERS
# ============================================================================


def _get_prev_month(year: int, month: int) -> tuple[int, int]:
    """Calculate previous month year and month."""
    if month == 1:
        return (year - 1, 12)
    return (year, month - 1)


def _get_next_month(year: int, month: int) -> tuple[int, int]:
    """Calculate next month year and month."""
    if month == 12:
        return (year + 1, 1)
    return (year, month + 1)


def _get_prev_week(d: date) -> str:
    """Calculate previous week ISO date string."""
    return (d - timedelta(days=7)).isoformat()


def _get_next_week(d: date) -> str:
    """Calculate next week ISO date string."""
    return (d + timedelta(days=7)).isoformat()


def _get_prev_day(d: date) -> str:
    """Calculate previous day ISO date string."""
    return (d - timedelta(days=1)).isoformat()


def _get_next_day(d: date) -> str:
    """Calculate next day ISO date string."""
    return (d + timedelta(days=1)).isoformat()


# ============================================================================
# HTMX FRAGMENT RENDERING
# ============================================================================


def _format_datetime(dt: datetime) -> str:
    """Format datetime for display."""
    return dt.strftime("%b %d, %I:%M %p")


def _render_item_details_modal(item: Any) -> Div:
    """
    Render calendar item details as an HTMX modal fragment.

    Returns server-rendered HTML instead of JSON for HTMX swap.
    """
    # Type badge
    type_badge = Span(
        item.item_type.value.replace("_", " ").upper(),
        cls="px-3 py-1 rounded-full text-xs font-medium",
        style=f"background-color: {item.color}20; color: {item.color}",
    )

    # Priority stars
    priority_stars = ""
    if item.priority:
        priority_stars = Span(
            "⭐" * item.priority,
            cls="text-sm text-muted-foreground ml-4",
        )

    # Schedule info
    schedule_text = (
        "All Day"
        if item.all_day
        else f"{_format_datetime(item.start_time)} - {_format_datetime(item.end_time)}"
    )

    recurrence_info = None
    if item.is_recurring:
        recurrence_info = P(
            f"🔁 Recurring: {item.recurrence_pattern}",
            cls="text-sm text-muted-foreground mt-1",
        )

    # Description section
    description_section = None
    if item.description:
        description_section = Div(
            P("Description", cls="text-sm font-semibold text-muted-foreground mb-2"),
            P(item.description, cls="text-muted-foreground"),
            cls="mb-4",
        )

    # Event-specific info (location, attendees)
    event_info = None
    if item.item_type.value == "event":
        event_details = []
        if item.location:
            event_details.append(
                P(
                    Span("📍 Location:", cls="font-semibold text-muted-foreground"),
                    Span(item.location, cls="text-muted-foreground ml-2"),
                    cls="text-sm mb-2",
                )
            )
        if item.is_online:
            event_details.append(
                P(
                    Span("💻 Format:", cls="font-semibold text-muted-foreground"),
                    Span("Online Meeting", cls="text-muted-foreground ml-2"),
                    cls="text-sm mb-2",
                )
            )
        if len(item.attendee_emails) > 0:
            attendee_badges = [
                Span(
                    email,
                    cls="px-2 py-1 bg-background border border-info/20 text-info rounded text-xs mr-1 mb-1",
                )
                for email in list(item.attendee_emails)[:5]
            ]
            event_details.append(
                Div(
                    P(
                        f"👥 Attendees ({len(item.attendee_emails)}"
                        + (f"/{item.max_attendees})" if item.max_attendees else ")"),
                        cls="text-sm font-semibold text-muted-foreground mb-1",
                    ),
                    Div(*attendee_badges, cls="flex flex-wrap"),
                    cls="mt-2",
                )
            )
        if event_details:
            event_info = Div(*event_details, cls="bg-info/10 p-4 rounded-lg mb-4")

    # Habit streak info
    habit_info = None
    if item.item_type.value == "habit" and item.streak_count is not None:
        habit_info = Div(
            P(
                f"Current Streak: {item.streak_count} days 🔥",
                cls="text-sm font-semibold text-success",
            ),
            cls="bg-success/10 p-4 rounded-lg mb-4",
        )

    # Tags
    tags_section = None
    if item.tags:
        tag_badges = [
            Badge(tag, variant=BadgeT.info, size=Size.sm, cls="mr-1") for tag in item.tags
        ]
        tags_section = Div(
            P("Tags", cls="text-sm font-semibold text-muted-foreground mb-2"),
            Div(*tag_badges, cls="flex flex-wrap"),
            cls="mb-4",
        )

    # Action buttons based on type
    action_buttons = [
        Button(
            "Close",
            variant=ButtonT.ghost,
            onclick="document.getElementById('item-details-modal').remove()",
        )
    ]

    if item.item_type.value in ("task_work", "task_deadline"):
        action_buttons.insert(
            0,
            ButtonLink(
                "Edit Task",
                href=f"/tasks/{item.source_uid}/edit",
                variant=ButtonT.primary,
                cls="mr-2",
            ),
        )
    elif item.item_type.value == "event":
        action_buttons.insert(
            0,
            ButtonLink(
                "Edit Event",
                href=f"/events/{item.source_uid}/edit",
                variant=ButtonT.success,
                cls="mr-2",
            ),
        )
    elif item.item_type.value == "habit":
        action_buttons.insert(
            0,
            Button(
                "Mark Complete",
                variant=ButtonT.secondary,
                cls="mr-2",
                **{
                    "hx-post": f"/events/calendar/habit/{item.source_uid}/complete",
                    "hx-swap": "none",
                },
            ),
        )

    return Div(
        Div(
            Div(
                # Header with title and close button
                Div(
                    H2(
                        Span(item.icon or "📅", cls="mr-2"),
                        item.title,
                        cls="text-2xl font-bold flex items-center",
                    ),
                    Button(
                        NotStr(
                            '<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
                            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>'
                            "</svg>"
                        ),
                        variant=ButtonT.ghost,
                        size=Size.sm,
                        cls="text-muted-foreground hover:text-muted-foreground",
                        onclick="document.getElementById('item-details-modal').remove()",
                    ),
                    cls="flex justify-between items-start mb-4",
                ),
                # Type and priority
                Div(type_badge, priority_stars, cls="flex items-center space-x-4 mb-4"),
                # Schedule
                Div(
                    P("Schedule", cls="text-sm font-semibold text-muted-foreground mb-2"),
                    P(schedule_text, cls="text-sm text-muted-foreground"),
                    recurrence_info,
                    cls="bg-muted p-4 rounded-lg mb-4",
                ),
                # Description
                description_section,
                # Event info
                event_info,
                # Habit info
                habit_info,
                # Tags
                tags_section,
                # Actions
                Div(*action_buttons, cls="flex pt-4 border-t"),
                cls="bg-background rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto",
            ),
            cls="fixed inset-0 flex items-center justify-center bg-black bg-opacity-50 z-50",
            onclick="if(event.target === this) document.getElementById('item-details-modal').remove()",
        ),
        id="item-details-modal",
    )


# ============================================================================
# ROUTE FACTORY
# ============================================================================


def create_calendar_ui_routes(_app, rt, calendar_service, habits_service=None):
    """Register calendar page and HTMX fragment routes."""

    @rt("/events/month/{year}/{month}")
    async def calendar_month(request: Request, year: int, month: int) -> Any:
        """Month view of the calendar."""
        user_uid = require_authenticated_user(request)  # Enforce authentication

        # Calculate date range for the month
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])

        # Get calendar data
        result = await calendar_service.get_calendar_view(
            user_uid=user_uid,
            start_date=first_day,
            end_date=last_day,
            view_type=CalendarView.MONTH,
        )

        if not result.is_ok:
            return error_response(result.error)

        calendar_data = result.value
        month_name = cal.month_name[month]
        navbar = await create_navbar_for_request(request, active_page="events")

        return _wrap_calendar_page(
            navbar,
            Div(
                Container(
                    # Header with navigation
                    Div(
                        H1(f"{month_name} {year}", cls="text-3xl font-bold mb-4"),
                        create_view_switcher("month", first_day),
                        # Month navigation - using links instead of JavaScript
                        Div(
                            ButtonLink(
                                "← Previous",
                                href=f"/events/month/{_get_prev_month(year, month)[0]}/{_get_prev_month(year, month)[1]}",
                                variant=ButtonT.ghost,
                                size=Size.sm,
                            ),
                            ButtonLink(
                                "Today",
                                href="/events",
                                variant=ButtonT.primary,
                                size=Size.sm,
                                cls="mx-2",
                            ),
                            ButtonLink(
                                "Next →",
                                href=f"/events/month/{_get_next_month(year, month)[0]}/{_get_next_month(year, month)[1]}",
                                variant=ButtonT.ghost,
                                size=Size.sm,
                            ),
                            cls="flex justify-center mb-6",
                        ),
                        cls="mb-6",
                    ),
                    # Month grid
                    create_month_grid(calendar_data),
                    # Hidden form for HTMX drag-drop reschedule
                    create_reschedule_form(),
                ),
                cls="max-w-7xl mx-auto p-6",
            ),
            f"{month_name} {year}",
        )

    @rt("/events")
    async def calendar_default(request: Request) -> Any:
        """Default calendar view - redirects to current month."""
        today = date.today()
        return await calendar_month(request, today.year, today.month)

    @rt("/events/week/{date_str}")
    async def calendar_week(request: Request, date_str: str) -> Any:
        """Week view of the calendar."""
        user_uid = require_authenticated_user(request)  # Enforce authentication

        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            target_date = date.today()

        # Calculate week range (Monday to Sunday)
        days_since_monday = target_date.weekday()
        week_start = target_date - timedelta(days=days_since_monday)
        week_end = week_start + timedelta(days=6)

        # Get calendar data
        result = await calendar_service.get_calendar_view(
            user_uid=user_uid,
            start_date=week_start,
            end_date=week_end,
            view_type=CalendarView.WEEK,
        )

        if not result.is_ok:
            return error_response(result.error)

        calendar_data = result.value
        week_start = calendar_data.start_date
        navbar = await create_navbar_for_request(request, active_page="events")

        return _wrap_calendar_page(
            navbar,
            Div(
                Container(
                    # Header
                    Div(
                        H1(
                            f"Week of {week_start.strftime('%B %d, %Y')}",
                            cls="text-3xl font-bold mb-4",
                        ),
                        create_view_switcher("week", week_start),
                        # Week navigation - using links instead of JavaScript
                        Div(
                            ButtonLink(
                                "← Previous Week",
                                href=f"/events/week/{_get_prev_week(week_start)}",
                                variant=ButtonT.ghost,
                                size=Size.sm,
                            ),
                            ButtonLink(
                                "This Week",
                                href=f"/events/week/{date.today().isoformat()}",
                                variant=ButtonT.primary,
                                size=Size.sm,
                                cls="mx-2",
                            ),
                            ButtonLink(
                                "Next Week →",
                                href=f"/events/week/{_get_next_week(week_start)}",
                                variant=ButtonT.ghost,
                                size=Size.sm,
                            ),
                            cls="flex justify-center mb-6",
                        ),
                        cls="mb-6",
                    ),
                    # Week grid
                    create_week_grid(calendar_data),
                    # Hidden form for HTMX drag-drop reschedule
                    create_reschedule_form(),
                ),
                cls="max-w-7xl mx-auto p-6",
            ),
            f"Week of {week_start.strftime('%B %d, %Y')}",
        )

    @rt("/events/day/{date_str}")
    async def calendar_day(request: Request, date_str: str) -> Any:
        """Day view of the calendar."""
        user_uid = require_authenticated_user(request)  # Enforce authentication

        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            target_date = date.today()

        # Get calendar data
        result = await calendar_service.get_calendar_view(
            user_uid=user_uid,
            start_date=target_date,
            end_date=target_date,
            view_type=CalendarView.DAY,
        )

        if not result.is_ok:
            return error_response(result.error)

        calendar_data = result.value
        navbar = await create_navbar_for_request(request, active_page="events")

        return _wrap_calendar_page(
            navbar,
            Div(
                Container(
                    # Header
                    Div(
                        H1(
                            target_date.strftime("%A, %B %d, %Y"),
                            cls="text-3xl font-bold mb-4",
                        ),
                        create_view_switcher("day", target_date),
                        # Day navigation - using links instead of JavaScript
                        Div(
                            ButtonLink(
                                "← Previous Day",
                                href=f"/events/day/{_get_prev_day(target_date)}",
                                variant=ButtonT.ghost,
                                size=Size.sm,
                            ),
                            ButtonLink(
                                "Today",
                                href=f"/events/day/{date.today().isoformat()}",
                                variant=ButtonT.primary,
                                size=Size.sm,
                                cls="mx-2",
                            ),
                            ButtonLink(
                                "Next Day →",
                                href=f"/events/day/{_get_next_day(target_date)}",
                                variant=ButtonT.ghost,
                                size=Size.sm,
                            ),
                            cls="flex justify-center mb-6",
                        ),
                        cls="mb-6",
                    ),
                    # Day timeline
                    create_day_timeline(calendar_data),
                    # Hidden form for HTMX drag-drop reschedule
                    create_reschedule_form(),
                ),
                cls="max-w-7xl mx-auto p-6",
            ),
            "Day View",
        )

    # =========================================================================
    # HTMX Fragment Routes
    # =========================================================================

    @rt("/events/calendar/quick-create")
    async def calendar_quick_create_htmx(request: Request) -> Any:
        """
        HTMX endpoint for quick create form.

        Accepts form data and returns HTML fragment for status display.
        """
        try:
            form_data = await request.form()

            item_type_raw = form_data.get("type", "task")
            item_type = str(item_type_raw) if item_type_raw else "task"
            title_raw = form_data.get("title", "")
            title = str(title_raw).strip() if title_raw else ""
            start_time_str_raw = form_data.get("start_time", "")
            start_time_str = str(start_time_str_raw) if start_time_str_raw else ""
            duration_raw = form_data.get("duration", 60)
            duration = int(duration_raw) if duration_raw else 60

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
        except Exception as e:
            logger.error(f"Quick create error: {e}")
            return Alert(
                P(f"Error: {e}", cls="text-sm"),
                variant=AlertT.error,
            )

    @rt("/events/calendar/habit/{habit_uid}/record/{status}")
    async def calendar_habit_record(request: Request, habit_uid: str, status: str) -> Any:
        """
        HTMX endpoint for recording habit occurrences.

        Args:
            habit_uid: The habit UID
            status: One of 'done', 'skipped', 'missed'
        """
        try:
            form_data = await request.form()
            notes = form_data.get("notes", "")

            # Validate status
            valid_statuses = {"done", "skipped", "missed"}
            if status.lower() not in valid_statuses:
                return Alert(
                    P(f"Invalid status: {status}", cls="text-sm"),
                    variant=AlertT.error,
                )

            # Get today's date
            today = date.today().isoformat()

            # Record the occurrence via habits service
            if habits_service:
                result = await habits_service.record_occurrence(
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

            # Fallback for development (no service)
            return Alert(
                P(
                    f"✓ Would record {status} (service not available)",
                    cls="text-sm",
                ),
                variant=AlertT.info,
            )

        except Exception as e:
            logger.error(f"Habit record error: {e}")
            return Alert(
                P(f"Error: {e}", cls="text-sm"),
                variant=AlertT.error,
            )

    @rt("/events/calendar/item-details/{item_id}")
    async def calendar_item_details_modal(_request: Request, item_id: str) -> Any:
        """
        HTMX endpoint for calendar item details modal.

        Returns HTML fragment instead of JSON for direct DOM insertion.
        """
        result = await calendar_service.get_item(item_id)

        if result.is_ok and result.value:
            return _render_item_details_modal(result.value)

        # Error state
        return Div(
            Div(
                Div(
                    H2("Error", cls="text-xl font-bold text-error mb-2"),
                    P("Calendar item not found", cls="text-muted-foreground"),
                    Button(
                        "Close",
                        variant=ButtonT.ghost,
                        cls="mt-4",
                        onclick="document.getElementById('item-details-modal').remove()",
                    ),
                    cls="bg-background rounded-lg p-6 max-w-md w-full mx-4",
                ),
                cls="fixed inset-0 flex items-center justify-center bg-black bg-opacity-50 z-50",
                onclick="if(event.target === this) document.getElementById('item-details-modal').remove()",
            ),
            id="item-details-modal",
        )
