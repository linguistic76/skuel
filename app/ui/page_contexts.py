"""Per-domain page context types for route→UI contracts.

Presentation-layer TypedDicts that define the contract between routes and
UI view components. These are UI concerns, NOT service-layer contracts.

Each Activity Domain gets a standalone TypedDict with properly typed entities.
Required fields use ``total=True`` (default); optional fields use ``NotRequired``.

Usage::

    from ui.page_contexts import TasksPageContext

    ctx: TasksPageContext = {
        "entities": tasks,
        "filters": filters,
    }
    view_content = TasksViewComponents.render_list_view(ctx)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NotRequired, TypedDict

if TYPE_CHECKING:
    from core.models.choice.choice import Choice
    from core.models.curriculum import Curriculum
    from core.models.event.calendar_models import CalendarItem
    from core.models.event.event import Event
    from core.models.exercises.exercise import Exercise
    from core.models.goal.goal import Goal
    from core.models.habit.habit import Habit
    from core.models.ku.ku import Ku
    from core.models.principle.principle import Principle
    from core.models.task.task import Task
    from core.models.user_entry.user_entry import UserEntry


# ============================================================================
# Activity Domain Contexts
# ============================================================================


class TasksPageContext(TypedDict):
    """Tasks list view context."""

    entities: list[Task]
    filters: dict[str, Any]
    projects: NotRequired[list[str]]
    assignees: NotRequired[list[str]]
    view: NotRequired[str]


class GoalsPageContext(TypedDict):
    """Goals list view context."""

    entities: list[Goal]
    stats: dict[str, int | float]
    filters: dict[str, Any]
    categories: NotRequired[list[str]]
    view: NotRequired[str]


class HabitsPageContext(TypedDict):
    """Habits list view context."""

    entities: list[Habit]
    stats: dict[str, int | float]
    filters: dict[str, Any]
    categories: NotRequired[list[str]]
    view: NotRequired[str]


class EventsPageContext(TypedDict):
    """Events list view context."""

    entities: list[Event]
    stats: dict[str, int | float]
    filters: dict[str, Any]
    view: NotRequired[str]


class ChoicesPageContext(TypedDict):
    """Choices list view context."""

    entities: list[Choice]
    stats: dict[str, int | float]
    filters: dict[str, Any]
    view: NotRequired[str]


class PrinciplesPageContext(TypedDict):
    """Principles list view context."""

    entities: list[Principle]
    stats: dict[str, int | float]
    filters: dict[str, Any]
    categories: NotRequired[list[str]]
    view: NotRequired[str]


# ============================================================================
# Curriculum Contexts
# ============================================================================


class CurriculumHubContext(TypedDict, total=False):
    """Curriculum landing page context."""

    path_step_count: int
    ps_count: int
    lp_count: int
    exercise_count: int


class CurriculumListContext(TypedDict, total=False):
    """Curriculum sub-page list context."""

    entities: list[Curriculum]
    active_section: str


# ============================================================================
# Study / Submissions Context
# ============================================================================


class SubmissionsPageContext(TypedDict, total=False):
    """Study submissions page context."""

    submissions: list[UserEntry]
    exercises: list[Exercise]


# ============================================================================
# KU Context
# ============================================================================


class KuIndexContext(TypedDict, total=False):
    """Knowledge Unit index page context."""

    kus: list[Ku]
    pinned_uids: list[str]
    latest: list[Ku]
    bookmarked: list[Ku]


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
