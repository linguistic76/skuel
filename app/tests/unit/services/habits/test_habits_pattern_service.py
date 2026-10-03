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

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from neo4j.exceptions import ServiceUnavailable

from core.models.enums.scheduling_enums import RecurrencePattern
from core.models.habit.habit import Habit
from core.services.habits.habits_pattern_service import HabitsPatternService
from core.utils.result_simplified import Errors, Result
from core.utils.timestamp_helpers import as_stored_clock, local_day_bounds, today_in
from core.utils.zone_context import current_zone

USER_UID = "user_test"
HABIT_UID = "habit_pattern_test"


def _habit(**kwargs) -> Habit:
    defaults = {
        "uid": HABIT_UID,
        "title": "Morning Reading",
        "user_uid": USER_UID,
        # Older than the adherence window, so the rate is measured over all of it.
        "created_at": as_stored_clock(
            local_day_bounds(today_in(current_zone()) - timedelta(days=90), current_zone())[0]
        ),
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


class _WindowCompletionsBackend:
    """The habits backend's window read: one completion on each of the given days ago."""

    def __init__(self, days_ago: list[int]) -> None:
        self._days_ago = days_ago

    async def get_habit_window_completions(
        self, habit_uids: list[str], window_start: str, window_end: str
    ) -> Result[dict[str, list[object]]]:
        zone = current_zone()
        today = today_in(zone)
        stamps = [
            as_stored_clock(
                local_day_bounds(today - timedelta(days=n), zone)[0] + timedelta(hours=9)
            ).isoformat()
            for n in self._days_ago
        ]
        return Result.ok({uid: stamps for uid in habit_uids})


def _service(
    relationships, habit: Habit | None = None, done_days_ago: list[int] | None = None
) -> HabitsPatternService:
    """24 of the last 30 days kept (0.8) unless told otherwise."""
    habits_core = AsyncMock()
    habits_core.verify_ownership.return_value = Result.ok(habit or _habit())
    habits_core.backend = _WindowCompletionsBackend(
        done_days_ago if done_days_ago is not None else list(range(24))
    )
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


@pytest.mark.asyncio
async def test_the_patterns_read_the_derived_rate_not_the_one_carried_in() -> None:
    """A habit read with a stale 0.9 that kept 6 of 30 days reads 0.2 — the low-rate pattern."""
    service = _service(
        _RelationshipsStub(Result.ok([])),
        habit=_habit(success_rate=0.9),
        done_days_ago=[0, 1, 2, 3, 4, 5],
    )

    result = await service.analyze_patterns(HABIT_UID, USER_UID)

    assert result.is_ok
    assert "Low success rate: 20%" in _pattern_texts(result.value.failure_patterns)
    assert not any("High success rate" in p for p in _pattern_texts(result.value.success_patterns))


@pytest.mark.asyncio
async def test_a_habit_with_no_rate_shows_neither_rate_pattern() -> None:
    """A quarterly habit has no rate in a 30-day window — not a low one."""
    service = _service(
        _RelationshipsStub(Result.ok([])),
        habit=_habit(recurrence_pattern="quarterly"),
        done_days_ago=[],
    )

    result = await service.analyze_patterns(HABIT_UID, USER_UID)

    assert result.is_ok
    texts = _pattern_texts(result.value.success_patterns + result.value.failure_patterns)
    assert not any("success rate" in p for p in texts)


@pytest.mark.asyncio
async def test_goal_system_pattern_confidence_is_the_adherence_rate() -> None:
    """Pattern 5's confidence is the habit's derived rate — 24 of 30 days kept reads 0.8."""
    service = _service(_RelationshipsStub(Result.ok(["goal_1", "goal_2"])))

    result = await service.analyze_patterns(HABIT_UID, USER_UID)

    assert result.is_ok
    system = [
        p for p in result.value.success_patterns if "Part of goal system" in str(p["pattern"])
    ]
    assert len(system) == 1
    assert system[0]["confidence"] == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_goal_system_pattern_needs_a_rate() -> None:
    """A habit with no rate yet shows no system pattern — "effective" is a claim about
    adherence, and there is none to make it on. A weekly habit created today has had
    nothing due (``expected_completions`` rounds a partial period down to 0)."""
    young = _habit(
        created_at=as_stored_clock(local_day_bounds(today_in(current_zone()), current_zone())[0]),
        recurrence_pattern=RecurrencePattern.WEEKLY,
    )
    service = _service(
        _RelationshipsStub(Result.ok(["goal_1", "goal_2"])), habit=young, done_days_ago=[0]
    )

    result = await service.analyze_patterns(HABIT_UID, USER_UID)

    assert result.is_ok
    assert not any(
        "Part of goal system" in p for p in _pattern_texts(result.value.success_patterns)
    )
