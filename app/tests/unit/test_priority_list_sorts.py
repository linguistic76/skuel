"""A list sorted by priority puts an item with no priority after LOW.

Every priority sort reads one rank, ``priority_sort_order``: the Activity list pages'
keys (``core/utils/entity_filters.py``), the facades' ``get_filtered_context`` keys,
and the calendar's peak-energy bucket. The task page's priority sort is
``get_task_urgency`` — within one priority the earlier due date first, an undated
task last. Goals and choices share the rank, and their ties keep the order they had.
"""

from __future__ import annotations

from datetime import date
from operator import attrgetter

from core.models.calendar_optimization import SlotEnergyLevel
from core.models.choice.choice import Choice
from core.models.enums import Priority
from core.models.goal.goal import Goal
from core.models.task.task import Task
from core.services.calendar_optimization_service import CalendarOptimizationService
from core.services.choices_service import _apply_choice_sort
from core.services.goals_service import _apply_goal_sort
from core.services.tasks_service import _apply_task_sort
from core.utils.entity_filters import filter_choices, filter_goals, filter_tasks

USER = "user_test"
EARLY = date(2026, 12, 1)
LATE = date(2026, 12, 20)


def _task(uid: str, priority: Priority | None, due_date: date | None = None, **kw: bool) -> Task:
    return Task(uid=uid, title=uid, user_uid=USER, priority=priority, due_date=due_date, **kw)


def _goal(uid: str, priority: Priority | None) -> Goal:
    return Goal(uid=uid, title=uid, user_uid=USER, priority=priority)


def _choice(uid: str, priority: Priority | None) -> Choice:
    return Choice(uid=uid, title=uid, user_uid=USER, priority=priority)


def _uids(items: list[Task] | list[Goal] | list[Choice]) -> list[str]:
    return [item.uid for item in items]


# The no-priority item is listed first, so a key that ranks it anywhere but last moves it.
def _tasks_with_none() -> list[Task]:
    return [
        _task("task_none", None, EARLY),
        _task("task_low", Priority.LOW, EARLY),
        _task("task_high", Priority.HIGH, EARLY),
        _task("task_medium", Priority.MEDIUM, EARLY),
    ]


def _goals_with_none() -> list[Goal]:
    return [
        _goal("goal_none", None),
        _goal("goal_low", Priority.LOW),
        _goal("goal_high", Priority.HIGH),
        _goal("goal_medium", Priority.MEDIUM),
    ]


def _choices_with_none() -> list[Choice]:
    return [
        _choice("choice_none", None),
        _choice("choice_low", Priority.LOW),
        _choice("choice_high", Priority.HIGH),
        _choice("choice_medium", Priority.MEDIUM),
    ]


class TestTheListPages:
    def test_tasks_no_priority_after_low(self) -> None:
        ordered = filter_tasks(_tasks_with_none(), status_filter="all", sort_by="priority")

        assert _uids(ordered) == ["task_high", "task_medium", "task_low", "task_none"]

    def test_tasks_within_a_priority_earlier_due_date_first_undated_last(self) -> None:
        tasks = [
            _task("task_undated", Priority.HIGH),
            _task("task_late", Priority.HIGH, LATE),
            _task("task_low_early", Priority.LOW, EARLY),
            _task("task_early", Priority.HIGH, EARLY),
        ]

        ordered = filter_tasks(tasks, status_filter="all", sort_by="priority")

        assert _uids(ordered) == ["task_early", "task_late", "task_undated", "task_low_early"]

    def test_goals_no_priority_after_low(self) -> None:
        ordered = filter_goals(_goals_with_none(), status_filter="all", sort_by="priority")

        assert _uids(ordered) == ["goal_high", "goal_medium", "goal_low", "goal_none"]

    def test_goals_tie_keeps_listed_order(self) -> None:
        goals = [_goal("goal_b", Priority.HIGH), _goal("goal_a", Priority.HIGH)]

        ordered = filter_goals(goals, status_filter="all", sort_by="priority")

        assert _uids(ordered) == ["goal_b", "goal_a"]

    def test_choices_no_priority_after_low(self) -> None:
        ordered = filter_choices(_choices_with_none(), status_filter="all", sort_by="priority")

        assert _uids(ordered) == ["choice_high", "choice_medium", "choice_low", "choice_none"]


class TestTheFacadeSorts:
    def test_tasks_no_priority_after_low(self) -> None:
        ordered = _apply_task_sort(_tasks_with_none(), "priority")

        assert _uids(ordered) == ["task_high", "task_medium", "task_low", "task_none"]

    def test_goals_no_priority_after_low(self) -> None:
        ordered = _apply_goal_sort(_goals_with_none(), "priority")

        assert _uids(ordered) == ["goal_high", "goal_medium", "goal_low", "goal_none"]

    def test_choices_no_priority_after_low(self) -> None:
        ordered = _apply_choice_sort(_choices_with_none(), "priority")

        assert _uids(ordered) == ["choice_high", "choice_medium", "choice_low", "choice_none"]


class TestThePeakEnergyBucket:
    def test_a_mastery_task_with_no_priority_comes_after_a_medium_one(self) -> None:
        service = CalendarOptimizationService()
        profile = service._get_user_energy_profile(USER)
        slots = service._generate_available_slots(EARLY, [], profile)
        none = _task("task_none", None, knowledge_mastery_check=True)
        medium = _task("task_medium", Priority.MEDIUM, knowledge_mastery_check=True)
        high = _task("task_high", Priority.HIGH)

        schedule = service._apply_energy_aligned_strategy(slots, [none, medium, high], profile)[
            "schedule"
        ]

        peak_slots = sorted(
            (s for s in slots if s.energy_level in (SlotEnergyLevel.PEAK, SlotEnergyLevel.HIGH)),
            key=attrgetter("cognitive_capacity"),
            reverse=True,
        )
        # The MEDIUM task sits in the medium bucket too, which places it again; the
        # bucket's order shows in the slot the no-priority task takes.
        assert schedule["task_high"]["slot"] is peak_slots[0]
        assert schedule["task_none"]["slot"] is peak_slots[2]
