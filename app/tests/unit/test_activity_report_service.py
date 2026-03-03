"""
Unit Tests for ActivityReportService
======================================

Tests create_snapshot() via UserContextBuilder.build_rich().
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.feedback.activity_report_service import ActivityReportService
from core.services.user.unified_user_context import UserContext
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


def _make_context(activity_rich: dict | None = None) -> UserContext:
    """Build a minimal UserContext with entities_rich populated."""
    context = UserContext(user_uid="user_ghost", username="ghost")
    context.entities_rich = activity_rich or {}
    return context


@pytest.fixture
def mock_context_builder():
    builder = MagicMock()
    builder.build_rich = AsyncMock(return_value=Result.ok(_make_context()))
    return builder


@pytest.fixture
def service(mock_executor, mock_backend, mock_context_builder):
    return ActivityReportService(
        backend=mock_backend,
        context_builder=mock_context_builder,
        executor=mock_executor,
    )


# ============================================================================
# SINGLE ROUND-TRIP TESTS
# ============================================================================


class TestSnapshotSingleRoundTrip:
    """create_snapshot() issues exactly one context_builder.build_rich() call."""

    @pytest.mark.asyncio
    async def test_single_query_call_all_domains(self, service, mock_context_builder):
        """All-domains snapshot uses 1 build_rich call."""
        mock_context_builder.build_rich.reset_mock()

        await service.create_snapshot("user_alice")

        assert mock_context_builder.build_rich.call_count == 1

    @pytest.mark.asyncio
    async def test_single_query_call_filtered_domains(self, service, mock_context_builder):
        """Domain-filtered snapshot still uses 1 build_rich call."""
        mock_context_builder.build_rich.reset_mock()

        await service.create_snapshot("user_alice", domains=["tasks", "goals"])

        assert mock_context_builder.build_rich.call_count == 1

    @pytest.mark.asyncio
    async def test_build_rich_called_with_window(self, service, mock_context_builder):
        """build_rich is called with window= instead of time_period=."""
        mock_context_builder.build_rich.reset_mock()

        await service.create_snapshot("user_alice", time_period="30d")

        call_kwargs = mock_context_builder.build_rich.call_args[1]
        assert call_kwargs.get("window") == "30d"


# ============================================================================
# EMPTY RESULT TESTS
# ============================================================================


class TestSnapshotEmptyResult:
    """Empty entities_rich produces zero-count domain sections."""

    @pytest.mark.asyncio
    async def test_empty_result_all_domains_present(self, service):
        """Empty result still populates all 6 domain keys with zero counts."""
        result = await service.create_snapshot("user_ghost")

        assert not result.is_error
        snapshot = result.value
        assert snapshot["domains"]["tasks"]["count"] == 0
        assert snapshot["domains"]["goals"]["count"] == 0
        assert snapshot["domains"]["habits"]["count"] == 0
        assert snapshot["domains"]["choices"]["count"] == 0
        assert snapshot["domains"]["events"]["count"] == 0
        assert snapshot["domains"]["principles"]["count"] == 0

    @pytest.mark.asyncio
    async def test_empty_result_metadata_correct(self, service):
        """Snapshot metadata is populated regardless of activity data."""
        result = await service.create_snapshot("user_ghost", time_period="30d")

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
        result = await service.create_snapshot("user_alice", domains=["tasks"])

        snapshot = result.value
        assert "tasks" in snapshot["domains"]
        assert "goals" not in snapshot["domains"]
        assert "habits" not in snapshot["domains"]
        assert "choices" not in snapshot["domains"]

    @pytest.mark.asyncio
    async def test_goals_habits_filter(self, service):
        """domains=['goals','habits'] → only those two keys present."""
        result = await service.create_snapshot("user_alice", domains=["goals", "habits"])

        snapshot = result.value
        assert "goals" in snapshot["domains"]
        assert "habits" in snapshot["domains"]
        assert "tasks" not in snapshot["domains"]
        assert "choices" not in snapshot["domains"]


# ============================================================================
# RECORD MAPPING TESTS
# ============================================================================


class TestSnapshotRecordMapping:
    """Records from entities_rich are correctly shaped into snapshot dicts."""

    @pytest.mark.asyncio
    async def test_task_records_mapped(self, service, mock_context_builder):
        """entities_rich tasks → tasks domain with completed count."""
        context = _make_context(
            activity_rich={
                "tasks": [
                    {
                        "entity": {
                            "uid": "t1",
                            "title": "Write tests",
                            "status": "completed",
                            "priority": "high",
                            "progress": None,
                        },
                        "graph_context": {"goal_refs": [], "ku_refs": []},
                    },
                    {
                        "entity": {
                            "uid": "t2",
                            "title": "Fix bug",
                            "status": "active",
                            "priority": "medium",
                            "progress": None,
                        },
                        "graph_context": {"goal_refs": [], "ku_refs": []},
                    },
                ],
            }
        )
        mock_context_builder.build_rich.return_value = Result.ok(context)

        result = await service.create_snapshot("user_alice")

        tasks = result.value["domains"]["tasks"]
        assert tasks["count"] == 2
        assert tasks["completed"] == 1
        assert tasks["items"][0]["title"] == "Write tests"
        assert tasks["items"][1]["title"] == "Fix bug"

    @pytest.mark.asyncio
    async def test_choice_principles_mapped(self, service, mock_context_builder):
        """principle_refs in graph_context → choices items principles field."""
        context = _make_context(
            activity_rich={
                "choices": [
                    {
                        "entity": {"uid": "c1", "title": "Chose to rest", "status": "active"},
                        "graph_context": {
                            "principle_refs": [
                                {"uid": "p1", "title": "Recovery"},
                                {"uid": "p2", "title": "Balance"},
                            ]
                        },
                    }
                ],
            }
        )
        mock_context_builder.build_rich.return_value = Result.ok(context)

        result = await service.create_snapshot("user_alice")

        choices = result.value["domains"]["choices"]
        assert choices["count"] == 1
        assert choices["items"][0]["principles"] == ["Recovery", "Balance"]

    @pytest.mark.asyncio
    async def test_event_is_milestone_mapped(self, service, mock_context_builder):
        """is_milestone comes from graph_context, not entity."""
        context = _make_context(
            activity_rich={
                "events": [
                    {
                        "entity": {
                            "uid": "e1",
                            "title": "Workshop",
                            "status": "completed",
                            "event_type": "workshop",
                        },
                        "graph_context": {"is_milestone": True},
                    }
                ],
            }
        )
        mock_context_builder.build_rich.return_value = Result.ok(context)

        result = await service.create_snapshot("user_alice")

        events = result.value["domains"]["events"]
        assert events["count"] == 1
        assert events["items"][0]["is_milestone"] is True


# ============================================================================
# ERROR PROPAGATION
# ============================================================================


class TestSnapshotErrorPropagation:
    """build_rich errors propagate as Result failures."""

    @pytest.mark.asyncio
    async def test_context_builder_error_propagates(self, service, mock_context_builder):
        """When build_rich fails, create_snapshot returns the error."""
        from core.utils.result_simplified import Errors

        mock_context_builder.build_rich.return_value = Result.fail(
            Errors.database("execute", "Connection refused")
        )

        result = await service.create_snapshot("user_alice")

        assert result.is_error


# ============================================================================
# PERSIST TESTS
# ============================================================================


class TestPersist:
    """persist() delegates to backend.create()."""

    @pytest.mark.asyncio
    async def test_persist_calls_backend_create(self, service, mock_backend):
        """persist() calls backend.create() with the given report."""
        from core.models.enums.entity_enums import ProcessorType
        from core.models.feedback.activity_report import ActivityReport

        mock_backend.create.return_value = Result.ok(MagicMock())
        report = ActivityReport.create(
            user_uid="user_alice",
            subject_uid="user_alice",
            content="Test content",
            processor_type=ProcessorType.AUTOMATIC,
            period_start=datetime.now(),
            period_end=datetime.now(),
            time_period="7d",
        )

        await service.persist(report)

        assert mock_backend.create.call_count == 1
        assert mock_backend.create.call_args[0][0] is report
