"""Today Orchestrator.

Produces the ``TodayPageContext`` consumed by ``ui/today/page.py``. One
method, one shape, no UI concerns leaking into the service layer.

See ``docs/design-handoff/today/today.md`` for the design spec and
``ui/page_contexts.py`` for the TypedDicts defined here.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from core.models.enums import EntityStatus, Priority
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
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


def _parse_hhmm(value: str | None) -> str | None:
    """Parse a ``"HH:MM"`` / ``"H:MM"`` / ``"HH:MM:SS"`` string into ``"HH:MM"``.

    Habit/event models store time-of-day as a free-form string (``preferred_time``,
    ``reminder_time``) rather than a typed ``datetime.time``. Day-spine positioning
    needs a canonical ``HH:MM``; anything unparseable drops off the spine.
    """
    if not value:
        return None
    parts = value.strip().split(":")
    if len(parts) < 2:
        return None
    try:
        hh, mm = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hh < 24 and 0 <= mm < 60):
        return None
    return f"{hh:02d}:{mm:02d}"


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

        active_goals = [g for g in all_goals if g.status == EntityStatus.ACTIVE]
        rituable_habits = [h for h in all_habits if _parse_hhmm(h.preferred_time) is not None]

        # GRAPH-NATIVE: Goal→Principle (GUIDED_BY_PRINCIPLE) and Habit→Principle
        # (EMBODIES_PRINCIPLE) live as Neo4j edges, not scalar fields. Fetch once
        # per build, concurrently, and index into maps the mappers consume.
        goal_principle_map = await _first_principle_map(self._goals, [g.uid for g in active_goals])
        habit_principle_map = await _first_principle_map(
            self._habits, [h.uid for h in rituable_habits]
        )

        lp_title = await _fetch_lp_title(self._lifepath, designation)

        task_views: list[TaskView] = [
            _task_to_view(t, lifepath_id=lifepath_id, today=today) for t in today_tasks_full
        ]
        triage_views: list[TriageItemView] = [
            _task_to_triage(t, lifepath_id=lifepath_id, today=today) for t in triage_tasks_full
        ]

        # TODO(principle-streak): Principle "streak" in the Today view is an
        # aggregate over habits that EMBODY the principle, not a Principle field.
        # Derive from habit completions once a streak-aggregation service lands.
        principle_views: list[PrincipleView] = [
            {
                "id": p.uid,
                "lifepath_id": lifepath_id,
                "label": p.title,
                "strength": _principle_strength(p),
                "streak": 0,
            }
            for p in all_principles
            if p.status != EntityStatus.ARCHIVED
        ]

        goal_views: list[GoalView] = [
            {
                "id": g.uid,
                "principle_id": goal_principle_map.get(g.uid, ""),
                "label": g.title,
                "progress": g.calculate_progress(),
            }
            for g in active_goals
        ]

        ribbon = _build_ribbon(
            lifepath_id=lifepath_id,
            designation=designation,
            lp_title=lp_title,
            all_tasks=all_tasks,
        )
        lifepaths: list[LifePathRibbonView] = [ribbon]

        rituals: list[RitualView] = _build_rituals(
            habits=all_habits,
            events=all_events,
            today=today,
            habit_principle_map=habit_principle_map,
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
        "goal_id": task.fulfills_goal_uid,
        "kind": "submission",
        "label": task.title,
        "meta": task.description[:80] if task.description else "",
        "priority": _priority_label(task.priority),
        "est_min": int(task.duration_minutes or 0),
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
    """Render ``Principle.strength`` (StrEnum) as the view-layer string."""
    if principle.strength is None:
        return "developing"
    return str(principle.strength.value)


async def _first_principle_map(service: object, entity_uids: list[str]) -> dict[str, str]:
    """Return ``{entity_uid: first_principle_uid}`` for the given entities.

    Uses the ``"principles"`` relationship key, which both ``HABITS_CONFIG``
    (EMBODIES_PRINCIPLE) and ``GOAPS_CONFIG`` (GUIDED_BY_PRINCIPLE) expose.
    Failures degrade to "no principle linked" rather than aborting the page.
    """
    if not entity_uids:
        return {}
    relationships = service.relationships  # type: ignore[attr-defined]
    results = await asyncio.gather(
        *(relationships.get_related_uids("principles", uid) for uid in entity_uids),
        return_exceptions=True,
    )
    mapping: dict[str, str] = {}
    for uid, r in zip(entity_uids, results, strict=True):
        if isinstance(r, BaseException):
            continue
        if r.is_error:
            continue
        uids: list[str] = r.value
        if uids:
            mapping[uid] = uids[0]
    return mapping


async def _fetch_lp_title(lifepath_service: object, designation: object) -> str | None:
    """Look up the designated LifePath's title via the LP service.

    The title lives on the LP entity itself; ``LifePathDesignation`` only
    carries the UID. Returns ``None`` when unavailable (no designation, no
    wired lp_service, or fetch error) — the ribbon falls back to "Your path".
    """
    if designation is None:
        return None
    life_path_uid = getattr(designation, "life_path_uid", None)
    if not life_path_uid:
        return None
    lp_service = getattr(getattr(lifepath_service, "core", None), "lp_service", None)
    if lp_service is None:
        return None
    r = await lp_service.get(life_path_uid)
    if r.is_error or r.value is None:
        return None
    title = getattr(r.value, "title", None)
    return str(title) if title else None


def _build_ribbon(
    *,
    lifepath_id: str,
    designation: object,
    lp_title: str | None,
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
        touched = t.updated_at or t.created_at
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

    vision = getattr(designation, "vision_statement", None) if designation else None
    blurb: str | None
    if not vision:
        blurb = None
    elif len(vision) < 120:
        blurb = vision
    else:
        blurb = vision[:117] + "…"

    return {
        "id": lifepath_id,
        "label": lp_title or "Your path",
        "blurb": blurb,
        "color": "oklch(0.55 0.20 255)",  # token-mirrored strength.strong
        "dormant": dormant,
        "last_touched": last_touched_label,
    }


def _build_rituals(
    *,
    habits: list[Habit],
    events: list[Event],
    today: date,
    habit_principle_map: dict[str, str] | None = None,
) -> list[RitualView]:
    """Time-anchored items for the Day spine.

    Habits contribute when their ``preferred_time`` parses as ``HH:MM``;
    events contribute when they occur today and carry a ``start_time``.
    Everything is sorted chronologically.
    """
    pmap = habit_principle_map or {}
    rituals: list[RitualView] = []

    for h in habits:
        parsed = _parse_hhmm(h.preferred_time)
        if parsed is None:
            continue
        rituals.append(
            {
                "id": h.uid,
                "time": parsed,
                "label": h.title,
                "est_min": int(h.duration_minutes or 0),
                "principle_id": pmap.get(h.uid),
            }
        )

    for e in events:
        if e.event_date != today or e.start_time is None:
            continue
        rituals.append(
            {
                "id": e.uid,
                "time": e.start_time.strftime("%H:%M"),
                "label": e.title,
                "est_min": int(e.duration_minutes or 0),
                "principle_id": None,
            }
        )

    rituals.sort(key=_ritual_sort_key)
    return rituals


def _ritual_sort_key(ritual: RitualView) -> str:
    return ritual["time"]


__all__ = ["TodayOrchestrator"]
