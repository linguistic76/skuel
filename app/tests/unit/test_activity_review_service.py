"""
Unit Tests for ActivityReviewService
=====================================

Tests create_activity_snapshot() single round-trip consolidation.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.feedback.activity_review_service import ActivityReviewService
from core.utils.result_simplified import Result


@pytest.fixture
def mock_executor():
    executor = MagicMock()
    executor.execute_query = AsyncMock(return_value=Result.ok([]))
    return executor


@pytest.fixture
def mock_backend():
    backend = MagicMock()
    backend.create = AsyncMock()
    return backend


@pytest.fixture
def service(mock_executor, mock_backend):
    return ActivityReviewService(
        executor=mock_executor,
        ai_feedback_backend=mock_backend,
    )


# ============================================================================
# SINGLE ROUND-TRIP TESTS
# ============================================================================


class TestSnapshotSingleRoundTrip:
    """create_activity_snapshot() issues exactly one execute_query call."""

    @pytest.mark.asyncio
    async def test_single_query_call_all_domains(self, service):
        """All-domains snapshot uses 1 query (was 4)."""
        service.executor.execute_query.reset_mock()

        await service.create_activity_snapshot("user_alice")

        assert service.executor.execute_query.call_count == 1

    @pytest.mark.asyncio
    async def test_single_query_call_filtered_domains(self, service):
        """Domain-filtered snapshot still uses 1 query."""
        service.executor.execute_query.reset_mock()

        await service.create_activity_snapshot("user_alice", domains=["tasks", "goals"])

        assert service.executor.execute_query.call_count == 1


# ============================================================================
# EMPTY RESULT TESTS
# ============================================================================


class TestSnapshotEmptyResult:
    """Empty query results produce zero-count domain sections."""

    @pytest.mark.asyncio
    async def test_empty_result_all_domains_present(self, service):
        """Empty result still populates all 4 domain keys with zero counts."""
        result = await service.create_activity_snapshot("user_ghost")

        assert not result.is_error
        snapshot = result.value
        assert snapshot["domains"]["tasks"]["count"] == 0
        assert snapshot["domains"]["goals"]["count"] == 0
        assert snapshot["domains"]["habits"]["count"] == 0
        assert snapshot["domains"]["choices"]["count"] == 0

    @pytest.mark.asyncio
    async def test_empty_result_metadata_correct(self, service):
        """Snapshot metadata is populated regardless of activity data."""
        result = await service.create_activity_snapshot("user_ghost", time_period="30d")

        snapshot = result.value
        assert snapshot["subject_uid"] == "user_ghost"
        assert snapshot["time_period"] == "30d"
        assert "start_date" in snapshot
        assert "end_date" in snapshot


# ============================================================================
# DOMAIN FILTER TESTS
# ============================================================================


class TestSnapshotDomainFilter:
    """domains parameter limits which sections appear in the snapshot."""

    @pytest.mark.asyncio
    async def test_tasks_only_filter(self, service):
        """domains=['tasks'] → only tasks key in snapshot['domains']."""
        result = await service.create_activity_snapshot("user_alice", domains=["tasks"])

        snapshot = result.value
        assert "tasks" in snapshot["domains"]
        assert "goals" not in snapshot["domains"]
        assert "habits" not in snapshot["domains"]
        assert "choices" not in snapshot["domains"]

    @pytest.mark.asyncio
    async def test_goals_habits_filter(self, service):
        """domains=['goals','habits'] → only those two keys present."""
        result = await service.create_activity_snapshot(
            "user_alice", domains=["goals", "habits"]
        )

        snapshot = result.value
        assert "goals" in snapshot["domains"]
        assert "habits" in snapshot["domains"]
        assert "tasks" not in snapshot["domains"]
        assert "choices" not in snapshot["domains"]


# ============================================================================
# RECORD MAPPING TESTS
# ============================================================================


class TestSnapshotRecordMapping:
    """Records returned by the combined query are correctly shaped."""

    @pytest.mark.asyncio
    async def test_task_records_mapped(self, service):
        """task_records from query → tasks domain with completed count."""
        service.executor.execute_query.return_value = Result.ok(
            [
                {
                    "task_records": [
                        {"uid": "t1", "title": "Write tests", "status": "completed", "priority": "high"},
                        {"uid": "t2", "title": "Fix bug", "status": "active", "priority": "medium"},
                    ],
                    "goal_records": [],
                    "habit_records": [],
                    "choice_records": [],
                }
            ]
        )

        result = await service.create_activity_snapshot("user_alice")

        tasks = result.value["domains"]["tasks"]
        assert tasks["count"] == 2
        assert tasks["completed"] == 1
        assert tasks["items"][0]["title"] == "Write tests"
        assert tasks["items"][1]["title"] == "Fix bug"

    @pytest.mark.asyncio
    async def test_choice_principles_mapped(self, service):
        """principle_titles from CALL {} → choices items principles field."""
        service.executor.execute_query.return_value = Result.ok(
            [
                {
                    "task_records": [],
                    "goal_records": [],
                    "habit_records": [],
                    "choice_records": [
                        {
                            "uid": "c1",
                            "title": "Chose to rest",
                            "principle_titles": ["Recovery", "Balance"],
                        }
                    ],
                }
            ]
        )

        result = await service.create_activity_snapshot("user_alice")

        choices = result.value["domains"]["choices"]
        assert choices["count"] == 1
        assert choices["items"][0]["principles"] == ["Recovery", "Balance"]
