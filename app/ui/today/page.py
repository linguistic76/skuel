"""The day view — one day of dated Activity, server-rendered.

The third temporal lens beside the calendar's Week and Month: the same nav
cluster, kind legend and chips (``ui/calendar/components.py``) around
per-domain sections rendered through the domain list cards. No page-local
JavaScript: interaction is HTMX (the cards' status toggles, quick-add, defer)
and the shared ``calendarLegend`` Alpine component (one filter, one storage
key, across every calendar surface).

Wiring: ``adapters/inbound/today_routes.py`` wraps ``TodayPage(ctx)`` in the
activity sidebar page with ``/static/css/calendar.css`` (chips + kind filters).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import TYPE_CHECKING

from fasthtml.common import H1, H2, A, Button, Div, Form, Header, Input, Main, P, Section, Span

from core.models.event.calendar_models import CalendarItemType
from ui.activities._shared import ActivityList
from ui.activities.events_views import EventCard
from ui.activities.tasks_views import TaskCard
from ui.calendar.components import DAY_KINDS, _event_chip, calendar_nav_cluster, create_kind_legend
from ui.components import Icon
from ui.patterns.empty_state import EmptyState
from ui.today.orchestrator import moment_is_on_day

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.choice.choice import Choice
    from core.models.event.calendar_models import CalendarItem
    from core.models.event.event import Event
    from core.models.goal.goal import Goal
    from core.models.task.task import Task
    from ui.page_contexts import TodayPageContext

_CONTAINER_CLS = "mx-auto max-w-[1280px] py-8 pb-24"
_SECTION_TITLE_CLS = "text-11 font-bold uppercase tracking-[0.09em] text-muted-foreground mb-2"
_SECTION_KEYS = ("overdue", "tasks", "events", "habits", "milestones", "choices")


def TodayPage(ctx: TodayPageContext) -> FT:
    """Render the day view from a ``TodayPageContext``.

    The Prev/Now/Next cluster and every date-anchored form field derive from
    ``ctx["today_iso"]`` — the day the orchestrator built the context for — so a
    second ``date.today()`` here cannot disagree across a midnight boundary.
    """
    view_date = date.fromisoformat(ctx["today_iso"])
    has_anything = any(ctx[key] for key in _SECTION_KEYS)  # type: ignore[literal-required]
    return Main(
        _header(view_date, ctx["heading"], ctx["date_label"]),
        _quick_add(view_date) if ctx["can_quick_add"] else None,
        _caught_up() if not has_anything else None,
        _overdue_section(ctx["overdue"], view_date) if ctx["overdue"] else None,
        _tasks_section(ctx["tasks"], view_date) if has_anything else None,
        _events_section(ctx["events"]) if ctx["events"] else None,
        _habits_section(ctx["habits"], view_date) if ctx["habits"] else None,
        _milestones_section(ctx["milestones"]) if ctx["milestones"] else None,
        _choices_section(ctx["choices"], view_date) if ctx["choices"] else None,
        cls=_CONTAINER_CLS,
        # The calendar's legend controller: toggles cal-hide-*/cal-spot-* on this
        # shell, and the pure-CSS filters (calendar.css) apply to the
        # data-item-type sections and chips below — the same filter, same stored
        # state, as the week.
        x_data="calendarLegend",
        **{":class": "filterClasses()"},
    )


# ============================================================================
# Header — eyebrow date, heading, nav cluster + kind legend
# ============================================================================


def _step_day(view_date: date, days: int) -> date:
    """``view_date`` shifted by ``days``, clamped to the representable range.

    ``date`` overflows below ``0001-01-01`` / above ``9999-12-31``; the day lens
    accepts arbitrary ISO dates, so a naive ``±1`` would crash render at those
    extremes. Clamping makes the boundary arrow a no-op self-link instead.
    """
    if days < 0 and view_date == date.min:
        return date.min
    if days > 0 and view_date == date.max:
        return date.max
    return view_date + timedelta(days=days)


def _header(view_date: date, heading: str, date_label: str) -> FT:
    return Header(
        Div(
            Div(
                date_label,
                cls="text-11 font-bold uppercase tracking-[0.09em] text-muted-foreground",
            ),
            H1(heading, cls="mt-1.5 text-[44px] font-bold leading-none tracking-tight"),
            cls="min-w-[280px] flex-1",
        ),
        # Right column: the Prev/Now/Next day-nav cluster (matching the Week/Month
        # calendar toolbar) sits top-right, the kind legend below it.
        Div(
            calendar_nav_cluster(
                # Clamp at date.min/date.max: the route accepts any ISO date, and
                # ±1 day past the boundaries raises OverflowError. At an extreme the
                # arrow self-links (a harmless no-op) instead of crashing render.
                prev_href=f"/today/{_step_day(view_date, -1).isoformat()}",
                next_href=f"/today/{_step_day(view_date, +1).isoformat()}",
                today_href="/today",
            ),
            create_kind_legend(DAY_KINDS),
            cls="flex flex-col items-end gap-4",
        ),
        cls="flex flex-wrap items-end justify-between gap-5 mb-8",
    )


def _quick_add(view_date: date) -> FT:
    """Tasks-only quick-add for the viewed day (act-from arc C6).

    Creates a task with ``scheduled_date`` = the viewed day and NO ``due_date``
    ("I'll work on it that day" — a work chip, not a deadline). Submits via HTMX
    (CSRF header attached by skuel.js); the route replies ``HX-Redirect`` back to
    this day's lens so the new task renders immediately. The hidden ``view_date``
    anchors creation to the day the lens is pointed at, not a second server clock.
    """
    return Form(
        Input(type="hidden", name="view_date", value=view_date.isoformat()),
        Input(
            type="text",
            name="title",
            placeholder="Add a task for this day…",
            required=True,
            autocomplete="off",
            maxlength="200",
            aria_label="New task title",
            cls=(
                "flex-1 min-w-0 h-10 px-3 rounded-md border border-border bg-card "
                "text-sm text-foreground placeholder:text-muted-foreground "
                "focus:outline-hidden focus:shadow-focus"
            ),
        ),
        Button(
            Icon("plus", size=15),
            "Add task",
            type="submit",
            cls=(
                "inline-flex items-center gap-1.5 h-10 px-4 rounded-md shrink-0 "
                "bg-foreground text-background text-sm font-semibold "
                "hover:opacity-90 focus:outline-hidden focus:shadow-focus"
            ),
        ),
        hx_post="/today/tasks/quick-add",
        hx_swap="none",
        cls="mb-6 flex items-center gap-2",
    )


def _caught_up() -> FT:
    return Div(
        Div(
            Icon("check-circle-2", size=28),
            cls=(
                "mx-auto mb-5 w-14 h-14 rounded-lg bg-priority-low/15 text-priority-low "
                "flex items-center justify-center"
            ),
        ),
        H2("You're caught up.", cls="text-xl font-bold tracking-tight mb-2"),
        P(
            "Nothing dated for this day. This is the point where most apps would "
            "offer you more to do. SKUEL suggests you close the laptop.",
            cls="text-13 text-muted-foreground leading-relaxed",
        ),
        cls="text-center mx-auto max-w-md py-20 px-8",
    )


# ============================================================================
# Sections — one per dated domain, each a data-item-type container so the
# shared legend filter (calendar.css) can hide or spotlight it
# ============================================================================


def _section(kind: CalendarItemType, title: str, body: FT) -> FT:
    return Section(
        H2(title, cls=_SECTION_TITLE_CLS),
        body,
        cls="mb-8",
        data_item_type=kind.value,
        aria_label=title,
    )


def _defer_form(task: Task, view_date: date, *, source: str) -> FT:
    """Server-rendered "Defer 1d / 1w" control posting the existing defer route.

    ``source`` speaks the card's language (``day`` moves the field(s) placing
    the task on this day; ``triage`` moves the deadline); the route re-derives
    membership from the fresh task and replies ``HX-Redirect`` back to the day,
    so the moved task leaves the list on the reload rather than by client
    bookkeeping.
    """
    button_cls = (
        "text-11 font-medium px-2 py-0.5 rounded-sm border border-border bg-card "
        "text-muted-foreground hover:bg-accent focus:outline-hidden focus:shadow-focus"
    )
    return Form(
        Input(type="hidden", name="view_date", value=view_date.isoformat()),
        Input(type="hidden", name="source", value=source),
        Span("Defer", cls="text-11 text-muted-foreground/70"),
        Button("1d", type="submit", name="span", value="1d", cls=button_cls),
        Button("1w", type="submit", name="span", value="1w", cls=button_cls),
        # The route's refusals are actionable text in a 400 body ("would pass the
        # deadline", "no longer on this day's lens"), which HTMX never swaps. Show
        # it beside the buttons instead of letting the click look inert.
        Span(cls="text-11 text-warning", role="status", **{"data-defer-note": True}),
        hx_post=f"/today/tasks/{task.uid}/defer",
        hx_swap="none",
        **{
            "hx-on::response-error": (
                "this.querySelector('[data-defer-note]').textContent"
                " = event.detail.xhr.responseText"
            ),
        },
        cls="flex items-center gap-1.5 mt-1 pl-1 flex-wrap",
    )


def _task_card_with_defer(
    view_date: date, *, source: str
) -> Callable[[Task, list[dict[str, str]]], FT]:
    """A ``TaskCard`` followed by its defer control — the ``card_fn`` shape
    ``ActivityList`` calls with ``(item, connections)``."""

    def card(task: Task, connections: list[dict[str, str]]) -> FT:
        # The card's status toggle swaps only the card (its own outerHTML target),
        # which would leave a completed task on the day beside a live defer
        # control. The day is server-rendered, so a status UPDATE reloads it —
        # membership then decides what the day shows, as on defer and quick-add.
        # The signal is the field route's HX-Trigger (fired only for a real
        # update, bubbling up from the card's button), not the HTTP status: a
        # refusal there is a 200 banner the card swaps in, which must stay.
        return Div(
            TaskCard(task, connections),
            _defer_form(task, view_date, source=source),
            **{
                "hx-on:activity-field-updated": (
                    "if (event.detail.field === 'status') window.location.reload()"
                ),
            },
        )

    return card


def _overdue_section(overdue: list[Task], view_date: date) -> FT:
    """The live day's triage: tasks due strictly before today (deadline language)."""
    return _section(
        CalendarItemType.TASK,
        "Overdue",
        ActivityList(
            overdue,
            "task",
            _task_card_with_defer(view_date, source="triage"),
            list_id="day-overdue",
        ),
    )


