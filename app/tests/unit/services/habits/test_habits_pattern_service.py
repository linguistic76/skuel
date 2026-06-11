"""
Unit tests for HabitsPatternService graph-derived system_contribution fill.

Habit.get_atomic_habits_analysis() emits conservative placeholders
(part_of_system=False, supports_goal_count=0) because the frozen domain model
cannot see the graph. HabitsPatternService.analyze_patterns() must overwrite
them from live SUPPORTS_GOAL edges BEFORE pattern extraction, so:

- Success pattern 5 ("Part of goal system (N goals)") can fire.
- Failure pattern 4 ("Habit not linked to goals") stops always-firing.

On relationship-fetch failure, the conservative placeholders must survive
(degrade, never fail the whole analysis).
"""

from unittest.mock import AsyncMock

import pytest
from neo4j.exceptions import ServiceUnavailable

from core.models.habit.habit import Habit
from core.services.habits.habits_pattern_service import HabitsPatternService
from core.utils.result_simplified import Errors, Result

USER_UID = "user_test"
HABIT_UID = "habit_pattern_test"


def _habit(**kwargs) -> Habit:
    defaults = {
        "uid": HABIT_UID,
        "title": "Morning Reading",
        "user_uid": USER_UID,
        "success_rate": 0.8,
        "current_streak": 5,
        "best_streak": 10,
        "total_completions": 40,
    }
    defaults.update(kwargs)
    return Habit(**defaults)


class _RelationshipsStub:
    """Plain stub for UnifiedRelationshipService (no MagicMock — the generic
    fetcher probes attributes with getattr, which MagicMock auto-creates)."""

    def __init__(self, goal_uids: Result, default: Result | None = None) -> None:
        self._goal_uids = goal_uids
        self._default = default if default is not None else Result.ok([])

    async def get_related_uids(self, relationship_key: str, entity_uid: str) -> Result:
        if relationship_key == "supported_goals":
            return self._goal_uids
        return self._default


class _RaisingRelationshipsStub:
    """Relationship service whose graph query raises (driver-level failure)."""

    async def get_related_uids(self, relationship_key: str, entity_uid: str) -> Result:
        raise ServiceUnavailable("neo4j down")


def _service(relationships, habit: Habit | None = None) -> HabitsPatternService:
    habits_core = AsyncMock()
    habits_core.verify_ownership.return_value = Result.ok(habit or _habit())
    return HabitsPatternService(habits_core=habits_core, relationships=relationships)


def _pattern_texts(patterns: list[dict]) -> list[str]:
    return [str(p["pattern"]) for p in patterns]


@pytest.mark.asyncio
async def test_graph_fill_makes_goal_system_pattern_fire() -> None:
    """With SUPPORTS_GOAL edges present, success pattern 5 fires with the live count."""
    service = _service(_RelationshipsStub(Result.ok(["goal_1", "goal_2"])))

    result = await service.analyze_patterns(HABIT_UID, USER_UID)

    assert result.is_ok
    success = _pattern_texts(result.value.success_patterns)
    assert any("Part of goal system (2 goals)" in p for p in success)
    failure = _pattern_texts(result.value.failure_patterns)
    assert not any("not linked to goals" in p for p in failure)


@pytest.mark.asyncio
async def test_no_goal_edges_keeps_failure_pattern() -> None:
    """With zero SUPPORTS_GOAL edges, failure pattern 4 fires and pattern 5 doesn't."""
    service = _service(_RelationshipsStub(Result.ok([])))

    result = await service.analyze_patterns(HABIT_UID, USER_UID)

    assert result.is_ok
    assert any("not linked to goals" in p for p in _pattern_texts(result.value.failure_patterns))
    assert not any(
        "Part of goal system" in p for p in _pattern_texts(result.value.success_patterns)
    )


@pytest.mark.asyncio
async def test_fetch_error_result_keeps_conservative_placeholders() -> None:
    """A failed relationship query degrades to the placeholders (not an analysis failure)."""
    service = _service(
        _RelationshipsStub(Result.fail(Errors.database("get_related_uids", "query failed")))
    )

    result = await service.analyze_patterns(HABIT_UID, USER_UID)

    assert result.is_ok
    # Conservative placeholders: treated as not part of a goal system.
    assert any("not linked to goals" in p for p in _pattern_texts(result.value.failure_patterns))


@pytest.mark.asyncio
async def test_driver_exception_keeps_conservative_placeholders() -> None:
    """A raised Neo4j driver exception is caught — analysis still succeeds."""
    service = _service(_RaisingRelationshipsStub())

    result = await service.analyze_patterns(HABIT_UID, USER_UID)

    assert result.is_ok
    assert any("not linked to goals" in p for p in _pattern_texts(result.value.failure_patterns))


@pytest.mark.asyncio
async def test_ownership_failure_propagates() -> None:
    """Ownership check failure short-circuits (404-shaped error, no graph fetch)."""
    habits_core = AsyncMock()
    habits_core.verify_ownership.return_value = Result.fail(Errors.not_found("Habit", HABIT_UID))
    service = HabitsPatternService(
        habits_core=habits_core, relationships=_RelationshipsStub(Result.ok([]))
    )

    result = await service.analyze_patterns(HABIT_UID, USER_UID)

    assert result.is_error
