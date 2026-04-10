"""
Unit tests for CrossDomainQueryService Tasks methods
====================================================

Covers the two methods added for the Tasks migration (N=2 validation of the
CrossDomainQueryService pattern):

- ``get_tasks_applying_knowledge`` — tasks a user owns that engage with a
  knowledge unit via APPLIES_KNOWLEDGE or REQUIRES_KNOWLEDGE edges.
- ``get_goals_for_task`` — goals a task contributes to or fulfills.

Each test mocks the injected ``QueryExecutor`` and asserts exactly one
``execute_query`` call, matching the service's "one Cypher per method" rule.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

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


@pytest.fixture
def mock_executor() -> AsyncMock:
    """Mock QueryExecutor — the only dependency of CrossDomainQueryService."""
    return AsyncMock()


@pytest.fixture
def service(mock_executor: AsyncMock) -> CrossDomainQueryService:
    return CrossDomainQueryService(mock_executor)


# ---------------------------------------------------------------------------
# get_tasks_applying_knowledge
# ---------------------------------------------------------------------------


class TestGetTasksApplyingKnowledge:
    @pytest.mark.asyncio
    async def test_returns_typed_result(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.ok(
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

        # Exactly one Cypher round-trip.
        assert mock_executor.execute_query.await_count == 1
        call_args = mock_executor.execute_query.call_args
        params = call_args.args[1]
        assert params["knowledge_uid"] == "ku_python"
        assert params["user_uid"] == "user_mike"
        assert params["limit"] == 10

    @pytest.mark.asyncio
    async def test_empty_rows_returns_empty_tuple(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.ok([])

        result = await service.get_tasks_applying_knowledge(
            knowledge_uid="ku_unused", user_uid="user_mike"
        )

        assert result.is_ok
        assert result.value.tasks == ()

    @pytest.mark.asyncio
    async def test_propagates_executor_error(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.fail(
            Errors.database(operation="execute_query", message="neo4j down")
        )

        result = await service.get_tasks_applying_knowledge(
            knowledge_uid="ku_python", user_uid="user_mike"
        )

        assert result.is_error

    @pytest.mark.asyncio
    async def test_skips_rows_without_uid(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.ok(
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
# get_goals_for_task
# ---------------------------------------------------------------------------


class TestGetGoalsForTask:
    @pytest.mark.asyncio
    async def test_returns_aligned_entities(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.ok(
            [
                {"uid": "goal_1", "title": "Ship v2"},
                {"uid": "goal_2", "title": "Learn Cypher"},
            ]
        )

        result = await service.get_goals_for_task(task_uid="task_1")

        assert result.is_ok
        goals = result.value
        assert isinstance(goals, tuple)
        assert len(goals) == 2
        assert goals[0] == AlignedEntity(uid="goal_1", title="Ship v2")
        assert goals[1] == AlignedEntity(uid="goal_2", title="Learn Cypher")
        # Exactly one Cypher round-trip.
        assert mock_executor.execute_query.await_count == 1
        params = mock_executor.execute_query.call_args.args[1]
        assert params["task_uid"] == "task_1"

    @pytest.mark.asyncio
    async def test_empty_rows_returns_empty_tuple(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.ok([])

        result = await service.get_goals_for_task(task_uid="task_orphan")

        assert result.is_ok
        assert result.value == ()

    @pytest.mark.asyncio
    async def test_propagates_executor_error(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.fail(
            Errors.database(operation="execute_query", message="neo4j down")
        )

        result = await service.get_goals_for_task(task_uid="task_1")

        assert result.is_error


# ---------------------------------------------------------------------------
# count_active_tasks_for_goal
# ---------------------------------------------------------------------------


class TestCountActiveTasksForGoal:
    @pytest.mark.asyncio
    async def test_returns_count(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.ok([{"count": 3}])

        result = await service.count_active_tasks_for_goal(goal_uid="goal_1")

        assert result.is_ok
        assert result.value == ActiveTaskCount(goal_uid="goal_1", count=3)

        # Exactly one Cypher round-trip.
        assert mock_executor.execute_query.await_count == 1
        params = mock_executor.execute_query.call_args.args[1]
        assert params["goal_uid"] == "goal_1"
        # Active statuses passed as a list, sourced from the EntityStatus enum.
        assert isinstance(params["active_statuses"], list)
        assert "active" in params["active_statuses"]
        assert "scheduled" in params["active_statuses"]
        assert "blocked" in params["active_statuses"]
        assert "paused" in params["active_statuses"]

    @pytest.mark.asyncio
    async def test_zero_when_empty(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.ok([])

        result = await service.count_active_tasks_for_goal(goal_uid="goal_orphan")

        assert result.is_ok
        assert result.value == ActiveTaskCount(goal_uid="goal_orphan", count=0)

    @pytest.mark.asyncio
    async def test_propagates_error(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.fail(
            Errors.database(operation="execute_query", message="neo4j down")
        )

        result = await service.count_active_tasks_for_goal(goal_uid="goal_1")

        assert result.is_error


# ---------------------------------------------------------------------------
# get_habit_knowledge_reinforcement (Habits migration — N=4)
# ---------------------------------------------------------------------------


class TestGetHabitKnowledgeReinforcement:
    @pytest.mark.asyncio
    async def test_returns_typed_rows(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.ok(
            [
                {
                    "habit_uid": "habit_1",
                    "current_streak": 10,
                    "success_rate": 0.8,
                    "status": "active",
                    "ku_uids": ["ku_a", "ku_b"],
                },
                {
                    "habit_uid": "habit_2",
                    "current_streak": 0,
                    "success_rate": 0.3,
                    "status": "active",
                    "ku_uids": ["ku_c"],
                },
            ]
        )

        result = await service.get_habit_knowledge_reinforcement(user_uid="user_mike")

        assert result.is_ok
        rows = result.value
        assert isinstance(rows, tuple)
        assert len(rows) == 2
        assert rows[0] == HabitKnowledgeReinforcement(
            habit_uid="habit_1",
            current_streak=10,
            success_rate=0.8,
            status="active",
            ku_uids=("ku_a", "ku_b"),
        )
        assert rows[1].habit_uid == "habit_2"

        assert mock_executor.execute_query.await_count == 1
        params = mock_executor.execute_query.call_args.args[1]
        assert params["user_uid"] == "user_mike"
        assert "active" in params["active_statuses"]
        assert "pending" in params["active_statuses"]

    @pytest.mark.asyncio
    async def test_skips_rows_with_no_kus(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.ok(
            [
                {
                    "habit_uid": "habit_lone",
                    "current_streak": 5,
                    "success_rate": 0.9,
                    "status": "active",
                    "ku_uids": [],
                },
                {
                    "habit_uid": "habit_with_ku",
                    "current_streak": 1,
                    "success_rate": 0.5,
                    "status": "active",
                    "ku_uids": ["ku_x"],
                },
            ]
        )

        result = await service.get_habit_knowledge_reinforcement(user_uid="user_mike")

        assert result.is_ok
        rows = result.value
        assert len(rows) == 1
        assert rows[0].habit_uid == "habit_with_ku"

    @pytest.mark.asyncio
    async def test_propagates_executor_error(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.fail(
            Errors.database(operation="execute_query", message="neo4j down")
        )

        result = await service.get_habit_knowledge_reinforcement(user_uid="user_mike")

        assert result.is_error


# ---------------------------------------------------------------------------
# get_choice_principle_adherence (Choices migration — N=5)
# ---------------------------------------------------------------------------


class TestGetChoicePrincipleAdherence:
    @pytest.mark.asyncio
    async def test_returns_typed_result(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.ok(
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

        assert mock_executor.execute_query.await_count == 1
        params = mock_executor.execute_query.call_args.args[1]
        assert params["user_uid"] == "user_mike"
        assert params["period_days"] == 90

    @pytest.mark.asyncio
    async def test_empty_result(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.ok([])

        result = await service.get_choice_principle_adherence(user_uid="user_mike", period_days=90)

        assert result.is_ok
        assert result.value == ChoicePrincipleAdherence(
            total_choices=0, aligned_count=0, choice_details=()
        )

    @pytest.mark.asyncio
    async def test_propagates_error(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.fail(
            Errors.database(operation="execute_query", message="neo4j down")
        )

        result = await service.get_choice_principle_adherence(user_uid="user_mike", period_days=90)

        assert result.is_error


# ---------------------------------------------------------------------------
# get_choice_conflict_count (Choices migration — N=5)
# ---------------------------------------------------------------------------


class TestGetChoiceConflictCount:
    @pytest.mark.asyncio
    async def test_returns_count(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.ok([{"conflict_count": 3}])

        result = await service.get_choice_conflict_count(user_uid="user_mike")

        assert result.is_ok
        assert result.value == ChoicePrincipleConflictCount(conflict_count=3)

        assert mock_executor.execute_query.await_count == 1
        params = mock_executor.execute_query.call_args.args[1]
        assert params["user_uid"] == "user_mike"

    @pytest.mark.asyncio
    async def test_empty_result(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.ok([])

        result = await service.get_choice_conflict_count(user_uid="user_mike")

        assert result.is_ok
        assert result.value == ChoicePrincipleConflictCount(conflict_count=0)

    @pytest.mark.asyncio
    async def test_propagates_error(
        self, service: CrossDomainQueryService, mock_executor: AsyncMock
    ) -> None:
        mock_executor.execute_query.return_value = Result.fail(
            Errors.database(operation="execute_query", message="neo4j down")
        )

        result = await service.get_choice_conflict_count(user_uid="user_mike")

        assert result.is_error
