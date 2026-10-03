"""
Unit tests for CrossDomainQueryService
=======================================

Each test mocks the injected ``CrossDomainBackendOperations`` and asserts
typed result transformation. The backend handles Cypher execution; the
service transforms raw dicts into typed dataclasses.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from core.models.habit.adherence import adherence_window_days
from core.services.cross_domain import (
    ActiveTaskCount,
    AlignedEntity,
    ChoiceAlignmentDetail,
    ChoicePrincipleAdherence,
    ChoicePrincipleConflictCount,
    CrossDomainQueryService,
    HabitKnowledgeReinforcement,
    KnowledgeApplyingTask,
    TasksForKnowledge,
)
from core.utils.result_simplified import Errors, Result
from core.utils.timestamp_helpers import as_stored_clock, local_day_bounds, today_in
from core.utils.zone_context import current_zone


@pytest.fixture
def mock_backend() -> AsyncMock:
    """Mock CrossDomainBackendOperations."""
    return AsyncMock()


@pytest.fixture
def service(mock_backend: AsyncMock) -> CrossDomainQueryService:
    return CrossDomainQueryService(mock_backend)


# ---------------------------------------------------------------------------
# get_tasks_applying_knowledge
# ---------------------------------------------------------------------------


class TestGetTasksApplyingKnowledge:
    @pytest.mark.asyncio
    async def test_returns_typed_result(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.get_tasks_applying_knowledge.return_value = Result.ok(
            [
                {"uid": "task_1", "title": "Ship feature", "rel": "APPLIES_KNOWLEDGE"},
                {"uid": "task_2", "title": "Write tests", "rel": "REQUIRES_KNOWLEDGE"},
            ]
        )

        result = await service.get_tasks_applying_knowledge(
            knowledge_uid="ku_python", user_uid="user_mike", limit=10
        )

        assert result.is_ok
        payload = result.value
        assert isinstance(payload, TasksForKnowledge)
        assert payload.knowledge_uid == "ku_python"
        assert payload.user_uid == "user_mike"
        assert len(payload.tasks) == 2
        assert payload.tasks[0] == KnowledgeApplyingTask(
            uid="task_1", title="Ship feature", relationship="APPLIES_KNOWLEDGE"
        )
        assert payload.tasks[1].relationship == "REQUIRES_KNOWLEDGE"

        mock_backend.get_tasks_applying_knowledge.assert_awaited_once_with(
            knowledge_uid="ku_python", user_uid="user_mike", limit=10
        )

    @pytest.mark.asyncio
    async def test_empty_rows_returns_empty_tuple(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.get_tasks_applying_knowledge.return_value = Result.ok([])

        result = await service.get_tasks_applying_knowledge(
            knowledge_uid="ku_unused", user_uid="user_mike"
        )

        assert result.is_ok
        assert result.value.tasks == ()

    @pytest.mark.asyncio
    async def test_propagates_backend_error(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.get_tasks_applying_knowledge.return_value = Result.fail(
            Errors.database(operation="get_tasks_applying_knowledge", message="neo4j down")
        )

        result = await service.get_tasks_applying_knowledge(
            knowledge_uid="ku_python", user_uid="user_mike"
        )

        assert result.is_error

    @pytest.mark.asyncio
    async def test_skips_rows_without_uid(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.get_tasks_applying_knowledge.return_value = Result.ok(
            [
                {"uid": "task_1", "title": "Good", "rel": "APPLIES_KNOWLEDGE"},
                {"uid": None, "title": "Skipped", "rel": "APPLIES_KNOWLEDGE"},
                {"uid": "", "title": "Also skipped", "rel": "APPLIES_KNOWLEDGE"},
            ]
        )

        result = await service.get_tasks_applying_knowledge(
            knowledge_uid="ku_python", user_uid="user_mike"
        )

        assert result.is_ok
        assert len(result.value.tasks) == 1
        assert result.value.tasks[0].uid == "task_1"


# ---------------------------------------------------------------------------
# get_goals_for_tasks_batch
# ---------------------------------------------------------------------------


class TestGetGoalsForTasksBatch:
    @pytest.mark.asyncio
    async def test_returns_map_of_aligned_entities(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.get_goals_for_tasks_batch.return_value = Result.ok(
            [
                {
                    "task_uid": "task_1",
                    "goals": [
                        {"uid": "goal_1", "title": "Ship v2"},
                        {"uid": "goal_2", "title": "Learn Cypher"},
                    ],
                },
                {"task_uid": "task_2", "goals": []},
            ]
        )

        result = await service.get_goals_for_tasks_batch(task_uids=["task_1", "task_2"])

        assert result.is_ok
        goals_by_task = result.value
        assert set(goals_by_task.keys()) == {"task_1", "task_2"}
        assert goals_by_task["task_1"] == (
            AlignedEntity(uid="goal_1", title="Ship v2"),
            AlignedEntity(uid="goal_2", title="Learn Cypher"),
        )
        assert goals_by_task["task_2"] == ()
        mock_backend.get_goals_for_tasks_batch.assert_awaited_once_with(
            task_uids=["task_1", "task_2"]
        )

    @pytest.mark.asyncio
    async def test_empty_input_short_circuits(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        result = await service.get_goals_for_tasks_batch(task_uids=[])

        assert result.is_ok
        assert result.value == {}
        mock_backend.get_goals_for_tasks_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_propagates_backend_error(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.get_goals_for_tasks_batch.return_value = Result.fail(
            Errors.database(operation="get_goals_for_tasks_batch", message="neo4j down")
        )

        result = await service.get_goals_for_tasks_batch(task_uids=["task_1"])

        assert result.is_error


# ---------------------------------------------------------------------------
# count_active_tasks_for_goal
# ---------------------------------------------------------------------------


class TestCountActiveTasksForGoal:
    @pytest.mark.asyncio
    async def test_returns_count(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.count_active_tasks_for_goal.return_value = Result.ok([{"count": 3}])

        result = await service.count_active_tasks_for_goal(goal_uid="goal_1")

        assert result.is_ok
        assert result.value == ActiveTaskCount(goal_uid="goal_1", count=3)
        mock_backend.count_active_tasks_for_goal.assert_awaited_once_with(goal_uid="goal_1")

    @pytest.mark.asyncio
    async def test_zero_when_empty(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.count_active_tasks_for_goal.return_value = Result.ok([])

        result = await service.count_active_tasks_for_goal(goal_uid="goal_orphan")

        assert result.is_ok
        assert result.value == ActiveTaskCount(goal_uid="goal_orphan", count=0)

    @pytest.mark.asyncio
    async def test_propagates_error(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.count_active_tasks_for_goal.return_value = Result.fail(
            Errors.database(operation="count_active_tasks_for_goal", message="neo4j down")
        )

        result = await service.count_active_tasks_for_goal(goal_uid="goal_1")

        assert result.is_error


# ---------------------------------------------------------------------------
# get_habit_knowledge_reinforcement (Habits migration — N=4)
# ---------------------------------------------------------------------------


def _habit_record(
    uid: str,
    ku_uids: list[str],
    *,
    done_days_ago: list[int],
    last_done_days_ago: int | None,
    pattern: str = "daily",
) -> dict[str, object]:
    """A reinforcement row as the backend projects it — stamps relative to today."""
    zone = current_zone()
    today = today_in(zone)

    def stamp(days_ago: int) -> str:
        start, _ = local_day_bounds(today - timedelta(days=days_ago), zone)
        return as_stored_clock(start + timedelta(hours=9)).isoformat()

    return {
        "habit_uid": uid,
        "current_streak": 10,
        "status": "active",
        "recurrence_pattern": pattern,
        "target_days_per_week": None,
        "created_at": stamp(90),
        "last_completed": stamp(last_done_days_ago) if last_done_days_ago is not None else None,
        "completion_stamps": [stamp(n) for n in done_days_ago],
        "ku_uids": ku_uids,
    }


class TestGetHabitKnowledgeReinforcement:
    @pytest.mark.asyncio
    async def test_returns_typed_rows_with_the_derived_rate_and_risk(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        """The rate is counted from the window stamps (24/30, 9/30); at risk is the one
        definition — the kept habit is not, the one last done three days ago is."""
        mock_backend.get_habit_knowledge_reinforcement.return_value = Result.ok(
            [
                _habit_record(
                    "habit_1",
                    ["ku_a", "ku_b"],
                    done_days_ago=list(range(1, 25)),
                    last_done_days_ago=1,
                ),
                _habit_record(
                    "habit_2", ["ku_c"], done_days_ago=list(range(3, 12)), last_done_days_ago=3
                ),
                _habit_record(
                    "habit_3",
                    ["ku_d"],
                    done_days_ago=[],
                    last_done_days_ago=10,
                    pattern="quarterly",
                ),
            ]
        )

        result = await service.get_habit_knowledge_reinforcement(user_uid="user_mike")

        assert result.is_ok
        rows = result.value
        assert isinstance(rows, tuple)
        assert rows[0] == HabitKnowledgeReinforcement(
            habit_uid="habit_1",
            current_streak=10,
            success_rate=0.8,
            at_risk=False,
            status="active",
            ku_uids=("ku_a", "ku_b"),
        )
        assert rows[1].success_rate == pytest.approx(0.3)
        assert rows[1].at_risk is True
        # A cadence the window cannot hold has no rate — None, never 0.0.
        assert (rows[2].success_rate, rows[2].at_risk) == (None, False)

        first_day, last_day = adherence_window_days(current_zone())
        mock_backend.get_habit_knowledge_reinforcement.assert_awaited_once_with(
            user_uid="user_mike",
            window_start=first_day.isoformat(),
            window_end=last_day.isoformat(),
        )

    @pytest.mark.asyncio
    async def test_skips_rows_with_no_kus(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.get_habit_knowledge_reinforcement.return_value = Result.ok(
            [
                _habit_record("habit_lone", [], done_days_ago=[1], last_done_days_ago=1),
                _habit_record("habit_with_ku", ["ku_x"], done_days_ago=[1], last_done_days_ago=1),
            ]
        )

        result = await service.get_habit_knowledge_reinforcement(user_uid="user_mike")

        assert result.is_ok
        rows = result.value
        assert len(rows) == 1
        assert rows[0].habit_uid == "habit_with_ku"

    @pytest.mark.asyncio
    async def test_propagates_backend_error(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.get_habit_knowledge_reinforcement.return_value = Result.fail(
            Errors.database(operation="get_habit_knowledge_reinforcement", message="neo4j down")
        )

        result = await service.get_habit_knowledge_reinforcement(user_uid="user_mike")

        assert result.is_error


# ---------------------------------------------------------------------------
# get_choice_principle_adherence (Choices migration — N=5)
# ---------------------------------------------------------------------------


class TestGetChoicePrincipleAdherence:
    @pytest.mark.asyncio
    async def test_returns_typed_result(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.get_choice_principle_adherence.return_value = Result.ok(
            [
                {
                    "total_choices": 10,
                    "aligned_count": 7,
                    "choice_details": [
                        {
                            "choice_uid": "choice_1",
                            "principles": ["principle_a", "principle_b"],
                            "satisfaction": 4.0,
                        },
                        {
                            "choice_uid": "choice_2",
                            "principles": [],
                            "satisfaction": None,
                        },
                    ],
                }
            ]
        )

        result = await service.get_choice_principle_adherence(user_uid="user_mike", period_days=90)

        assert result.is_ok
        adherence = result.value
        assert isinstance(adherence, ChoicePrincipleAdherence)
        assert adherence.total_choices == 10
        assert adherence.aligned_count == 7
        assert len(adherence.choice_details) == 2
        assert adherence.choice_details[0] == ChoiceAlignmentDetail(
            choice_uid="choice_1",
            principle_uids=("principle_a", "principle_b"),
            satisfaction=4.0,
        )
        assert adherence.choice_details[1].principle_uids == ()

        mock_backend.get_choice_principle_adherence.assert_awaited_once_with(
            user_uid="user_mike", period_days=90
        )

    @pytest.mark.asyncio
    async def test_empty_result(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.get_choice_principle_adherence.return_value = Result.ok([])

        result = await service.get_choice_principle_adherence(user_uid="user_mike", period_days=90)

        assert result.is_ok
        assert result.value == ChoicePrincipleAdherence(
            total_choices=0, aligned_count=0, choice_details=()
        )

    @pytest.mark.asyncio
    async def test_propagates_error(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.get_choice_principle_adherence.return_value = Result.fail(
            Errors.database(operation="get_choice_principle_adherence", message="neo4j down")
        )

        result = await service.get_choice_principle_adherence(user_uid="user_mike", period_days=90)

        assert result.is_error


# ---------------------------------------------------------------------------
# get_choice_conflict_count (Choices migration — N=5)
# ---------------------------------------------------------------------------


class TestGetChoiceConflictCount:
    @pytest.mark.asyncio
    async def test_returns_count(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.get_choice_conflict_count.return_value = Result.ok([{"conflict_count": 3}])

        result = await service.get_choice_conflict_count(user_uid="user_mike")

        assert result.is_ok
        assert result.value == ChoicePrincipleConflictCount(conflict_count=3)
        mock_backend.get_choice_conflict_count.assert_awaited_once_with(user_uid="user_mike")

    @pytest.mark.asyncio
    async def test_empty_result(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.get_choice_conflict_count.return_value = Result.ok([])

        result = await service.get_choice_conflict_count(user_uid="user_mike")

        assert result.is_ok
        assert result.value == ChoicePrincipleConflictCount(conflict_count=0)

    @pytest.mark.asyncio
    async def test_propagates_error(
        self, service: CrossDomainQueryService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.get_choice_conflict_count.return_value = Result.fail(
            Errors.database(operation="get_choice_conflict_count", message="neo4j down")
        )

        result = await service.get_choice_conflict_count(user_uid="user_mike")

        assert result.is_error
