"""Today Orchestrator.

Produces the ``TodayPageContext`` consumed by ``ui/today/page.py``. One
method, one shape, no UI concerns leaking into the service layer.

See ``docs/design-handoff/today/today.md`` for the design spec and
``ui/page_contexts.py`` for the TypedDicts defined here.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from core.models.enums import EntityStatus, Priority
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from ui.page_contexts import (
    GoalView,
    KindMeta,
    LifePathRibbonView,
    PrincipleView,
    RitualView,
    TaskView,
    TodayPageContext,
    TodayStats,
    TriageItemView,
)

if TYPE_CHECKING:
    from core.models.event.event import Event
    from core.models.goal.goal import Goal
    from core.models.habit.habit import Habit
    from core.models.principle.principle import Principle
    from core.models.task.task import Task
    from core.services.events_service import EventsService
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.lifepath.lifepath_service import LifePathService
    from core.services.principles_service import PrinciplesService
    from core.services.tasks_service import TasksService


logger = get_logger("skuel.orchestrators.today")


# Days-since-activity threshold for a ribbon to render as "dormant".
_DORMANCY_DAYS = 7

# How far into the future counts as "today" when filtering tasks/events.
# A task due later today is still "today"; tasks due tomorrow are not.
_TODAY_WINDOW = timedelta(days=0)


# Canonical kind metadata — matches today.md §2 and handoff/today/today.html.
# Keys are the string ``kind`` values on ``TaskView``.
_KINDS: dict[str, KindMeta] = {
    "submission": {"icon": "file-text", "label": "Submission"},
    "path-step": {"icon": "route", "label": "Path step"},
    "askesis": {"icon": "sunrise", "label": "Askesis"},
    "journal": {"icon": "book-open", "label": "Journal"},
    "ku": {"icon": "gem", "label": "KU"},
    "resource": {"icon": "link", "label": "Resource"},
}


# Priority → view-string mapping. The mock uses "high" / "medium" / "low";
# SKUEL's enum also has CRITICAL and NONE which we collapse.
def _priority_label(raw: object) -> str:
    try:
        p = raw if isinstance(raw, Priority) else Priority(str(raw).lower())
    except ValueError:
        return "low"
    if p in (Priority.CRITICAL, Priority.HIGH):
        return "high"
    if p == Priority.MEDIUM:
        return "medium"
    return "low"


def _due_label(d: date | None, today: date) -> str:
    """Render a due-date into the right-side card label."""
    if d is None:
        return ""
    if d == today:
        return "Today"
    if d < today:
        delta = (today - d).days
        return f"Overdue · {delta}d"
    delta = (d - today).days
    if delta == 1:
        return "Tomorrow"
    return f"In {delta}d"


def _date_label(today: date) -> str:
    """E.g. ``"Saturday · March 22"``."""
    return today.strftime("%A · %B ") + str(today.day)


class TodayOrchestrator:
    """Facade for the Today page.

    Composes tasks, goals, habits, events, principles, and the user's
    lifepath into a flat ``TodayPageContext``. The orchestrator does NOT
    mutate — all writes happen through the individual domain services
    (triggered by HTMX endpoints in ``adapters/inbound/today_routes.py``).

    Design notes:

    - ``build_context()`` issues several independent reads. Failure in one
      domain degrades that section rather than failing the whole page (the
      user's day is still useful without habit rituals).
    - ``lifepaths`` is always a single ribbon keyed off the user's
      ``life_path_uid``. The design mock groups principles under multiple
      lifepaths, but SKUEL's current model is one-lifepath-per-user; a
      real multi-lifepath grouping is a future refactor (see TODO below).
    - ``now_hhmm`` is server-clock. Client-side drift would misplace the
      NOW line on the Day spine relative to server-computed ritual
      positions — stay consistent.
    """

    # TODO(multi-lifepath): when the model supports multiple LifePaths per
    # user, group principles by their :BELONGS_TO LifePath edge and emit
    # one ``LifePathRibbonView`` per lifepath, sorted active-first.

    def __init__(
        self,
        tasks_service: TasksService,
        goals_service: GoalsService,
        habits_service: HabitsService,
        events_service: EventsService,
        principles_service: PrinciplesService,
        lifepath_service: LifePathService,
    ) -> None:
        self._tasks = tasks_service
        self._goals = goals_service
        self._habits = habits_service
        self._events = events_service
        self._principles = principles_service
        self._lifepath = lifepath_service

    async def build_context(self, user_uid: UserUID) -> Result[TodayPageContext]:
        """Assemble the full Today page context for this user."""

        now = datetime.now()
        today = now.date()

        tasks_r = await self._tasks.get_user_tasks(user_uid)
        goals_r = await self._goals.get_user_goals(user_uid)
        principles_r = await self._principles.get_user_principles(user_uid)
        habits_r = await self._habits.get_user_habits(user_uid)
        events_r = await self._events.get_user_events(user_uid)
        designation_r = await self._lifepath.core.get_designation(user_uid)

        if tasks_r.is_error:
            return Result.fail(tasks_r)
        if goals_r.is_error:
            return Result.fail(goals_r)
        if principles_r.is_error:
            return Result.fail(principles_r)

        all_tasks: list[Task] = tasks_r.value
        all_goals: list[Goal] = goals_r.value
        all_principles: list[Principle] = principles_r.value
        all_habits: list[Habit] = habits_r.value if not habits_r.is_error else []
        all_events: list[Event] = events_r.value if not events_r.is_error else []
        designation = None if designation_r.is_error else designation_r.value

        lifepath_id = (
            f"lp-{user_uid}"
            if designation is None
            else f"lp-{designation.life_path_uid or user_uid}"
        )

        today_tasks_full = [
            t for t in all_tasks if t.due_date == today and t.status != EntityStatus.COMPLETED
        ]
        triage_tasks_full = [
            t
            for t in all_tasks
            if t.due_date is not None and t.due_date < today and t.status != EntityStatus.COMPLETED
        ]

        task_views: list[TaskView] = [
            _task_to_view(t, lifepath_id=lifepath_id, today=today) for t in today_tasks_full
        ]
        triage_views: list[TriageItemView] = [
            _task_to_triage(t, lifepath_id=lifepath_id, today=today) for t in triage_tasks_full
        ]

        principle_views: list[PrincipleView] = [
            {
                "id": p.uid,
                "lifepath_id": lifepath_id,
                "label": p.title,
                "strength": _principle_strength(p),
                "streak": getattr(p, "streak_days", 0) or 0,
            }
            for p in all_principles
            if p.status != EntityStatus.ARCHIVED
        ]

        goal_views: list[GoalView] = [
            {
                "id": g.uid,
                "principle_id": _first_principle_for_goal(g, all_principles),
                "label": g.title,
                "progress": _goal_progress(g),
            }
            for g in all_goals
            if g.status == EntityStatus.ACTIVE
        ]

        ribbon = _build_ribbon(
            lifepath_id=lifepath_id,
            designation=designation,
            all_tasks=all_tasks,
        )
        lifepaths: list[LifePathRibbonView] = [ribbon]

        rituals: list[RitualView] = _build_rituals(
            habits=all_habits, events=all_events, today=today
        )

        stats: TodayStats = {
            "nodes": len(task_views) + len(triage_views),
            "committed_min": sum(tv["est_min"] for tv in task_views),
            "done": sum(
                1
                for t in all_tasks
                if t.status == EntityStatus.COMPLETED and t.completion_date == today
            ),
        }

        ctx: TodayPageContext = {
            "date_label": _date_label(today),
            "now_hhmm": now.strftime("%H:%M"),
            "stats": stats,
            "triage": triage_views,
            "lifepaths": lifepaths,
            "principles": principle_views,
            "goals": goal_views,
            "tasks": task_views,
            "rituals": rituals,
            "kinds": _KINDS,
        }
        return Result.ok(ctx)


# ============================================================================
# Mappers — keep them as module-level functions so they can be unit-tested
# without instantiating the orchestrator.
# ============================================================================


def _task_to_view(task: Task, *, lifepath_id: str, today: date) -> TaskView:
    return {
        "id": task.uid,
        "lifepath_id": lifepath_id,
        "goal_id": getattr(task, "goal_uid", None),
        "kind": "submission",
        "label": task.title,
        "meta": task.description[:80] if task.description else "",
        "priority": _priority_label(task.priority),
        "est_min": int(getattr(task, "estimated_minutes", 0) or 0),
        "due_label": _due_label(task.due_date, today),
    }


def _task_to_triage(task: Task, *, lifepath_id: str, today: date) -> TriageItemView:
    base = _task_to_view(task, lifepath_id=lifepath_id, today=today)
    delta = (today - task.due_date).days if task.due_date else 0
    reason = f"Overdue · {delta}d" if delta > 0 else "Blocked"
    return {
        **base,
        "reason": reason,
        "severity": "overdue" if delta > 0 else "blocked",
    }


def _principle_strength(principle: Principle) -> str:
    raw = getattr(principle, "strength", None)
    if raw is None:
        return "developing"
    s = str(raw).lower()
    if s in ("core", "strong", "moderate", "developing", "exploring"):
        return s
    return "developing"


def _first_principle_for_goal(_goal: Goal, principles: list[Principle]) -> str:
    # The Goal↔Principle edge is graph-native; until the orchestrator
    # pulls enriched graph context, fall back to the first active
    # principle so the progress bar still groups sensibly.
    for p in principles:
        if p.status == EntityStatus.ACTIVE:
            return p.uid
    return ""


def _goal_progress(goal: Goal) -> float:
    raw = getattr(goal, "progress", None)
    if raw is None:
        return 0.0
    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return 0.0


def _build_ribbon(
    *,
    lifepath_id: str,
    designation: object,
    all_tasks: list[Task],
) -> LifePathRibbonView:
    """Produce the single LifePath ribbon for the current user.

    ``dormant`` fires when no task has been touched in the last
    ``_DORMANCY_DAYS``. When the model grows multi-lifepath support
    this logic will move into a per-lifepath loop (see TODO on class).
    """
    now = datetime.now()
    touched_ats: list[datetime] = []
    for t in all_tasks:
        touched = getattr(t, "updated_at", None) or getattr(t, "created_at", None)
        if isinstance(touched, datetime):
            touched_ats.append(touched)
    last_touched_at: datetime | None = max(touched_ats) if touched_ats else None

    dormant = False
    last_touched_label: str | None = None
    if last_touched_at is None:
        dormant = True
    else:
        delta = now - last_touched_at
        if delta > timedelta(days=_DORMANCY_DAYS):
            dormant = True
            last_touched_label = f"{delta.days} days ago"

    label = getattr(designation, "life_path_title", None) if designation else None
    blurb = getattr(designation, "vision", None) if designation else None

    return {
        "id": lifepath_id,
        "label": label or "Your path",
        "blurb": (blurb or None)
        if blurb is None or len(str(blurb)) < 120
        else str(blurb)[:117] + "…",
        "color": "oklch(0.55 0.20 255)",  # token-mirrored strength.strong
        "dormant": dormant,
        "last_touched": last_touched_label,
    }


def _build_rituals(*, habits: list[Habit], events: list[Event], today: date) -> list[RitualView]:
    """Time-anchored items for the Day spine.

    Today's rituals = habits with a scheduled_time + events scheduled for
    today with a start_time. Everything sorted chronologically.
    """
    rituals: list[RitualView] = []

    for h in habits:
        t = getattr(h, "scheduled_time", None)
        if t is None:
            continue
        rituals.append(
            {
                "id": h.uid,
                "time": t.strftime("%H:%M") if hasattr(t, "strftime") else str(t),
                "label": h.title,
                "est_min": int(getattr(h, "estimated_minutes", 0) or 0),
                "principle_id": getattr(h, "principle_uid", None),
            }
        )

    for e in events:
        event_date = getattr(e, "event_date", None)
        if event_date != today:
            continue
        start = getattr(e, "start_time", None)
        if start is None:
            continue
        rituals.append(
            {
                "id": e.uid,
                "time": start.strftime("%H:%M") if hasattr(start, "strftime") else str(start),
                "label": e.title,
                "est_min": int(getattr(e, "duration_minutes", 0) or 0),
                "principle_id": None,
            }
        )

    rituals.sort(key=lambda r: r["time"])
    return rituals


__all__ = ["TodayOrchestrator"]


# Silence the "imported but unused" warning for Errors — reserved for when
# per-domain failures become their own Result-level errors instead of
# empty fallbacks.
_ = Errors
