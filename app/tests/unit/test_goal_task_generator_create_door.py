"""``GoalTaskGenerator`` persists through the Tasks entity door, never a backend.

``TasksCoreService.create`` is the one create path for Tasks: the creation rule
(``Task.with_creation_due_date``), the entity-carried link edges (FULFILLS_GOAL,
REINFORCES_HABIT), ``TaskCreated`` and the ADR-074 embedding request all happen
there — so a task that reaches the graph any other way reaches it undated (absent
from Today and the calendar), un-announced and un-embedded. Pinned here with a
fake Tasks facade:

- every generated task reaches ``tasks_service.create`` as a ``Task``;
- a habit-reinforcement task carries its habit as ``reinforces_habit_uid`` — the
  edge's INPUT on create — so the primitive writes the edge, not the generator;
- ``auto_create=False`` persists nothing;
- a failed create is skipped, the rest still land.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.models.enums import EntityStatus
from core.models.goal.goal import Goal
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.services.goal_task_generator import GoalTaskGenerator, TaskGenerationConfig
from core.services.goals.goal_relationships import GoalRelationships
from core.services.user import UserContext
from core.utils.result_simplified import Errors, Result

GOAL_UID = "goal_gen_fixture"
USER = "user_gen"


class _FakeTasksFacade:
    """Records what reaches the entity door; echoes the task back as persisted."""

    def __init__(self, *, refuse_titles: frozenset[str] = frozenset()) -> None:
        self.created: list[Task] = []
        self.refuse_titles = refuse_titles

    async def create(self, entity: Task) -> Result[Task]:
        if entity.title in self.refuse_titles:
            return Result.fail(Errors.database("create", "refused by the fixture"))
        self.created.append(entity)
        return Result.ok(entity)


class _FakeGoalsBackend:
    def __init__(self, goal: Goal) -> None:
        self._goal = goal

    async def get_goal(self, goal_uid: str) -> Result[dict[str, Any]]:
        assert goal_uid == self._goal.uid
        return Result.ok(self._goal.to_dto().to_dict())


def _goal() -> Goal:
    return Goal(uid=GOAL_UID, user_uid=USER, title="Ship it", status=EntityStatus.ACTIVE)


def _context(**overrides: Any) -> UserContext:
    return UserContext(user_uid=USER, **overrides)


@pytest.fixture
def rels(monkeypatch: pytest.MonkeyPatch) -> GoalRelationships:
    fixed = GoalRelationships(
        required_knowledge_uids=["ku.python.basics"],
        supporting_habit_uids=["habit_daily_read"],
    )

    async def fetch(cls: Any, goal_uid: str, service: Any) -> GoalRelationships:
        return fixed

    monkeypatch.setattr(GoalRelationships, "fetch", classmethod(fetch))
    return fixed


def _generator(facade: _FakeTasksFacade) -> GoalTaskGenerator:
    return GoalTaskGenerator(
        goals_backend=_FakeGoalsBackend(_goal()),  # type: ignore[arg-type]
        tasks_service=facade,  # type: ignore[arg-type]
        relationship_service=object(),  # truthy → GoalRelationships.fetch (patched) runs
        config=TaskGenerationConfig(generate_check_in_tasks=False),
    )


@pytest.mark.asyncio
async def test_every_generated_task_reaches_the_entity_door_as_a_task(rels) -> None:
    facade = _FakeTasksFacade()
    result = await _generator(facade).generate_tasks_for_goal(
        GOAL_UID, _context(), auto_create=True
    )

    assert result.is_ok
    assert facade.created, "nothing reached the entity door"
    assert all(isinstance(t, Task) for t in facade.created)
    # The knowledge task is built undated — the shape the door's creation rule
    # exists for — so reaching the door is what puts it on a day.
    knowledge = [t for t in facade.created if t.title == "Learn: ku.python.basics"]
    assert len(knowledge) == 1
    assert knowledge[0].fulfills_goal_uid == GOAL_UID
    assert [dto.uid for dto in result.value] == [t.uid for t in facade.created]
    assert all(isinstance(dto, TaskDTO) for dto in result.value)


@pytest.mark.asyncio
async def test_a_habit_task_carries_its_habit_on_the_entity(rels) -> None:
    """The primitive writes REINFORCES_HABIT from ``reinforces_habit_uid`` —
    the generator sets the input, it does not write the edge itself."""
    facade = _FakeTasksFacade()
    await _generator(facade).generate_tasks_for_goal(
        GOAL_UID, _context(habit_streaks={"habit_daily_read": 2}), auto_create=True
    )

    habit_tasks = [t for t in facade.created if t.title == "Practice habit: habit_daily_read"]
    assert len(habit_tasks) == 1
    assert habit_tasks[0].reinforces_habit_uid == "habit_daily_read"
    assert habit_tasks[0].fulfills_goal_uid == GOAL_UID
    # The link rides only on the habit task.
    others = [t for t in facade.created if t is not habit_tasks[0]]
    assert all(t.reinforces_habit_uid is None for t in others)


@pytest.mark.asyncio
async def test_templates_only_persist_nothing(rels) -> None:
    facade = _FakeTasksFacade()
    result = await _generator(facade).generate_tasks_for_goal(
        GOAL_UID, _context(), auto_create=False
    )
    assert result.is_ok and result.value
    assert facade.created == []


@pytest.mark.asyncio
async def test_a_refused_create_is_skipped_and_the_rest_land(rels) -> None:
    facade = _FakeTasksFacade(refuse_titles=frozenset({"Learn: ku.python.basics"}))
    result = await _generator(facade).generate_tasks_for_goal(
        GOAL_UID, _context(habit_streaks={"habit_daily_read": 0}), auto_create=True
    )
    assert result.is_ok
    titles = {dto.title for dto in result.value}
    assert "Learn: ku.python.basics" not in titles
    assert "Practice habit: habit_daily_read" in titles