def _tasks_section(tasks: list[Task], view_date: date) -> FT:
    return _section(
        CalendarItemType.TASK,
        "Tasks",
        ActivityList(
            tasks,
            "task",
            _task_card_with_defer(view_date, source="day"),
            empty_state=EmptyState(
                title="No tasks on this day",
                description="Nothing is scheduled or due here.",
            ),
            list_id="day-tasks",
        ),
    )


def _events_section(events: list[Event]) -> FT:
    return _section(
        CalendarItemType.EVENT,
        "Events",
        ActivityList(events, "event", EventCard, list_id="day-events"),
    )


def _habits_section(habits: list[CalendarItem], view_date: date) -> FT:
    """The day's habit occurrences as the calendar's day-stamped chips — each
    opens the day-aware item-details modal with the per-day complete door."""
    return _section(CalendarItemType.HABIT, "Habits", habits_fragment(habits, view_date))


def habits_fragment(habits: list[CalendarItem], view_date: date) -> FT:
    """The habit chips container — the page's and the refresh fragment's one shape.

    The per-day complete door answers with ``HX-Trigger: calendar-refresh``
    (the event the month and week grids re-render on); this container listens
    for it too and swaps itself with ``GET /today/{date}/habits``, so a chip
    completed from its modal turns completed without a reload.
    """
    return Div(
        *[_event_chip(item, large=True) for item in habits],
        id="day-habits",
        cls="flex flex-col gap-1.5",
        hx_get=f"/today/{view_date.isoformat()}/habits",
        hx_trigger="calendar-refresh from:body",
        hx_swap="outerHTML",
    )


