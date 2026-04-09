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
    AlignedEntity,
    CrossDomainQueryService,
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
