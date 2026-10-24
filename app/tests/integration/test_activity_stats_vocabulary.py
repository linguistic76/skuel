"""
The six Activity ``get_stats_for_user`` counts speak their model's vocabulary.

Each backend counts a user's entities in one Cypher aggregate, naming statuses and
fields as literals inside the statement. A literal the model does not use counts
nothing and raises nothing, so each domain is seeded with one entity per legal
status (plus the field each count reads, both ways), read back as models, and every
count must equal what the model's own predicate selects over the same rows.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any

import pytest

from adapters.persistence.neo4j.backends.activity_backends import (
    ChoicesBackend,
    EventsBackend,
    GoalsBackend,
    HabitsBackend,
    PrinciplesBackend,
    TasksBackend,
)
from core.models.choice.choice import Choice
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.principle_enums import PrincipleStrength
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.principle.principle import Principle
from core.models.task.task import Task
from core.models.user_owned_entity import UserOwnedEntity
from core.utils.timestamp_helpers import today_in
from core.utils.uid_grammar import slugify
from core.utils.zone_context import current_zone
from tests.helpers.seed_uids import seed_user_uid

_OWNER = seed_user_uid("stats_vocabulary")
_STRANGER = seed_user_uid("stats_vocabulary_stranger")


def _today() -> date:
    return today_in(current_zone())


def _tasks() -> list[Task]:
    return [
        Task(
            uid=f"task.{slugify(status.value)}.{when}",
            title="t",
            user_uid=_OWNER,
            status=status,
            due_date=_today() + timedelta(days=offset),
        )
        for status in EntityType.TASK.valid_statuses()
        for when, offset in (("past", -3), ("future", 3))
    ]


def _goals() -> list[Goal]:
    return [
        Goal(uid=f"goal.{slugify(status.value)}", title="g", user_uid=_OWNER, status=status)
        for status in EntityType.GOAL.valid_statuses()
    ]


def _habits() -> list[Habit]:
    return [
        Habit(
            uid=f"habit.{slugify(status.value)}.{streak}",
            title="h",
            user_uid=_OWNER,
            status=status,
            current_streak=streak,
        )
        for status in EntityType.HABIT.valid_statuses()
        for streak in (0, 4)
    ]


def _events() -> list[Event]:
    return [
        Event(
            uid=f"event.{slugify(status.value)}.{when}",
            title="e",
            user_uid=_OWNER,
            status=status,
            event_date=_today() + timedelta(days=offset),
        )
        for status in EntityType.EVENT.valid_statuses()
        for when, offset in (("today", 0), ("later", 2))
    ]


def _choices() -> list[Choice]:
    return [
        Choice(uid=f"choice.{slugify(status.value)}", title="c", user_uid=_OWNER, status=status)
        for status in EntityType.CHOICE.valid_statuses()
    ]


def _principles() -> list[Principle]:
    return [
        Principle(
            uid=f"principle.{slugify(status.value)}.{strength.value}-{'on' if active else 'off'}",
            title="p",
            user_uid=_OWNER,
            status=status,
            strength=strength,
            is_active=active,
        )
        for status in EntityType.PRINCIPLE.valid_statuses()
        for strength in (PrincipleStrength.CORE, PrincipleStrength.DEVELOPING)
        for active in (True, False)
    ]


def _task_completed(task: Task) -> bool:
    return task.is_completed


def _task_overdue(task: Task) -> bool:
    return task.is_overdue()


def _goal_active(goal: Goal) -> bool:
    return goal.is_active


def _goal_achieved(goal: Goal) -> bool:
    return goal.is_achieved()


def _habit_active(habit: Habit) -> bool:
    return habit.is_active


def _habit_on_a_streak(habit: Habit) -> bool:
    return habit.current_streak > 0


def _event_scheduled(event: Event) -> bool:
    return event.status == EntityStatus.SCHEDULED


def _event_today(event: Event) -> bool:
    return event.event_date == _today()


def _choice_pending(choice: Choice) -> bool:
    return choice.is_pending()


def _choice_decided(choice: Choice) -> bool:
    return choice.is_decided()


def _principle_core(principle: Principle) -> bool:
    return principle.strength == PrincipleStrength.CORE


def _principle_active(principle: Principle) -> bool:
    return principle.is_active


@dataclass(frozen=True)
class _Domain:
    """One Activity domain: how to build its backend, its seeds, and the model
    predicate behind each count ``get_stats_for_user`` returns."""

    backend_class: type[Any]  # boundary: heterogeneous — one row per domain backend
    label: NeoLabel
    model_class: type[UserOwnedEntity]
    seeds: Callable[[], Sequence[UserOwnedEntity]]
    # boundary: heterogeneous — each predicate reads its own domain model's fields
    predicates: dict[str, Callable[[Any], bool]]


_DOMAINS: dict[str, _Domain] = {
    "task": _Domain(
        TasksBackend,
        NeoLabel.TASK,
        Task,
        _tasks,
        {"completed": _task_completed, "overdue": _task_overdue},
    ),
    "goal": _Domain(
        GoalsBackend,
        NeoLabel.GOAL,
        Goal,
        _goals,
        {"active": _goal_active, "completed": _goal_achieved},
    ),
    "habit": _Domain(
        HabitsBackend,
        NeoLabel.HABIT,
        Habit,
        _habits,
        {"active": _habit_active, "streaks": _habit_on_a_streak},
    ),
    "event": _Domain(
        EventsBackend,
        NeoLabel.EVENT,
        Event,
        _events,
        {"scheduled": _event_scheduled, "today": _event_today},
    ),
    "choice": _Domain(
        ChoicesBackend,
        NeoLabel.CHOICE,
        Choice,
        _choices,
        {"pending": _choice_pending, "decided": _choice_decided},
    ),
    "principle": _Domain(
        PrinciplesBackend,
        NeoLabel.PRINCIPLE,
        Principle,
        _principles,
        {"core": _principle_core, "active": _principle_active},
    ),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", sorted(_DOMAINS))
async def test_each_count_is_the_models_predicate(neo4j_driver, clean_neo4j, domain: str) -> None:
    spec = _DOMAINS[domain]
    seeds, predicates = spec.seeds, spec.predicates
    backend = spec.backend_class(
        neo4j_driver, spec.label, spec.model_class, base_label=NeoLabel.ENTITY
    )
    async with neo4j_driver.session() as session:
        await session.run("UNWIND $uids AS uid MERGE (:User {uid: uid})", uids=[_OWNER, _STRANGER])
    for seed in seeds():
        created = await backend.create(seed)
        assert created.is_ok, created.expect_error()
    stranger = next(iter(seeds()))
    created = await backend.create(
        replace(stranger, uid=f"{stranger.uid}-stranger", user_uid=_STRANGER)
    )
    assert created.is_ok, created.expect_error()

    found = await backend.find_by(user_uid=_OWNER)
    assert found.is_ok, found.expect_error()
    models = list(found.value)
    assert len(models) == len(seeds())

    stats = await backend.get_stats_for_user(_OWNER)

    assert stats.is_ok, stats.expect_error()
    expected = {
        key: sum(1 for m in models if predicate(m)) for key, predicate in predicates.items()
    }
    assert stats.value == {"total": len(models), **expected}
    # The comparison is only worth something if every count splits the rows.
    for key, count in expected.items():
        assert 0 < count < len(models), (domain, key, count)
