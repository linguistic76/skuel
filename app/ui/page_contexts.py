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
# Flat UI-shape views used by the Today page (ui/today/). The orchestrator
# (core/orchestrator/today_orchestrator.py) produces these; the UI consumes
# them without ever touching the underlying domain models.
#
# See docs/design-handoff/today/today.md (paired spec) for field semantics.


class TodayStats(TypedDict):
    """Header stats block on the Today page."""

    nodes: int  # total cards currently visible (tasks + triage)
    committed_min: int  # sum of est_min across today's tasks
    done: int  # completed-today count


class LifePathRibbonView(TypedDict):
    """One row per LifePath on the Today page.

    ``dormant=True`` renders the collapsed nudge variant (wake button, no
    ribbon body); the orchestrator sets it when the LifePath has had no
    activity in the dormancy window.
    """

    id: str
    label: str
    blurb: str | None
    color: str  # oklch(...) or hsl(...) — token-aware
    dormant: bool
    last_touched: str | None  # human label, e.g. "7 days ago"


class PrincipleView(TypedDict):
    """Principle pill shown in each ribbon header."""

    id: str
    lifepath_id: str
    label: str
    strength: str  # "core" | "strong" | "developing" | "moderate" | "exploring"
    streak: int  # days


class GoalView(TypedDict):
    """Goal progress bar (optional — only rendered if a ribbon has goals)."""

    id: str
    principle_id: str
    label: str
    progress: float  # 0..1


class TaskView(TypedDict):
    """Flat card shape used by rows in ribbons AND triage.

    ``kind`` drives icon + kind-chip label; the mock defines six canonical
    kinds (submission, path-step, askesis, journal, ku, resource).
    ``due_label`` is the right-side label shown on each row.
    """

    id: str
    lifepath_id: str
    goal_id: str | None
    kind: str
    label: str
    meta: str  # short gloss: "draft · needs your decision"
    priority: str  # "high" | "medium" | "low"
    est_min: int
    due_label: str  # "Today", "Tonight", "Overdue · 2d"


class TriageItemView(TaskView):
    """Face-first row in the Triage bar. Extends TaskView with severity/reason."""

    reason: str  # "Overdue · 2 days" / "Blocked · waiting on @mentor"
    severity: str  # "overdue" | "blocked"


class RitualView(TypedDict):
    """Time-anchored item shown on the Day spine."""

    id: str
    time: str  # "HH:MM" 24h
    label: str
    est_min: int
    principle_id: str | None


class KindMeta(TypedDict):
    """Lucide icon + label per task ``kind`` string."""

    icon: str
    label: str


class TodayPageContext(TypedDict):
    """Complete data contract for the Today page.

    Produced by ``TodayOrchestrator.build_context(user_uid)``; consumed by
    ``ui.today.page.TodayPage(ctx)`` and serialized into ``window.SEED`` for
    the Alpine ``today()`` factory in ``static/js/today.js``.

    ``now_hhmm`` is the server clock in the user's timezone — NEVER derive
    it client-side. This keeps SSR output and the Day spine's ``NOW`` marker
    consistent.

    ``lifepaths`` MUST be sorted active-first, dormant-last.
    """

    date_label: str  # "Saturday · March 22"
    now_hhmm: str  # server clock, user tz
    stats: TodayStats
    triage: list[TriageItemView]
    lifepaths: list[LifePathRibbonView]
    principles: list[PrincipleView]
    goals: list[GoalView]
    tasks: list[TaskView]
    rituals: list[RitualView]
    kinds: dict[str, KindMeta]
