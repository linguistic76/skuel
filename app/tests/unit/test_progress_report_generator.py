"""
Unit Tests for ProgressKuGenerator
=====================================

Tests generation flow, content building, time period parsing,
and depth control with mocked dependencies.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.ku_enums import KuStatus, KuType, ProcessorType
from core.models.ku import AiReportKu
from core.services.reports.progress_report_generator import (
    TIME_PERIOD_DAYS,
    ProgressKuGenerator,
)


@pytest.fixture
def mock_driver():
    """Create a mock Neo4j driver."""
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=([], None, None))
    return driver


@pytest.fixture
def mock_backend():
    """Create a mock reports backend."""
    backend = MagicMock()
    backend.create = AsyncMock()
    return backend


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
def generator(mock_driver, mock_backend, mock_insight_store, mock_event_bus):
    """Create ProgressKuGenerator with mocked deps."""
    return ProgressKuGenerator(
        driver=mock_driver,
        ku_backend=mock_backend,
        user_service=None,
        insight_store=mock_insight_store,
        event_bus=mock_event_bus,
    )


# ============================================================================
# TIME PERIOD TESTS
# ============================================================================


class TestTimePeriodMapping:
    """Test time period string to days mapping."""

    def test_7d(self):
        assert TIME_PERIOD_DAYS["7d"] == 7

    def test_14d(self):
        assert TIME_PERIOD_DAYS["14d"] == 14

    def test_30d(self):
        assert TIME_PERIOD_DAYS["30d"] == 30

    def test_90d(self):
        assert TIME_PERIOD_DAYS["90d"] == 90


# ============================================================================
# GENERATION TESTS
# ============================================================================


class TestGenerate:
    """Test the generate() method."""

    @pytest.mark.asyncio
    async def test_generate_creates_ku(self, generator, mock_backend):
        """Test that generate creates a Ku with correct type."""
        from core.utils.result_simplified import Result

        mock_backend.create.return_value = Result.ok(MagicMock())

        result = await generator.generate(
            user_uid="user_alice",
            time_period="7d",
            depth="standard",
        )

        assert not result.is_error
        # Verify backend.create was called
        assert mock_backend.create.call_count == 1
        created_ku = mock_backend.create.call_args[0][0]
        assert isinstance(created_ku, AiReportKu)
        assert created_ku.ku_type == KuType.AI_REPORT
        assert created_ku.status == KuStatus.COMPLETED
        assert created_ku.processor_type == ProcessorType.AUTOMATIC
        assert created_ku.user_uid == "user_alice"
        assert created_ku.subject_uid == "user_alice"

    @pytest.mark.asyncio
    async def test_generate_sets_metadata(self, generator, mock_backend):
        """Test metadata includes time period and stats."""
        from core.utils.result_simplified import Result

        mock_backend.create.return_value = Result.ok(MagicMock())

        await generator.generate(
            user_uid="user_alice",
            time_period="30d",
            depth="detailed",
        )

        created_ku = mock_backend.create.call_args[0][0]
        assert created_ku.metadata["time_period"] == "30d"
        assert created_ku.metadata["depth"] == "detailed"
        assert "start_date" in created_ku.metadata
        assert "end_date" in created_ku.metadata

    @pytest.mark.asyncio
    async def test_generate_with_insights(self, generator, mock_backend, mock_insight_store):
        """Test insight relationships are created when insights exist."""
        from core.utils.result_simplified import Result

        insight = MagicMock()
        insight.uid = "insight_123"
        insight.title = "Test Insight"
        insight.impact = "high"
        mock_insight_store.get_active_insights.return_value = Result.ok([insight])
        mock_backend.create.return_value = Result.ok(MagicMock())

        await generator.generate(
            user_uid="user_alice",
            include_insights=True,
        )

        # Insight referenced in metadata
        created_ku = mock_backend.create.call_args[0][0]
        assert created_ku.metadata["insights_referenced"] == 1

    @pytest.mark.asyncio
    async def test_generate_backend_failure(self, generator, mock_backend):
        """Test generate returns error when backend fails."""
        from core.utils.result_simplified import Errors, Result

        mock_backend.create.return_value = Result.fail(Errors.database("create", "Create failed"))

        result = await generator.generate(user_uid="user_alice")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_generate_unknown_period_defaults_7d(self, generator, mock_backend):
        """Test unknown time period defaults to 7 days."""
        from core.utils.result_simplified import Result

        mock_backend.create.return_value = Result.ok(MagicMock())

        await generator.generate(
            user_uid="user_alice",
            time_period="unknown",
        )

        created_ku = mock_backend.create.call_args[0][0]
        assert created_ku.metadata["time_period"] == "unknown"


# ============================================================================
# CONTENT BUILDING TESTS
# ============================================================================


class TestBuildReportContent:
    """Test _build_report_content method."""

    def test_summary_depth_no_details(self, generator):
        """Summary depth should not include per-item details."""
        from core.models.enums.ku_enums import ProgressDepth

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
        from core.models.enums.ku_enums import ProgressDepth

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
        from core.models.enums.ku_enums import ProgressDepth

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
        from core.models.enums.ku_enums import ProgressDepth

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
