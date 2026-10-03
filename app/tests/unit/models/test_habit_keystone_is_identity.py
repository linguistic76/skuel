"""A keystone habit is an identity habit — there is no second predicate.

``Habit`` carries no ``total_attempts`` and no consistency score of its own; the
habit's one consistency measure is the derived ``success_rate``. The keystone
readers (the list filter, the stats chip) read ``is_identity_habit`` by name, and
no alias stands in for it. Record: /docs/roadmap/habit-completion-persistence-bundle.md.
"""

from __future__ import annotations

from dataclasses import fields

from core.models.enums.entity_enums import EntityStatus
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.utils.activity_stats import compute_habit_stats
from core.utils.entity_filters import filter_habits


def _habit(uid: str, *, identity: bool, streak: int = 0) -> Habit:
    return Habit(
        uid=uid,
        title=uid,
        user_uid="user_1",
        status=EntityStatus.ACTIVE,
        is_identity_habit=identity,
        current_streak=streak,
    )


def test_total_attempts_is_gone_from_model_and_dto() -> None:
    assert "total_attempts" not in {f.name for f in fields(Habit)}
    assert "total_attempts" not in {f.name for f in fields(HabitDTO)}


def test_habit_has_no_consistency_score_or_keystone_alias() -> None:
    for name in ("calculate_consistency_score", "is_keystone", "predict_goal_impact"):
        assert getattr(Habit, name, None) is None, name


def test_keystone_filter_is_the_identity_habits() -> None:
    habits = [_habit("h_identity", identity=True), _habit("h_plain", identity=False, streak=40)]

    keystone = filter_habits(habits, status_filter="keystone")

    assert [h.uid for h in keystone] == ["h_identity"]


def test_keystone_count_is_the_identity_habit_count() -> None:
    habits = [
        _habit("h_1", identity=True),
        _habit("h_2", identity=True),
        _habit("h_3", identity=False, streak=40),
    ]

    assert compute_habit_stats(habits).keystone_count == 2
