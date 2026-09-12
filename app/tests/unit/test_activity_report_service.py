"""
Unit Tests for ActivityReportService
======================================

Tests create_snapshot() with pre-built UserContext.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.report.activity_report_service import ActivityReportService
from core.services.user.unified_user_context import UserContext
from core.utils.result_simplified import Result


@pytest.fixture
def mock_backend():
    backend = MagicMock()
    backend.create = AsyncMock()
    backend.get_history = AsyncMock(return_value=Result.ok([]))
    backend.annotate = AsyncMock(return_value=Result.ok([]))
    backend.get_annotation = AsyncMock(return_value=Result.ok([]))
    backend.get_admin_snapshots = AsyncMock(return_value=Result.ok([]))
    backend.get_shares_granted = AsyncMock(return_value=Result.ok([]))
    backend.get_report_schedule = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def mock_event_bus():
    bus = MagicMock()
    bus.publish_async = AsyncMock()
    return bus


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
def service(mock_backend, mock_context_builder, mock_event_bus):
    return ActivityReportService(
        backend=mock_backend,
        context_builder=mock_context_builder,
        event_bus=mock_event_bus,
    )


# ============================================================================
# SINGLE ROUND-TRIP TESTS
# ============================================================================


class TestSnapshotAcceptsContext:
    """create_snapshot() accepts a pre-built UserContext (no internal build_rich)."""

    @pytest.mark.asyncio
    async def test_does_not_call_build_rich(self, service, mock_context_builder):
        """create_snapshot no longer calls context_builder.build_rich — context is pre-built."""
        mock_context_builder.build_rich.reset_mock()
        context = _make_context()

        await service.create_snapshot(context)

        assert mock_context_builder.build_rich.call_count == 0

    @pytest.mark.asyncio
    async def test_uses_context_user_uid_as_subject(self, service):
        """subject_uid is extracted from context.user_uid."""
        context = _make_context()

        result = await service.create_snapshot(context)

        assert result.value["subject_uid"] == "user_ghost"


# ============================================================================
# EMPTY RESULT TESTS
# ============================================================================


class TestSnapshotEmptyResult:
    """Empty entities_rich produces zero-count domain sections."""

    @pytest.mark.asyncio
    async def test_empty_result_all_domains_present(self, service):
        """Empty result still populates all 6 domain keys with zero counts."""
        result = await service.create_snapshot(_make_context())

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
        result = await service.create_snapshot(_make_context(), time_period="30d")

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
        result = await service.create_snapshot(_make_context(), domains=["tasks"])

        snapshot = result.value
        assert "tasks" in snapshot["domains"]
        assert "goals" not in snapshot["domains"]
        assert "habits" not in snapshot["domains"]
        assert "choices" not in snapshot["domains"]

    @pytest.mark.asyncio
    async def test_goals_habits_filter(self, service):
        """domains=['goals','habits'] → only those two keys present."""
        result = await service.create_snapshot(_make_context(), domains=["goals", "habits"])

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
    async def test_task_records_mapped(self, service):
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
                        "graph_context": {"goal_context": None, "applied_knowledge": []},
                    },
                    {
                        "entity": {
                            "uid": "t2",
                            "title": "Fix bug",
                            "status": "active",
                            "priority": "medium",
                            "progress": None,
                        },
                        "graph_context": {"goal_context": None, "applied_knowledge": []},
                    },
                ],
            }
        )

        result = await service.create_snapshot(context)

        tasks = result.value["domains"]["tasks"]
        assert tasks["count"] == 2
        assert tasks["completed"] == 1
        assert tasks["items"][0]["title"] == "Write tests"
        assert tasks["items"][1]["title"] == "Fix bug"

    @pytest.mark.asyncio
    async def test_choice_principles_mapped(self, service):
        """guiding_principles in graph_context → choices items principles field."""
        context = _make_context(
            activity_rich={
                "choices": [
                    {
                        "entity": {"uid": "c1", "title": "Chose to rest", "status": "active"},
                        "graph_context": {
                            "guiding_principles": [
                                {"uid": "p1", "title": "Recovery"},
                                {"uid": "p2", "title": "Balance"},
                            ]
                        },
                    }
                ],
            }
        )

        result = await service.create_snapshot(context)

        choices = result.value["domains"]["choices"]
        assert choices["count"] == 1
        assert choices["items"][0]["principles"] == ["Recovery", "Balance"]

    @pytest.mark.asyncio
    async def test_event_is_milestone_mapped(self, service):
        """is_milestone comes from the entity's is_milestone_event property."""
        context = _make_context(
            activity_rich={
                "events": [
                    {
                        "entity": {
                            "uid": "e1",
                            "title": "Workshop",
                            "status": "completed",
                            "event_type": "workshop",
                            "is_milestone_event": True,
                        },
                        "graph_context": {},
                    }
                ],
            }
        )

        result = await service.create_snapshot(context)

        events = result.value["domains"]["events"]
        assert events["count"] == 1
        assert events["items"][0]["is_milestone"] is True


# ============================================================================
# PERSIST TESTS
# ============================================================================


class TestPersist:
    """persist() delegates to backend.create()."""

    @pytest.mark.asyncio
    async def test_persist_calls_backend_create(self, service, mock_backend):
        """persist() calls backend.create() with the given report."""
        from core.models.enums.pipeline import ReportSource
        from core.models.report.activity_report import ActivityReport

        mock_backend.create.return_value = Result.ok(MagicMock())
        report = ActivityReport.create(
            user_uid="user_alice",
            subject_uid="user_alice",
            content="Test content",
            processor_type=ReportSource.AUTOMATIC,
            period_start=datetime.now(),
            period_end=datetime.now(),
            time_period="7d",
        )

        await service.persist(report)

        assert mock_backend.create.call_count == 1
        assert mock_backend.create.call_args[0][0] is report