def _read_only_row(
    title: str, href: str, label: str, *, item_id: str, kind: CalendarItemType
) -> FT:
    color = kind.get_color()
    return Div(
        Span(cls="flex-none w-2 h-2 rounded-full", style=f"background-color: {color}"),
        A(title, href=href, cls="text-sm font-medium hover:underline truncate"),
        Span(label, cls="ml-auto text-11 text-muted-foreground whitespace-nowrap"),
        id=item_id,
        cls="flex items-center gap-2.5 px-3 py-2 rounded-md border border-border bg-card",
    )


def _milestones_section(milestones: list[Goal]) -> FT:
    """Goals whose target date is this day — read-only rows; goal target dates
    move on the goals surface, not here."""
    return _section(
        CalendarItemType.MILESTONE,
        "Milestones",
        Div(
            *[
                _read_only_row(
                    goal.title or "Untitled goal",
                    f"/goals/detail?uid={goal.uid}",
                    "Target date",
                    item_id=f"day-milestone-{goal.uid}",
                    kind=CalendarItemType.MILESTONE,
                )
                for goal in milestones
            ],
            id="day-milestones",
            cls="flex flex-col gap-1.5",
        ),
    )


def _choices_section(choices: list[Choice], view_date: date) -> FT:
    """Choices due to be decided or decided on this day — read-only rows
    linking to the choice (the only other dated domain; Principles are
    dateless and have no day section)."""
    return _section(
        CalendarItemType.CHOICE,
        "Choices",
        Div(
            *[
                _read_only_row(
                    choice.title or "Untitled choice",
                    f"/choices/detail?uid={choice.uid}",
                    "Decided"
                    if moment_is_on_day(choice.decided_at, view_date)
                    else "Decide by this day",
                    item_id=f"day-choice-{choice.uid}",
                    kind=CalendarItemType.CHOICE,
                )
                for choice in choices
            ],
            id="day-choices",
            cls="flex flex-col gap-1.5",
        ),
    )
