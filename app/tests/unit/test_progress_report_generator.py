"""
Unit Tests for ProgressReportGenerator
=====================================

Tests generation flow, content building, time period parsing,
and depth control with mocked dependencies.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.constants import ReportTimePeriod
from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.report.activity_report import ActivityReport
from core.services.report.progress_report_generator import ProgressReportGenerator
from core.utils.result_simplified import Result


@pytest.fixture
def mock_driver():
    """Create a mock Neo4j driver."""
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=Result.ok([]))
    return driver


@pytest.fixture
def mock_activity_report_service():
    """Create a mock ActivityReportService."""
    service = MagicMock()
    service.persist = AsyncMock(return_value=Result.ok(MagicMock()))
    return service


@pytest.fixture
def mock_insight_store():
    """Create a mock insight store."""
    from core.utils.result_simplified import Result

    store = MagicMock()
    store.get_active_insights = AsyncMock(return_value=Result.ok([]))
    return store


@pytest.fixture
def mock_event_bus():
    """Create a mock event bus."""
    bus = MagicMock()
    bus.publish = AsyncMock()
    bus.publish_async = AsyncMock()
    return bus


@pytest.fixture
def mock_context_builder():
    """Create a mock UserContextBuilder returning an empty entities_rich context."""
    mock_context = MagicMock()
    mock_context.entities_rich = {}

    builder = MagicMock()
    builder.build_rich = AsyncMock(return_value=Result.ok(mock_context))
    return builder


@pytest.fixture
def generator(
    mock_driver,
    mock_activity_report_service,
    mock_context_builder,
    mock_insight_store,
    mock_event_bus,
):
    """Create ProgressReportGenerator with mocked deps."""
    return ProgressReportGenerator(
        executor=mock_driver,
        activity_report_service=mock_activity_report_service,
        context_builder=mock_context_builder,
        insight_store=mock_insight_store,
        event_bus=mock_event_bus,
    )


# ============================================================================
# TIME PERIOD TESTS
# ============================================================================


class TestTimePeriodMapping:
    """Test time period string to days mapping."""

    def test_7d(self):
        assert ReportTimePeriod.DAYS["7d"] == 7

    def test_14d(self):
        assert ReportTimePeriod.DAYS["14d"] == 14

    def test_30d(self):
        assert ReportTimePeriod.DAYS["30d"] == 30

    def test_90d(self):
        assert ReportTimePeriod.DAYS["90d"] == 90


# ============================================================================
# GENERATION TESTS
# ============================================================================


class TestContextBuildingSingleRoundTrip:
    """generate() builds UserContext via a single build_rich() call."""

    @pytest.mark.asyncio
    async def test_single_build_rich_call(self, generator):
        """generate() calls build_rich exactly once."""
        generator.context_builder.build_rich.reset_mock()
        await generator.generate(user_uid="user_alice")
        assert generator.context_builder.build_rich.call_count == 1

    @pytest.mark.asyncio
    async def test_build_rich_called_with_window(self, generator):
        """build_rich is called with the correct window parameter."""
        generator.context_builder.build_rich.reset_mock()
        await generator.generate(user_uid="user_alice", time_period="14d")
        _, kwargs = generator.context_builder.build_rich.call_args
        assert kwargs.get("window") == "14d"

    @pytest.mark.asyncio
    async def test_empty_context_produces_zero_counts(self, generator):
        """Empty entities_rich produces all-zero metadata counts."""
        result = await generator.generate(user_uid="user_ghost")
        assert result.is_ok
        report = generator.activity_report_service.persist.call_args[0][0]
        assert report.metadata["tasks_completed"] == 0
        assert report.metadata["events_attended"] == 0
        assert report.metadata["choices_made"] == 0


class TestPreviousAnnotationParameter:
    """generate() skips _fetch_previous_annotation when annotation is provided."""

    @pytest.mark.asyncio
    async def test_provided_annotation_skips_db_lookup(self, generator):
        """When previous_annotation is given, build_rich called once; executor called once (cooldown only)."""
        generator.executor.execute_query.reset_mock()
        generator.context_builder.build_rich.reset_mock()

        await generator.generate(
            user_uid="user_alice",
            previous_annotation="I was overcommitting last week.",
        )

        # Activity data via context_builder — annotation lookup skipped; only cooldown check fires
        assert generator.context_builder.build_rich.call_count == 1
        assert generator.executor.execute_query.call_count == 1  # cooldown only

    @pytest.mark.asyncio
    async def test_no_annotation_fetches_from_db(self, generator):
        """When previous_annotation is None, build_rich called once + executor twice (cooldown + annotation)."""
        generator.executor.execute_query.reset_mock()
        generator.context_builder.build_rich.reset_mock()

        await generator.generate(user_uid="user_alice")

        # Activity data via context_builder + cooldown check + annotation lookup via executor
        assert generator.context_builder.build_rich.call_count == 1
        assert generator.executor.execute_query.call_count == 2  # cooldown + annotation lookup


class TestGenerate:
    """Test the generate() method."""

    @pytest.mark.asyncio
    async def test_generate_creates_ku(self, generator):
        """Test that generate creates an entity with correct type."""
        result = await generator.generate(
            user_uid="user_alice",
            time_period="7d",
            depth="standard",
        )

        assert not result.is_error
        # Verify persist was called
        assert generator.activity_report_service.persist.call_count == 1
        created_ku = generator.activity_report_service.persist.call_args[0][0]
        assert isinstance(created_ku, ActivityReport)
        assert created_ku.entity_type == EntityType.ACTIVITY_REPORT
        assert created_ku.status == EntityStatus.COMPLETED
        assert created_ku.processor_type == ProcessorType.AUTOMATIC
        assert created_ku.user_uid == "user_alice"
        assert created_ku.subject_uid == "user_alice"

    @pytest.mark.asyncio
    async def test_generate_sets_metadata(self, generator):
        """Test metadata includes time period and stats."""
        await generator.generate(
            user_uid="user_alice",
            time_period="30d",
            depth="detailed",
        )

        created_ku = generator.activity_report_service.persist.call_args[0][0]
        assert created_ku.metadata["time_period"] == "30d"
        assert created_ku.metadata["depth"] == "detailed"
        assert "start_date" in created_ku.metadata
        assert "end_date" in created_ku.metadata

    @pytest.mark.asyncio
    async def test_generate_with_insights(self, generator, mock_insight_store):
        """Test insight relationships are created when insights exist."""
        insight = MagicMock()
        insight.uid = "insight_123"
        insight.title = "Test Insight"
        insight.impact = "high"
        mock_insight_store.get_active_insights.return_value = Result.ok([insight])

        await generator.generate(
            user_uid="user_alice",
            include_insights=True,
        )

        # Insight referenced in metadata
        created_ku = generator.activity_report_service.persist.call_args[0][0]
        assert created_ku.metadata["insights_referenced"] == 1

    @pytest.mark.asyncio
    async def test_generate_persist_failure(self, generator):
        """Test generate returns error when persist fails."""
        from core.utils.result_simplified import Errors

        generator.activity_report_service.persist.return_value = Result.fail(
            Errors.database("create", "Create failed")
        )

        result = await generator.generate(user_uid="user_alice")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_generate_unknown_period_defaults_7d(self, generator):
        """Test unknown time period defaults to 7 days."""
        await generator.generate(
            user_uid="user_alice",
            time_period="unknown",
        )

        created_ku = generator.activity_report_service.persist.call_args[0][0]
        assert created_ku.metadata["time_period"] == "unknown"


# ============================================================================
# CONTENT BUILDING TESTS
# ============================================================================


class TestBuildReportContent:
    """Test _build_report_content method."""

    def test_summary_depth_no_details(self, generator):
        """Summary depth should not include per-item details."""
        from core.models.enums.submissions_enums import ProgressDepth

        completions = {
            "tasks_completed": 5,
            "tasks_total": 10,
            "tasks_details": [
                {"uid": "t1", "title": "Task 1", "status": "completed", "goals": [], "kus": []},
            ],
            "goals_progressed": 0,
            "goals_details": [],
            "habits_completed": 0,
            "habits_details": [],
            "choices_made": 0,
            "choices_details": [],
            "goal_alignments": [],
            "knowledge_applications": [],
        }

        content = generator._build_report_content(
            completions,
            [],
            datetime.now() - timedelta(days=7),
            datetime.now(),
            ProgressDepth.SUMMARY,
        )

        assert "5 / 10" in content
        # Summary should NOT have per-task lines
        assert "Task 1" not in content

    def test_standard_depth_includes_details(self, generator):
        """Standard depth should include per-item details."""
        from core.models.enums.submissions_enums import ProgressDepth

        completions = {
            "tasks_completed": 1,
            "tasks_total": 1,
            "tasks_details": [
                {
                    "uid": "t1",
                    "title": "Read Chapter 5",
                    "status": "completed",
                    "goals": [],
                    "kus": [],
                },
            ],
            "goals_progressed": 0,
            "goals_details": [],
            "habits_completed": 0,
            "habits_details": [],
            "choices_made": 0,
            "choices_details": [],
            "goal_alignments": [],
            "knowledge_applications": [],
        }

        content = generator._build_report_content(
            completions,
            [],
            datetime.now() - timedelta(days=7),
            datetime.now(),
            ProgressDepth.STANDARD,
        )

        assert "Read Chapter 5" in content

    def test_empty_report_fallback(self, generator):
        """Empty completions should produce fallback text."""
        from core.models.enums.submissions_enums import ProgressDepth

        completions = {
            "tasks_completed": 0,
            "tasks_total": 0,
            "tasks_details": [],
            "goals_progressed": 0,
            "goals_details": [],
            "habits_completed": 0,
            "habits_details": [],
            "choices_made": 0,
            "choices_details": [],
            "goal_alignments": [],
            "knowledge_applications": [],
        }

        content = generator._build_report_content(
            completions,
            [],
            datetime.now() - timedelta(days=7),
            datetime.now(),
            ProgressDepth.STANDARD,
        )

        assert "No activity recorded" in content

    def test_insights_section(self, generator):
        """Active insights should appear in report content."""
        from core.models.enums.submissions_enums import ProgressDepth

        completions = {
            "tasks_completed": 0,
            "tasks_total": 0,
            "tasks_details": [],
            "goals_progressed": 0,
            "goals_details": [],
            "habits_completed": 0,
            "habits_details": [],
            "choices_made": 0,
            "choices_details": [],
            "goal_alignments": [],
            "knowledge_applications": [],
        }

        insight = MagicMock()
        insight.title = "You complete more tasks on Mondays"
        insight.impact = "medium"

        content = generator._build_report_content(
            completions,
            [insight],
            datetime.now() - timedelta(days=7),
            datetime.now(),
            ProgressDepth.STANDARD,
        )

        assert "Active Insights" in content
        assert "You complete more tasks on Mondays" in content
