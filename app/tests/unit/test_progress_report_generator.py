"""
Unit Tests for ProgressReportGenerator
=====================================

Tests generation flow, content building, time period parsing,
and depth control with mocked dependencies.
"""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.constants import ReportTimePeriod
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.pipeline import ReportSource
from core.models.enums.user_entry_enums import ProgressDepth
from core.models.report.activity_report import ActivityReport
from core.services.report.progress_report_generator import ProgressReportGenerator
from core.utils.period_keys import monthly_period_key
from core.utils.report_periods import resolve_report_period
from core.utils.result_simplified import Errors, Result


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
    service.latest_for_period = AsyncMock(return_value=Result.ok(None))
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
    backend.count_habit_completions = AsyncMock(return_value=Result.ok([]))
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
    async def test_generate_unknown_period_is_a_validation_failure(self, generator):
        """No default window: a token the vocabulary does not name is refused
        before any read — the same verdict the context builder gives."""
        result = await generator.generate(user_uid="user_alice", time_period="unknown")

        assert result.is_error
        assert result.expect_error().category.value == "validation"
        generator.activity_report_service.persist.assert_not_called()
        generator.context_builder.build_rich.assert_not_called()


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
            resolve_report_period("7d", datetime.now()),
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
            resolve_report_period("7d", datetime.now()),
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
            resolve_report_period("7d", datetime.now()),
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
            resolve_report_period("7d", datetime.now()),
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
                        {
                            "uid": "t1",
                            "title": "Write the ADR",
                            "status": "completed",
                            "completion_date": date(2026, 9, 3),
                        },
                        {
                            "goal_context": {"uid": "g1", "title": "Ship v1", "progress": 0.4},
                            "applied_knowledge": [{"uid": "ku1", "title": "Cypher basics"}],
                        },
                    ),
                    _row(
                        {
                            "uid": "t2",
                            "title": "Unlinked task",
                            "status": "completed",
                            "completion_date": "2026-09-08",
                        },
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

    def test_habits_completed_counts_habits_with_a_completion_row_in_period(self, generator):
        """The counter reads persisted HabitCompletion rows (per-habit counts
        from the backend), never ``last_completed`` — a stamp every later
        completion overwrites, which would count zero for a habit done in this
        month and the next."""
        completions = generator._completions_from_context(
            _rich_context(
                {
                    "habits": [
                        _row({"uid": "h1", "title": "Done twice", "status": "active"}),
                        _row({"uid": "h2", "title": "Done once", "status": "active"}),
                        _row(
                            {
                                "uid": "h3",
                                "title": "Stamped, no row",
                                "status": "active",
                                "last_completed": datetime(2026, 9, 5, 7, 0, 0),
                            }
                        ),
                        _row({"uid": "h4", "title": "Retired habit", "status": "completed"}),
                    ]
                }
            ),
            None,
            window_start=self.WINDOW_START,
            window_end=self.WINDOW_END,
            habit_completions={"h1": 2, "h2": 1, "h9": 3},
        )
        # Habit-level, not row-level: two habits, not three completions — and a
        # count for a habit outside the context's rows adds nothing.
        assert completions["habits_completed"] == 2

    def test_habits_completed_is_zero_without_completion_rows(self, generator):
        completions = self._map(
            generator,
            {
                "habits": [
                    _row(
                        {
                            "uid": "h1",
                            "title": "Stamp only",
                            "status": "active",
                            "last_completed": datetime(2026, 9, 5, 7, 0, 0),
                        }
                    )
                ]
            },
        )
        assert completions["habits_completed"] == 0

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
                    _row(
                        {
                            "uid": "e1",
                            "title": "Held",
                            "event_date": date(2026, 9, 5),
                            "status": "completed",
                        }
                    ),
                    _row(
                        {
                            "uid": "e2",
                            "title": "Held (string date)",
                            "event_date": "2026-09-10",
                            "status": "completed",
                        }
                    ),
                    _row({"uid": "e3", "title": "Next month", "event_date": date(2026, 10, 2)}),
                    _row(
                        {"uid": "e4", "title": "Before the window", "event_date": date(2026, 8, 30)}
                    ),
                    _row({"uid": "e5", "title": "Undated"}),
                ]
            },
        )
        assert completions["events_attended"] == 2
        assert [e["uid"] for e in completions["events_details"]] == ["e1", "e2", "e5"]

    def test_habit_completion_counts_come_from_the_period_bounded_backend_read(self, generator):
        """The window is applied by the backend read, not by the mapper: the
        generator asks for [start, cutoff] and counts what comes back."""
        completions = generator._completions_from_context(
            _rich_context({"habits": [_row({"uid": "h6", "title": "Any", "status": "active"})]}),
            None,
            window_start=self.WINDOW_START,
            window_end=self.WINDOW_END,
            habit_completions={},
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

    def test_task_completed_before_the_period_does_not_count(self, generator):
        """The rich query selects completed tasks by ``updated_at``; an old
        completion edited in the period is inventory, not a period completion."""
        completions = self._map(
            generator,
            {
                "tasks": [
                    _row(
                        {
                            "uid": "t1",
                            "title": "Done in July, retagged today",
                            "status": "completed",
                            "completion_date": date(2026, 7, 14),
                        },
                        {"goal_context": {"uid": "g1", "title": "Ship v1"}},
                    ),
                    _row({"uid": "t2", "title": "Completed, no stamp", "status": "completed"}),
                    _row({"uid": "t3", "title": "Still open", "status": "active"}),
                    _row({"uid": "t4", "title": "Cancelled", "status": "cancelled"}),
                ]
            },
        )
        # Only the open task is in play; the old completions and the cancelled
        # task are outside the period's denominator — and outside the details,
        # which list exactly what was counted.
        assert completions["tasks_total"] == 1
        assert completions["tasks_completed"] == 0
        assert completions["goal_alignments"] == []
        assert [t["uid"] for t in completions["tasks_details"]] == ["t3"]

    def test_events_attended_counts_only_completed_in_window_events(self, generator):
        completions = self._map(
            generator,
            {
                "events": [
                    _row(
                        {
                            "uid": "e1",
                            "title": "Attended",
                            "event_date": date(2026, 9, 5),
                            "status": "completed",
                        }
                    ),
                    _row(
                        {
                            "uid": "e2",
                            "title": "Cancelled",
                            "event_date": date(2026, 9, 6),
                            "status": "cancelled",
                        }
                    ),
                    _row(
                        {
                            "uid": "e3",
                            "title": "Passed unmarked",
                            "event_date": date(2026, 9, 7),
                            "status": "scheduled",
                        }
                    ),
                ]
            },
        )
        assert completions["events_attended"] == 1
        assert len(completions["events_details"]) == 3


# ============================================================================
# CALENDAR PERIODS — fixed ends, data cutoffs, per-period cooldown
# ============================================================================


def _persisted(generator) -> ActivityReport:
    return generator.activity_report_service.persist.call_args[0][0]


class TestCalendarPeriods:
    """A ``2026-09`` / ``2026-W37`` token resolves to the calendar period; the
    counts run up to ``min(now, period_end)`` and the report says when it is
    partial; the cooldown is keyed per (user, period) and yields to a closed
    period's final snapshot."""

    @pytest.mark.asyncio
    async def test_month_token_builds_the_month_window_and_records_the_period(self, generator):
        result = await generator.generate(user_uid="user_alice", time_period="2026-01")

        assert result.is_ok, result.error
        report = _persisted(generator)
        assert report.period_end is not None and report.data_cutoff is not None
        _, kwargs = generator.context_builder.build_rich.call_args
        assert kwargs["window"] == "2026-01"
        assert report.time_period == "2026-01"
        assert report.period_start == datetime(2026, 1, 1)
        assert report.period_end.date() == date(2026, 1, 31)
        # January 2026 is closed: counted through its end, final, with its limits named.
        assert report.data_cutoff == report.period_end
        assert report.metadata["period_kind"] == "month"
        assert report.metadata["is_partial"] is False
        assert report.metadata["data_cutoff"] == report.metadata["end_date"]
        assert report.metadata["period_end"] == report.period_end.isoformat()
        assert len(report.metadata["limitations"]) == 2

    @pytest.mark.asyncio
    async def test_open_period_is_counted_through_now_and_marked_partial(self, generator):
        token = monthly_period_key(date.today())  # the current month: started, still open
        result = await generator.generate(user_uid="user_alice", time_period=token)

        assert result.is_ok, result.error
        report = _persisted(generator)
        assert report.period_end is not None and report.data_cutoff is not None
        assert report.data_cutoff < report.period_end
        assert report.metadata["is_partial"] is True
        # The habit-count read is bounded to the cutoff, never the period's end.
        _, kwargs = generator.report_backend.count_habit_completions.call_args
        assert kwargs["end"] == report.data_cutoff.isoformat()

    @pytest.mark.asyncio
    async def test_a_partial_report_is_not_compared_and_tells_the_llm_it_is_partial(
        self, generator
    ):
        """The elapsed slice of an open period against a full prior period would
        print declines the unequal windows caused, so a partial report carries no
        comparison; the prompt's period label says "so far" with the cutoff."""
        prior = MagicMock(uid="ar_prev", time_period="2026-08")
        prior.metadata = {"intelligence": {"domain_trends": {}}}
        generator.activity_report_service.get_history = AsyncMock(return_value=Result.ok([prior]))
        generator.chat_port = MagicMock()
        generator.chat_port.complete = AsyncMock(
            return_value=Result.ok(MagicMock(text="An LLM report"))
        )
        token = monthly_period_key(date.today())  # the current month: open

        result = await generator.generate(user_uid="user_alice", time_period=token)

        assert result.is_ok, result.error
        report = _persisted(generator)
        assert report.metadata["is_partial"] is True
        assert "comparison" not in report.metadata
        generator.activity_report_service.get_history.assert_not_awaited()
        prompt = generator.chat_port.complete.await_args.args[0][0]["content"]
        assert " so far (counted through " in prompt

    @pytest.mark.asyncio
    async def test_a_final_report_is_compared(self, generator):
        prior = MagicMock(uid="ar_dec", time_period="2025-12")
        prior.metadata = {"intelligence": {"domain_trends": {"tasks": "stable"}}}
        generator.activity_report_service.get_history = AsyncMock(return_value=Result.ok([prior]))

        result = await generator.generate(user_uid="user_alice", time_period="2026-01")

        assert result.is_ok, result.error
        assert _persisted(generator).metadata["comparison"]["previous_report_uid"] == "ar_dec"

    @pytest.mark.asyncio
    async def test_a_period_that_has_not_started_is_refused_before_any_read(self, generator):
        """A future month holds nothing yet: counting today's open work against
        an inverted window would persist misleading statistics."""
        token = f"{datetime.now().year + 1}-01"  # next January
        result = await generator.generate(user_uid="user_alice", time_period=token)

        assert result.is_error
        assert result.expect_error().category.value == "validation"
        assert "has not started" in result.expect_error().message
        generator.context_builder.build_rich.assert_not_called()
        generator.activity_report_service.persist.assert_not_called()

    @pytest.mark.asyncio
    async def test_trailing_window_carries_no_limitations_and_is_never_partial(self, generator):
        await generator.generate(user_uid="user_alice", time_period="7d")
        report = _persisted(generator)
        assert "limitations" not in report.metadata
        assert report.metadata["is_partial"] is False
        assert report.data_cutoff == report.period_end

    @pytest.mark.asyncio
    async def test_cooldown_is_keyed_per_period(self, generator):
        await generator.generate(user_uid="user_alice", time_period="2026-W03")
        _, kwargs = generator.report_backend.check_cooldown.call_args
        assert kwargs["time_period"] == "2026-W03"

    @pytest.mark.asyncio
    async def test_cooldown_refusal_names_the_period(self, generator):
        generator.report_backend.check_cooldown = AsyncMock(
            return_value=Result.ok([{"recent_count": 1}])
        )
        result = await generator.generate(user_uid="user_alice", time_period="2026-01")
        assert result.is_error
        assert "January 2026" in result.expect_error().message

    @pytest.mark.asyncio
    async def test_finalising_a_closed_periods_partial_report_bypasses_the_cooldown(
        self, generator
    ):
        """A partial generated in the period's last hour must not block the final one."""
        partial = MagicMock()
        partial.data_cutoff = datetime(2026, 1, 31, 22, 0, 0)  # before the month's end
        generator.activity_report_service.latest_for_period = AsyncMock(
            return_value=Result.ok(partial)
        )
        generator.report_backend.check_cooldown = AsyncMock(
            return_value=Result.ok([{"recent_count": 1}])
        )

        result = await generator.generate(user_uid="user_alice", time_period="2026-01")

        assert result.is_ok, result.error
        generator.report_backend.check_cooldown.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_closed_periods_final_report_keeps_the_cooldown(self, generator):
        final = MagicMock()
        final.data_cutoff = datetime(2026, 1, 31, 23, 59, 59, 999999)
        generator.activity_report_service.latest_for_period = AsyncMock(
            return_value=Result.ok(final)
        )
        generator.report_backend.check_cooldown = AsyncMock(
            return_value=Result.ok([{"recent_count": 1}])
        )

        result = await generator.generate(user_uid="user_alice", time_period="2026-01")

        assert result.is_error
        generator.report_backend.check_cooldown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_failed_habit_count_read_fails_the_report(self, generator):
        """A count that silently read as zero is the defect the read removes."""
        generator.report_backend.count_habit_completions = AsyncMock(
            return_value=Result.fail(Errors.database("count", "boom"))
        )
        result = await generator.generate(user_uid="user_alice", time_period="2026-01")
        assert result.is_error
        generator.activity_report_service.persist.assert_not_called()

    @pytest.mark.asyncio
    async def test_comparison_skips_a_superseded_same_period_report(self, generator):
        """For a calendar period the period BEFORE it is compared — the history
        read keeps only reports whose period ended by this one's start, so its
        own regenerations and a later period generated earlier never qualify."""
        prior = MagicMock(uid="ar_aug", time_period="2026-08")
        prior.metadata = {"intelligence": {"domain_trends": {"tasks": "stable"}}}
        generator.activity_report_service.get_history = AsyncMock(return_value=Result.ok([prior]))

        comparison = await generator._collect_comparison(
            "user_alice", resolve_report_period("2026-09", datetime(2026, 9, 12))
        )

        assert comparison is not None
        assert comparison["previous_report_uid"] == "ar_aug"
        assert comparison["previous_period"] == "2026-08"
        generator.activity_report_service.get_history.assert_awaited_once_with(
            subject_uid="user_alice", limit=5, ending_before=datetime(2026, 9, 1)
        )

    @pytest.mark.asyncio
    async def test_comparison_for_a_trailing_window_keeps_same_token_history(self, generator):
        prior = MagicMock(uid="ar_last_week", time_period="7d")
        prior.metadata = {"intelligence": {"domain_trends": {}}}
        generator.activity_report_service.get_history = AsyncMock(return_value=Result.ok([prior]))

        comparison = await generator._collect_comparison(
            "user_alice", resolve_report_period("7d", datetime(2026, 9, 12))
        )

        assert comparison is not None and comparison["previous_report_uid"] == "ar_last_week"
        generator.activity_report_service.get_history.assert_awaited_once_with(
            subject_uid="user_alice", limit=5, ending_before=None
        )

    def test_report_content_names_a_partial_period(self, generator):
        period = resolve_report_period("2026-09", datetime(2026, 9, 12))
        content = generator._build_report_content(
            generator._empty_completions(),
            [],
            period,
            datetime(2026, 9, 12, 10, 0),
            ProgressDepth.SUMMARY,
        )
        assert "Partial: September 2026 is still open" in content
        assert "counted through Sep 12, 2026" in content

    def test_report_content_for_a_closed_period_has_no_partial_line(self, generator):
        period = resolve_report_period("2026-08", datetime(2026, 9, 12))
        content = generator._build_report_content(
            generator._empty_completions(), [], period, period.end, ProgressDepth.SUMMARY
        )
        assert "Partial" not in content


class TestStreaksAtTheCutoff:
    """``current_streak`` is rewritten by every completion, so it is the streak
    at the cutoff only while the cutoff is now; a closed period regenerated
    later reports none, and nothing downstream reads an absent streak as zero."""

    def _habit_rows(self):
        return {
            "habits": [_row({"uid": "h1", "title": "Run", "status": "active", "current_streak": 7})]
        }

    def test_a_closed_period_carries_no_streak(self, generator):
        completions = generator._completions_from_context(
            _rich_context(self._habit_rows()),
            None,
            window_start=datetime(2026, 9, 1),
            window_end=datetime(2026, 9, 30, 23, 59, 59),
            streaks_are_current=False,
        )
        assert completions["habits_details"][0]["streak"] is None
        trends = generator._compute_domain_trends(completions)
        assert trends["habits"]["avg_streak"] is None
        # No "streaks are low" advice from an unknown average.
        assert not any(
            r["domain"] == "habits"
            for r in generator._synthesize_recommendations(trends, completions)
        )
        prompt = generator._build_llm_prompt(completions, [], "September 2026", "standard")
        assert '"streak"' not in prompt
        content = generator._build_report_content(
            completions,
            [],
            resolve_report_period("2026-09", datetime(2026, 10, 15)),
            datetime(2026, 9, 30, 23, 59, 59),
            ProgressDepth.STANDARD,
        )
        assert "streak:" not in content

    def test_a_live_cutoff_keeps_the_streak(self, generator):
        completions = generator._completions_from_context(
            _rich_context(self._habit_rows()),
            None,
            window_start=datetime(2026, 9, 1),
            window_end=datetime(2026, 9, 12),
        )
        assert completions["habits_details"][0]["streak"] == 7
        assert generator._compute_domain_trends(completions)["habits"]["avg_streak"] == 7.0

    @pytest.mark.asyncio
    async def test_generate_passes_the_cutoff_verdict(self, generator):
        with patch.object(
            generator, "_completions_from_context", wraps=generator._completions_from_context
        ) as mapper:
            await generator.generate(user_uid="user_alice", time_period="2026-01")
            assert mapper.call_args.kwargs["streaks_are_current"] is False
            await generator.generate(user_uid="user_alice", time_period="7d")
            assert mapper.call_args.kwargs["streaks_are_current"] is True


class TestPeriodEndDenominator:
    """``tasks_total`` = completed in period + open AT the period's end."""

    PERIOD = resolve_report_period("2026-09", datetime(2026, 10, 15))

    def _map(self, generator, tasks):
        return generator._completions_from_context(
            _rich_context({"tasks": tasks}),
            None,
            window_start=self.PERIOD.start,
            window_end=self.PERIOD.end,
            period_end=self.PERIOD.end,
        )

    def test_a_task_created_after_the_period_is_not_in_its_denominator(self, generator):
        completions = self._map(
            generator,
            [
                _row(
                    {
                        "uid": "t1",
                        "title": "October",
                        "status": "active",
                        "created_at": "2026-10-02T09:00:00",
                    }
                )
            ],
        )
        assert completions["tasks_total"] == 0

    def test_a_task_closed_after_the_period_was_open_at_its_end(self, generator):
        completions = self._map(
            generator,
            [
                _row(
                    {
                        "uid": "t2",
                        "title": "Done in October",
                        "status": "completed",
                        "created_at": "2026-09-03T09:00:00",
                        "completion_date": "2026-10-04",
                    }
                )
            ],
        )
        assert completions["tasks_total"] == 1
        assert completions["tasks_completed"] == 0

    def test_a_task_closed_before_the_period_is_neither(self, generator):
        completions = self._map(
            generator,
            [
                _row(
                    {
                        "uid": "t3",
                        "title": "Done in August",
                        "status": "completed",
                        "created_at": "2026-08-03T09:00:00",
                        "completion_date": "2026-08-20",
                        "updated_at": "2026-10-04T09:00:00",  # merely re-edited later
                    }
                )
            ],
        )
        assert completions["tasks_total"] == 0

    def test_a_cancelled_task_with_no_completion_date_uses_updated_at(self, generator):
        """The named false positive: terminal before the period but edited after
        it reads as open — the metadata records the limit."""
        completions = self._map(
            generator,
            [
                _row(
                    {
                        "uid": "t4",
                        "title": "Cancelled, edited later",
                        "status": "cancelled",
                        "created_at": "2026-08-03T09:00:00",
                        "updated_at": "2026-10-04T09:00:00",
                    }
                )
            ],
        )
        assert completions["tasks_total"] == 1

    def test_details_list_exactly_the_tasks_counted(self, generator):
        """A task created after the period is neither completed in it nor open at
        its end — and the details (the prompt's and the fallback's task list)
        must not name it; the rich query hands over every open task regardless."""
        completions = self._map(
            generator,
            [
                _row(
                    {
                        "uid": "after",
                        "title": "October task",
                        "status": "active",
                        "created_at": "2026-10-02T09:00:00",
                    }
                ),
                _row(
                    {
                        "uid": "done",
                        "title": "Done in September",
                        "status": "completed",
                        "created_at": "2026-09-02T09:00:00",
                        "completion_date": "2026-09-20",
                    }
                ),
                _row(
                    {
                        "uid": "open",
                        "title": "Still open",
                        "status": "active",
                        "created_at": "2026-09-05T09:00:00",
                    }
                ),
            ],
        )
        assert [t["uid"] for t in completions["tasks_details"]] == ["done", "open"]
        assert completions["tasks_total"] == 2

    def test_every_activity_detail_list_skips_entities_created_after_the_period(self, generator):
        """The rich query hands over the current inventory whatever the window;
        a goal, habit, choice or principle created after a closed period is not
        in that period's report — not in its details, not in its counts."""
        after = "2026-10-02T09:00:00"
        before = "2026-09-02T09:00:00"
        completions = generator._completions_from_context(
            _rich_context(
                {
                    "goals": [
                        _row({"uid": "g_after", "title": "October goal", "created_at": after}),
                        _row({"uid": "g_before", "title": "September goal", "created_at": before}),
                    ],
                    "habits": [
                        _row({"uid": "h_after", "title": "October habit", "created_at": after}),
                        _row({"uid": "h_before", "title": "September habit", "created_at": before}),
                    ],
                    "choices": [
                        _row({"uid": "c_after", "title": "October choice", "created_at": after}),
                        _row(
                            {"uid": "c_before", "title": "September choice", "created_at": before}
                        ),
                    ],
                    "principles": [
                        _row(
                            {
                                "uid": "p_after",
                                "title": "October principle",
                                "created_at": after,
                                "current_alignment": "drifting",
                            }
                        ),
                        _row({"uid": "p_before", "title": "Old principle", "created_at": before}),
                    ],
                }
            ),
            None,
            window_start=self.PERIOD.start,
            window_end=self.PERIOD.end,
            period_end=self.PERIOD.end,
            habit_completions={"h_after": 3},
        )
        assert [g["uid"] for g in completions["goals_details"]] == ["g_before"]
        assert [h["uid"] for h in completions["habits_details"]] == ["h_before"]
        assert [c["uid"] for c in completions["choices_details"]] == ["c_before"]
        assert [p["uid"] for p in completions["principles_details"]] == ["p_before"]
        assert completions["habits_completed"] == 0
        # Nothing downstream sees the October principle either.
        assert generator._compute_domain_trends(completions)["principles"]["needs_attention"] == 0

    def test_an_open_task_created_in_the_period_counts(self, generator):
        completions = self._map(
            generator,
            [
                _row(
                    {
                        "uid": "t5",
                        "title": "Still open",
                        "status": "active",
                        "created_at": "2026-09-20T09:00:00",
                    }
                )
            ],
        )
        assert completions["tasks_total"] == 1