# ============================================================================
# find_by_period — the period door's reusable-report verdict
# ============================================================================


def _period_report(token: str, cutoff: datetime | None):
    from core.models.enums.pipeline import ReportSource
    from core.models.report.activity_report import ActivityReport

    return ActivityReport(
        uid=f"ar_{token}",
        title=f"Report {token}",
        user_uid="user_alice",
        subject_uid="user_alice",
        processor_type=ReportSource.AUTOMATIC,
        time_period=token,
        period_start=datetime(2026, 1, 1),
        period_end=datetime(2026, 1, 31, 23, 59, 59, 999999),
        data_cutoff=cutoff,
    )


class TestFindByPeriod:
    """Reuse while the period stands; a closed period's partial report is stale."""

    @pytest.mark.asyncio
    async def test_reads_the_newest_owned_report_for_the_token(self, service, mock_backend):
        mock_backend.find_by_period = AsyncMock(return_value=Result.ok([]))

        result = await service.latest_for_period("user_alice", "user_alice", "2026-01")

        assert result.is_ok and result.value is None
        mock_backend.find_by_period.assert_awaited_once_with("user_alice", "user_alice", "2026-01")

    @pytest.mark.asyncio
    async def test_a_closed_periods_final_report_is_reused(self, service, mock_backend):
        final = _period_report("2026-01", datetime(2026, 1, 31, 23, 59, 59, 999999))
        mock_backend.find_by_period = AsyncMock(return_value=Result.ok([final.to_dto().to_dict()]))

        result = await service.find_by_period("user_alice", "user_alice", "2026-01")

        assert result.is_ok and result.value is not None
        assert result.value.uid == "ar_2026-01"

    @pytest.mark.asyncio
    async def test_a_closed_periods_partial_report_is_stale_and_absent(self, service, mock_backend):
        partial = _period_report("2026-01", datetime(2026, 1, 20, 9, 0))
        mock_backend.find_by_period = AsyncMock(
            return_value=Result.ok([partial.to_dto().to_dict()])
        )

        result = await service.find_by_period("user_alice", "user_alice", "2026-01")

        assert result.is_ok and result.value is None

    @pytest.mark.asyncio
    async def test_a_report_with_no_recorded_cutoff_is_stale_once_closed(
        self, service, mock_backend
    ):
        unknown = _period_report("2026-01", None)
        mock_backend.find_by_period = AsyncMock(
            return_value=Result.ok([unknown.to_dto().to_dict()])
        )

        result = await service.find_by_period("user_alice", "user_alice", "2026-01")

        assert result.is_ok and result.value is None

    @pytest.mark.asyncio
    async def test_an_open_periods_partial_report_is_reused(self, service, mock_backend):
        token = f"{datetime.now().year + 1}-01"  # next January: still open
        partial = _period_report(token, datetime(2026, 1, 20, 9, 0))
        mock_backend.find_by_period = AsyncMock(
            return_value=Result.ok([partial.to_dto().to_dict()])
        )

        result = await service.find_by_period("user_alice", "user_alice", token)

        assert result.is_ok and result.value is not None

    @pytest.mark.asyncio
    async def test_a_trailing_window_report_is_always_reused(self, service, mock_backend):
        weekly = _period_report("7d", None)
        mock_backend.find_by_period = AsyncMock(return_value=Result.ok([weekly.to_dto().to_dict()]))

        result = await service.find_by_period("user_alice", "user_alice", "7d")

        assert result.is_ok and result.value is not None

    @pytest.mark.asyncio
    async def test_unknown_token_is_a_validation_failure(self, service, mock_backend):
        mock_backend.find_by_period = AsyncMock(return_value=Result.ok([]))

        result = await service.find_by_period("user_alice", "user_alice", "someday")

        assert result.is_error
        mock_backend.find_by_period.assert_not_awaited()


class TestRowConversion:
    """Every owner-scoped read decodes the stored node through the DTO's parse
    layer — the temporal fields and the JSON ``metadata`` blob included."""

    @pytest.mark.asyncio
    async def test_get_for_user_decodes_the_stored_node(self, service, mock_backend):
        stored = _period_report("2026-01", datetime(2026, 1, 31, 23, 59, 59, 999999))
        mock_backend.get_for_user = AsyncMock(
            return_value=Result.ok([{"n": stored.to_dto().to_dict()}])
        )

        result = await service.get_for_user("ar_2026-01", "user_alice")

        assert result.is_ok
        assert result.value.uid == "ar_2026-01"
        assert result.value.time_period == "2026-01"
        assert result.value.data_cutoff == datetime(2026, 1, 31, 23, 59, 59, 999999)

    @pytest.mark.asyncio
    async def test_get_history_decodes_every_row(self, service, mock_backend):
        rows = [
            {"n": _period_report("2026-01", None).to_dto().to_dict()},
            {"n": _period_report("7d", None).to_dto().to_dict()},
        ]
        mock_backend.get_history = AsyncMock(return_value=Result.ok(rows))

        result = await service.get_history("user_alice")

        assert result.is_ok
        assert [r.time_period for r in result.value] == ["2026-01", "7d"]
