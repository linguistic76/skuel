"""Page context types for route→UI contracts.

Presentation-layer TypedDicts that define the contract between a route (or a UI
orchestrator) and the view that renders it: the Today day view's context and the
Explore related-concepts fragments' rows. These are UI concerns, NOT
service-layer contracts.

Usage::

    ctx_result = await orchestrator.build_context(user_uid, view_date)
    content = TodayPage(ctx_result.value)  # ctx_result: Result[TodayPageContext]
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from core.models.choice.choice import Choice
    from core.models.event.calendar_models import CalendarItem
    from core.models.event.event import Event
    from core.models.goal.goal import Goal
    from core.models.task.task import Task
    from core.ports.query_types import EntityConnection


# ============================================================================
# Today Surface Context
# ============================================================================
# The day view (ui/today/) renders per-domain lists of DOMAIN MODELS — the
# same entities the domain list pages render, through the same cards — so the
# orchestrator (ui/today/orchestrator.py) selects and sorts, and never re-shapes.


class TodayPageContext(TypedDict):
    """Everything the day view renders for one day.

    Produced by ``TodayOrchestrator.build_context(user_uid, view_date)``;
    consumed by ``ui.today.page.TodayPage(ctx)``.

    ``overdue`` is the live day's triage — tasks due strictly before today —
    and is empty while browsing another day (``ui/today/membership.py``
    decides membership; the defer guard validates by the same predicates).
    ``tasks`` are the day's lens members (scheduled OR due on the day) minus the
    ones already shown in ``overdue``: a task in both renders once, in Overdue.
    ``habits`` are the calendar's day-stamped items (``occurrence_data`` carries
    the day and its completion state), so their chips open the day-aware modal.
    """

    today_iso: str  # ISO date the day lens is pointed at — the single source
    #                 for every date-anchored href (Prev/Now/Next, quick-add)
    date_label: str  # "Saturday · March 22" (eyebrow, for the viewed day)
    heading: str  # H1 word: "Today" / "Yesterday" / "Tomorrow" / "Jul 19"
    is_today: bool  # the viewed day is the live current day
    can_quick_add: bool  # True on today/future — gates the day-lens task quick-add
    #                      affordance (absent on past days; the POST also refuses
    #                      past dates server-side — act-from arc C6)
    overdue: list[Task]
    tasks: list[Task]
    events: list[Event]
    task_links: dict[str, list[EntityConnection]]  # overdue + tasks, by uid (ADR-090 §2)
    event_links: dict[str, list[EntityConnection]]
    habits: list[CalendarItem]
    milestones: list[Goal]
    choices: list[Choice]


# =============================================================================
# Explore — Related-concepts fragments (vector-similarity read-time lens)
# =============================================================================


class RelatedConceptChip(TypedDict):
    """One similarity chip: uid + title only — a read-time hint, never an edge.

    Produced by the /explore/*/related route boundary (narrowed from raw
    vector-search node dicts); consumed by the related-concepts renderers.
    """

    uid: str
    title: str


class NextStepRelatedGroup(TypedDict):
    """One ZPD next-step Ku with its undirected similarity hints.

    ``ku`` is the readiness-ranked proximal-zone Ku (authored-edge traversal);
    ``related`` are its vector neighbours, engaged Kus already filtered out.
    """

    ku: RelatedConceptChip
    related: list[RelatedConceptChip]
