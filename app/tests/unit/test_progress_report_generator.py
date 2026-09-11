"""
Unit Tests for ProgressReportGenerator
=====================================

Tests generation flow, content building, time period parsing,
and depth control with mocked dependencies.
"""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.constants import ReportTimePeriod
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.pipeline import ReportSource
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
    service.get_history = AsyncMock(return_value=Result.ok([]))
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
    # Real contexts carry None (CORE tier) or a ZPDAssessment — never a Mock.
    # Leaving this as an auto-MagicMock would route generate() through the
    # zpd_summary path with a fake truthy assessment.
    mock_context.zpd_assessment = None

    builder = MagicMock()
    builder.build_rich = AsyncMock(return_value=Result.ok(mock_context))
    return builder


@pytest.fixture
def mock_report_backend():
    """Create a mock ActivityReportGeneratorBackend."""
    backend = MagicMock()
    backend.check_cooldown = AsyncMock(return_value=Result.ok([{"recent_count": 0}]))
    backend.get_previous_annotation = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def generator(
    mock_driver,
    mock_activity_report_service,
    mock_context_builder,
    mock_insight_store,
    mock_event_bus,
    mock_report_backend,
):
    """Create ProgressReportGenerator with mocked deps."""
    return ProgressReportGenerator(
        executor=mock_driver,
        activity_report_service=mock_activity_report_service,
        context_builder=mock_context_builder,
        insight_store=mock_insight_store,
        event_bus=mock_event_bus,
        report_backend=mock_report_backend,
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
        """When previous_annotation is given, build_rich called once; backend called once (cooldown only)."""
        generator.report_backend.check_cooldown.reset_mock()
        generator.report_backend.get_previous_annotation.reset_mock()
        generator.context_builder.build_rich.reset_mock()

        await generator.generate(
            user_uid="user_alice",
            previous_annotation="I was overcommitting last week.",
        )

        # Activity data via context_builder — annotation lookup skipped; only cooldown check fires
        assert generator.context_builder.build_rich.call_count == 1
        assert generator.report_backend.check_cooldown.call_count == 1
        assert generator.report_backend.get_previous_annotation.call_count == 0

    @pytest.mark.asyncio
    async def test_no_annotation_fetches_from_db(self, generator):
        """When previous_annotation is None, build_rich called once + backend called twice (cooldown + annotation)."""
        generator.report_backend.check_cooldown.reset_mock()
        generator.report_backend.get_previous_annotation.reset_mock()
        generator.context_builder.build_rich.reset_mock()

        await generator.generate(user_uid="user_alice")

        # Activity data via context_builder + cooldown check + annotation lookup via backend
        assert generator.context_builder.build_rich.call_count == 1
        assert generator.report_backend.check_cooldown.call_count == 1
        assert generator.report_backend.get_previous_annotation.call_count == 1


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
        assert created_ku.processor_type == ReportSource.AUTOMATIC
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
        from core.models.enums.user_entry_enums import ProgressDepth

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
        from core.models.enums.user_entry_enums import ProgressDepth

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
        from core.models.enums.user_entry_enums import ProgressDepth

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
        from core.models.enums.user_entry_enums import ProgressDepth

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


class TestExtractZpdSummary:
    """_extract_zpd_summary must read the fields ZPDAssessment actually has.

    Regression (PR 5, discovery-analytics arc): the summary previously read a
    phantom ``zpd.readiness_score`` scalar — the real field is the
    ``readiness_scores`` dict — so the baked summary always carried None and
    the report's ZPD section never rendered.
    """

    def test_summary_from_real_assessment(self, generator):
        from core.models.zpd.zpd_assessment import ZPDAction, ZPDAssessment

        assessment = ZPDAssessment(
            current_zone=["ku.a"],
            proximal_zone=["ku.b", "ku.c"],
            engaged_paths=[],
            readiness_scores={"ku.b": 1.0, "ku.c": 0.5},
            blocking_gaps=["ku.gap"],
            behavioral_readiness=0.5,
            recommended_actions=(
                ZPDAction(
                    entity_uid="ku.b",
                    entity_type="path_step",
                    action_type="learn",
                    priority=0.8,
                    rationale="ready",
                ),
            ),
        )

        summary = generator._extract_zpd_summary(assessment)

        assert summary == {
            "proximal_count": 2,
            "max_readiness": 1.0,
            "blocking_gaps_count": 1,
            "recommended_count": 1,
        }

    def test_empty_assessment_yields_zero_counts(self, generator):
        from core.models.zpd.zpd_assessment import ZPDAssessment

        assessment = ZPDAssessment(
            current_zone=[],
            proximal_zone=[],
            engaged_paths=[],
            readiness_scores={},
            blocking_gaps=[],
            behavioral_readiness=0.5,
        )

        summary = generator._extract_zpd_summary(assessment)

        assert summary["proximal_count"] == 0
        assert summary["max_readiness"] is None
        assert summary["blocking_gaps_count"] == 0
        assert summary["recommended_count"] == 0

    def test_render_zpd_section_shows_counts(self, generator):
        """The report UI renders the new summary shape (end-to-end shape check)."""
        from fasthtml.common import to_xml

        from ui.learning_loop.report import _render_zpd_section

        html = to_xml(
            _render_zpd_section(
                {
                    "proximal_count": 2,
                    "max_readiness": 0.5,
                    "blocking_gaps_count": 1,
                    "recommended_count": 3,
                }
            )
        )

        assert "Zone of Proximal Development" in html
        assert "Ready next steps: 2" in html
        assert "Top readiness: 50%" in html
        assert "Blocking gaps: 1" in html
        assert "Recommended actions: 3" in html

    def test_render_zpd_section_collapses_for_legacy_snapshot(self, generator):
        """Old baked snapshots ({'readiness_score': None, counts 0}) render nothing."""
        from fasthtml.common import to_xml

        from ui.learning_loop.report import _render_zpd_section

        html = to_xml(
            _render_zpd_section(
                {"readiness_score": None, "blocking_gaps_count": 0, "recommended_count": 0}
            )
        )

        assert "Zone of Proximal Development" not in html


# ============================================================================
# COMPLETIONS MAPPER — the key contract with the rich UserContext query
# ============================================================================


def _rich_context(entities_rich: dict) -> MagicMock:
    """A UserContext stand-in carrying rows in the query's real shape."""
    context = MagicMock()
    context.entities_rich = entities_rich
    context.zpd_assessment = None
    return context


def _row(entity: dict, graph_context: dict | None = None) -> dict:
    return {"entity": entity, "graph_context": graph_context or {}}


class TestCompletionsFromContext:
    """The mapper's row contract: rows are ``{entity: properties(n), graph_context:
    {...}}``, keys are the persisted property names and the query's graph-context
    aliases, and every headline counter is an in-period transition read off the
    entity's own stamp. Each assertion pins a non-zero value for one key."""

    WINDOW_START = datetime(2026, 9, 1, 0, 0, 0)
    WINDOW_END = datetime(2026, 9, 11, 12, 0, 0)

    def _map(self, generator, entities_rich):
        return generator._completions_from_context(
            _rich_context(entities_rich),
            None,
            window_start=self.WINDOW_START,
            window_end=self.WINDOW_END,
        )

    def test_completed_task_reports_its_goal_and_applied_knowledge(self, generator):
        completions = self._map(
            generator,
            {
                "tasks": [
                    _row(
                        {"uid": "t1", "title": "Write the ADR", "status": "completed"},
                        {
                            "goal_context": {"uid": "g1", "title": "Ship v1", "progress": 0.4},
                            "applied_knowledge": [{"uid": "ku1", "title": "Cypher basics"}],
                        },
                    ),
                    _row(
                        {"uid": "t2", "title": "Unlinked task", "status": "completed"},
                        {"goal_context": None, "applied_knowledge": []},
                    ),
                ]
            },
        )
        assert completions["tasks_completed"] == 2
        assert completions["goal_alignments"] == ["Ship v1"]
        assert completions["knowledge_applications"] == ["Cypher basics"]
        assert completions["tasks_details"][0]["goals"] == ["Ship v1"]
        assert completions["tasks_details"][0]["kus"] == ["Cypher basics"]
        assert completions["tasks_details"][1]["goals"] == []

    def test_goal_progress_reads_progress_percentage(self, generator):
        completions = self._map(
            generator,
            {
                "goals": [
                    _row(
                        {
                            "uid": "g1",
                            "title": "Ship v1",
                            "status": "active",
                            "progress_percentage": 40.0,
                        }
                    )
                ]
            },
        )
        assert completions["goals_details"][0]["progress"] == 40.0
        assert generator._compute_domain_trends(completions)["goals"]["avg_progress"] == 40.0

    def test_habit_streak_reads_current_streak(self, generator):
        completions = self._map(
            generator,
            {
                "habits": [
                    _row(
                        {"uid": "h1", "title": "Meditate", "status": "active", "current_streak": 5}
                    )
                ]
            },
        )
        assert completions["habits_details"][0]["streak"] == 5
        assert generator._compute_domain_trends(completions)["habits"]["avg_streak"] == 5.0

    def test_habit_completed_in_window_counts_by_last_completed(self, generator):
        inside = datetime(2026, 9, 5, 7, 0, 0)
        before = datetime(2026, 8, 20, 7, 0, 0)
        completions = self._map(
            generator,
            {
                "habits": [
                    _row(
                        {
                            "uid": "h1",
                            "title": "In window",
                            "status": "active",
                            "last_completed": inside,
                        }
                    ),
                    _row(
                        {
                            "uid": "h2",
                            "title": "ISO in window",
                            "status": "active",
                            "last_completed": inside.isoformat(),
                        }
                    ),
                    _row(
                        {
                            "uid": "h3",
                            "title": "Before window",
                            "status": "active",
                            "last_completed": before,
                        }
                    ),
                    _row({"uid": "h4", "title": "Retired habit", "status": "completed"}),
                    _row(
                        {
                            "uid": "h5",
                            "title": "Never done",
                            "status": "active",
                            "last_completed": None,
                        }
                    ),
                ]
            },
        )
        assert completions["habits_completed"] == 2

    def test_habit_window_test_survives_aware_timestamps(self, generator):
        aware = datetime(2026, 9, 5, 7, 0, 0, tzinfo=UTC)
        completions = generator._completions_from_context(
            _rich_context(
                {"habits": [_row({"uid": "h1", "title": "Aware", "last_completed": aware})]}
            ),
            None,
            window_start=datetime(2026, 9, 1, tzinfo=UTC),
            window_end=datetime(2026, 9, 11, tzinfo=UTC),
        )
        assert completions["habits_completed"] == 1

    def test_event_milestone_reads_is_milestone_event(self, generator):
        completions = self._map(
            generator,
            {
                "events": [
                    _row(
                        {
                            "uid": "e1",
                            "title": "Launch",
                            "event_type": "milestone",
                            "is_milestone_event": True,
                        }
                    ),
                    _row({"uid": "e2", "title": "Standup", "event_type": "meeting"}),
                ]
            },
        )
        assert [e["is_milestone"] for e in completions["events_details"]] == [True, False]
        assert generator._compute_domain_trends(completions)["events"]["milestones"] == 1

    def test_choice_principles_read_guiding_principles(self, generator):
        completions = self._map(
            generator,
            {
                "choices": [
                    _row(
                        {"uid": "c1", "title": "Decline the offer"},
                        {"guiding_principles": [{"uid": "p1", "title": "Honesty"}]},
                    )
                ]
            },
        )
        assert completions["choices_details"][0]["principles"] == ["Honesty"]
        assert generator._compute_domain_trends(completions)["choices"]["principled"] == 1

    def test_principle_alignment_reads_current_alignment_and_category(self, generator):
        completions = self._map(
            generator,
            {
                "principles": [
                    _row(
                        {
                            "uid": "p1",
                            "title": "Honesty",
                            "current_alignment": "aligned",
                            "strength": "strong",
                            "principle_category": "ethics",
                        }
                    ),
                    _row({"uid": "p2", "title": "Patience", "current_alignment": "drifting"}),
                ]
            },
        )
        assert completions["principles_details"][0]["alignment"] == "aligned"
        assert completions["principles_details"][0]["category"] == "ethics"
        trends = generator._compute_domain_trends(completions)["principles"]
        assert (trends["aligned"], trends["needs_attention"]) == (1, 1)

    def test_events_outside_the_window_are_not_attended(self, generator):
        """The rich query has no upper bound on event_date: a future event is
        selected, and must not be reported as attended."""
        completions = self._map(
            generator,
            {
                "events": [
                    _row({"uid": "e1", "title": "Held", "event_date": date(2026, 9, 5)}),
                    _row({"uid": "e2", "title": "Held (string date)", "event_date": "2026-09-10"}),
                    _row({"uid": "e3", "title": "Next month", "event_date": date(2026, 10, 2)}),
                    _row(
                        {"uid": "e4", "title": "Before the window", "event_date": date(2026, 8, 30)}
                    ),
                    _row({"uid": "e5", "title": "Undated"}),
                ]
            },
        )
        assert completions["events_attended"] == 3
        assert [e["uid"] for e in completions["events_details"]] == ["e1", "e2", "e5"]

    def test_habit_completed_after_the_window_is_not_counted(self, generator):
        completions = self._map(
            generator,
            {
                "habits": [
                    _row(
                        {
                            "uid": "h6",
                            "title": "After window",
                            "status": "active",
                            "last_completed": datetime(2026, 9, 12, 7, 0, 0),
                        }
                    )
                ]
            },
        )
        assert completions["habits_completed"] == 0

    def test_goals_progressed_counts_in_period_progress_updates(self, generator):
        completions = self._map(
            generator,
            {
                "goals": [
                    _row(
                        {
                            "uid": "g1",
                            "title": "Moved",
                            "last_progress_update": datetime(2026, 9, 3),
                        }
                    ),
                    _row(
                        {
                            "uid": "g2",
                            "title": "Stale",
                            "last_progress_update": datetime(2026, 7, 1),
                        }
                    ),
                    _row({"uid": "g3", "title": "Never moved"}),
                ]
            },
        )
        assert completions["goals_progressed"] == 1
        assert len(completions["goals_details"]) == 3
        trends = generator._compute_domain_trends(completions)["goals"]
        assert (trends["total"], trends["progressed"]) == (3, 1)

    def test_choices_made_counts_in_period_decisions(self, generator):
        completions = self._map(
            generator,
            {
                "choices": [
                    _row({"uid": "c1", "title": "Decided", "decided_at": "2026-09-04T10:00:00"}),
                    _row({"uid": "c2", "title": "Pending"}),
                    _row(
                        {"uid": "c3", "title": "Old decision", "decided_at": datetime(2026, 8, 1)}
                    ),
                ]
            },
        )
        assert completions["choices_made"] == 1
        assert len(completions["choices_details"]) == 3
        assert generator._compute_domain_trends(completions)["choices"]["decided"] == 1

    def test_principles_reviewed_counts_in_period_reviews(self, generator):
        completions = self._map(
            generator,
            {
                "principles": [
                    _row({"uid": "p1", "title": "Reviewed", "last_review_date": date(2026, 9, 6)}),
                    _row(
                        {
                            "uid": "p2",
                            "title": "Reviewed (string)",
                            "last_review_date": "2026-09-02",
                        }
                    ),
                    _row({"uid": "p3", "title": "Long ago", "last_review_date": date(2026, 1, 6)}),
                    _row({"uid": "p4", "title": "Never"}),
                ]
            },
        )
        assert completions["principles_reviewed"] == 2
        assert len(completions["principles_details"]) == 4
        assert generator._compute_domain_trends(completions)["principles"]["reviewed"] == 2
