"""
Analytics Service - Facade Pattern (4-Service Architecture)
============================================================

**ARCHITECTURAL PATTERN: Meta-Service (Statistical Aggregator)**
----------------------------------------------------------------
Analytics is NOT a domain - it's a meta-layer service that sits ABOVE all domains.

**Unique Characteristics:**
- NOT in Domain enum (no Domain.ANALYTICS)
- NO graph entities (Analytics nodes don't exist in Neo4j)
- NO relationship service (analytics don't create edges)
- READ-ONLY aggregation (queries domains, never writes)
- Spans ALL layers (0: Curriculum, 1: Activity, 2: Pipeline, 3: Life Path)

**What Analytics Does:**
- Queries ALL domain services (tasks, habits, goals, events, finance, choices, etc.)
- Aggregates data into statistical metrics (completion rates, totals, averages)
- Generates cross-domain synthesis (Life Analytics)
- Tracks life path alignment (Layer 3 meta-metric)
- Optionally stores markdown analytics (file-based, NOT in graph)

**What Analytics Does NOT Do:**
- Create graph entities
- Modify domain data
- Create relationships
- Store in Neo4j
- Provide AI recommendations (metrics only)

**See:** /docs/architecture/REPORTS_ARCHITECTURE.md for complete documentation

---

Generates purely statistical analytics across ALL layers.

Version: 3.1.0 - Cross-Layer Metrics (October 24, 2025)
- v3.1.0: Extended AnalyticsMetricsService with Layer 0 and Layer 2 metrics (Phase 2)
- v3.0.0: Added AnalyticsLifePathService for Life Path alignment tracking (Phase 1)
- v2.0.0: Facade pattern with AnalyticsMetricsService + AnalyticsAggregationService
- v1.0.0: Monolithic implementation

NEW in v3.1.0: Cross-Layer Metrics (Phase 2 Complete)
- Knowledge substance metrics (Layer 0: theoretical, applied, practiced, embodied)
- Curriculum progress tracking (Layer 0: learning paths, steps, mastery)
- Journal reflection patterns (Layer 2: themes, frequency, metacognition)
- Complete metrics coverage across ALL 4 layers

Architecture:
AnalyticsService (Facade, ~530 lines) - this file
├── AnalyticsMetricsService (~863 lines) - ALL layers: Layer 0, Layer 1, Layer 2
├── AnalyticsAggregationService (~570 lines) - Cross-domain synthesis
└── AnalyticsLifePathService (~500 lines) - Life Path alignment tracking

This facade:
1. Orchestrates analytics generation for ALL layers (0, 1, 2, 3)
2. Enables cross-domain Life Analytics (Layer 1 synthesis)
3. Enables Life Path alignment tracking (cross-layer synthesis)
4. Handles markdown rendering and file storage
5. Maintains backward compatibility

SKUEL's approach: Listen and respond. User asks for analytics, system provides data.
Philosophy: "Everything flows toward the life path"
"""

from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from core.models.analytics import AnalyticsSummary, AnalyticsSummaryDTO, dto_to_summary
from core.models.enums import AnalyticsDomain
from core.services.analytics import (
    AnalyticsAggregationService,
    AnalyticsLifePathService,
    AnalyticsMetricsService,
)
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger(__name__)


class AnalyticsService:
    """
    Analytics service facade with specialized sub-services.

    This facade:
    1. Delegates to AnalyticsMetricsService for domain-specific statistics
    2. Delegates to AnalyticsAggregationService for cross-domain Life Analytics
    3. Delegates to AnalyticsLifePathService for Life Path alignment tracking (NEW!)
    4. Orchestrates analytics generation, rendering, and storage
    5. Maintains backward compatibility with existing code

    NEW in v3.0.0: Life Path Alignment (Layer 3 Cross-Layer Metric!)
    - calculate_life_path_alignment()
    - track_alignment_trends()
    - identify_knowledge_gaps()
    - analyze_domain_contributions()

    Cross-Domain Life Analytics (Layer 1 Synthesis):
    - aggregate_weekly_life_summary()
    - aggregate_monthly_life_review()
    - aggregate_quarterly_progress()
    - aggregate_yearly_review()
    - detect_cross_domain_patterns()


    Source Tag: "analytics_explicit"
    - Format: "analytics_explicit" for user-created relationships
    - Format: "analytics_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from reports metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(
        self,
        tasks_service=None,
        habits_service=None,
        goals_service=None,
        events_service=None,
        finance_service=None,
        choices_service=None,
        principle_service=None,
        content_enrichment=None,
        user_service=None,
        ku_service=None,
        lp_service=None,
        report_dir: Path | None = None,
        event_bus=None,
    ) -> None:
        """
        Initialize analytics facade with all domain and curriculum services.

        Args:
            tasks_service: TasksService facade (Layer 1)
            habits_service: HabitsService facade (Layer 1)
            goals_service: GoalsService facade (Layer 1)
            events_service: EventsService facade (Layer 1)
            finance_service: FinanceService facade (Layer 1)
            choices_service: ChoicesService facade (Layer 1)
            principle_service: PrincipleAlignmentService facade (Layer 1)
            content_enrichment: ContentEnrichmentService (Layer 2) - for Phase 2
            user_service: UserService for getting UserContext (Layer 3 - for Life Path)
            ku_service: KuService for knowledge substance scores (Layer 0 - for Phase 2)
            lp_service: LpService for Learning Path details (Layer 0 - for Phase 2)
            report_dir: Directory for storing generated analytics
            event_bus: Event bus for automatic analytics generation (Phase 4)
        """
        self.event_bus = event_bus
        self.user_service = user_service
        # Initialize sub-services
        self.metrics = AnalyticsMetricsService(
            # Layer 1: Activity domains
            tasks_service=tasks_service,
            habits_service=habits_service,
            goals_service=goals_service,
            events_service=events_service,
            finance_service=finance_service,
            choices_service=choices_service,
            principle_service=principle_service,
            # Layer 2: Pipeline services (Phase 2)
            content_enrichment=content_enrichment,
            # Layer 0: Curriculum services (Phase 2)
            ku_service=ku_service,
            lp_service=lp_service,
        )

        self.aggregation = AnalyticsAggregationService(metrics_service=self.metrics)

        # NEW: Life Path alignment tracking (Layer 3 cross-layer metric!)
        self.life_path = AnalyticsLifePathService(
            user_service=user_service, ku_service=ku_service, lp_service=lp_service
        )

        # Analytics storage
        self.report_dir = report_dir or Path("/home/mike/skuel/app/data/reports")
        self.report_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logger
        logger.info(
            "AnalyticsService facade initialized (v3.1.0): "
            "metrics (ALL layers), aggregation (cross-domain), life_path (alignment)"
        )

    # ========================================================================
    # EVENT HANDLERS (Phase 4: Event-Driven Report Generation)
    # ========================================================================

    async def handle_goal_achieved(self, event: Any) -> None:
        """
        Generate achievement report when a goal is completed.

        Event-driven handler that triggers automatic report generation
        for goal completion milestones.

        Args:
            event: GoalAchieved event containing goal completion details

        Phase 4 Integration:
        - Subscribes to: GoalAchieved
        - Generates: Goal achievement summary report

        Phase 5 Enhancement:
        - Actually generates markdown report file
        - Stores in /data/reports/goals/
        """
        try:
            self.logger.info(
                f"Goal achieved: {event.goal_uid} by user {event.user_uid} "
                f"(occurred: {event.occurred_at})"
            )

            # Generate goal achievement report for the past month
            period_end = date.today()
            period_start = period_end - timedelta(days=30)

            # Generate and save report file
            result = await self.generate_report(
                user_uid=event.user_uid,
                analytics_domain=AnalyticsDomain.GOALS,
                period_start=period_start,
                period_end=period_end,
            )

            if result.is_ok:
                report = result.value
                self.logger.info(
                    f"✅ Goal achievement report generated: {report.uid} "
                    f"(saved to {self.report_dir}/goals/)"
                )
            else:
                self.logger.warning(
                    f"⚠️ Goal achievement report generation failed: {result.expect_error().message}"
                )

        except Exception as e:
            # Best-effort: Log error but don't raise
            self.logger.error(f"Error handling goal_achieved event: {e}")

    async def handle_learning_path_completed(self, event: Any) -> None:
        """
        Generate learning progress report when a path is completed.

        Event-driven handler that triggers automatic learning summary
        when users complete learning paths.

        Args:
            event: LearningPathCompleted event

        Phase 4 Integration:
        - Subscribes to: LearningPathCompleted
        - Generates: Learning progress summary

        Phase 5 Enhancement:
        - Actually generates markdown report file
        - Stores in /data/reports/learning/
        - Includes mastery metrics and duration analysis
        """
        try:
            self.logger.info(
                f"Learning path completed: {event.path_uid} by user {event.user_uid} "
                f"({event.kus_mastered} KUs mastered, mastery: {event.average_mastery_score:.1%})"
            )

            # Generate learning progress report for the past month
            period_end = date.today()
            period_start = period_end - timedelta(days=30)

            # Generate and save report file
            # NOTE: Using TASKS as placeholder until AnalyticsDomain.LEARNING is added
            result = await self.generate_report(
                user_uid=event.user_uid,
                analytics_domain=AnalyticsDomain.TASKS,
                period_start=period_start,
                period_end=period_end,
            )

            if result.is_ok:
                report = result.value
                self.logger.info(
                    f"✅ Learning progress report generated: {report.uid} "
                    f"(saved to {self.report_dir}/tasks/) - "
                    f"Path: {event.path_uid}, KUs mastered: {event.kus_mastered}, "
                    f"Ahead of schedule: {event.completed_ahead_of_schedule}"
                )
            else:
                self.logger.warning(
                    f"⚠️ Learning progress report generation failed: {result.expect_error().message}"
                )

        except Exception as e:
            # Best-effort: Log error but don't raise
            self.logger.error(f"Error handling learning_path_completed event: {e}")

    async def handle_habit_streak_milestone(self, event: Any) -> None:
        """
        Generate habit consistency report on streak milestones.

        Event-driven handler that triggers habit performance summaries
        when significant streaks are achieved.

        Args:
            event: HabitStreakMilestone event

        Phase 4 Integration:
        - Subscribes to: HabitStreakMilestone
        - Generates: Habit consistency report

        Phase 5 Enhancement:
        - Actually generates markdown report file
        - Stores in /data/reports/habits/
        - Only generates for major milestones (7, 30, 100, 365 days)
        """
        try:
            # Only generate reports for major milestones (7, 30, 100, 365 days)
            major_milestones = [7, 30, 100, 365]
            if event.streak_length not in major_milestones:
                return

            self.logger.info(
                f"Habit streak milestone: {event.habit_uid} by user {event.user_uid} "
                f"({event.streak_length} days - {event.milestone_name})"
            )

            # Generate habit consistency report for the past month
            period_end = date.today()
            period_start = period_end - timedelta(days=30)

            # Generate and save report file
            result = await self.generate_report(
                user_uid=event.user_uid,
                analytics_domain=AnalyticsDomain.HABITS,
                period_start=period_start,
                period_end=period_end,
            )

            if result.is_ok:
                report = result.value
                self.logger.info(
                    f"✅ Habit consistency report generated: {report.uid} "
                    f"(saved to {self.report_dir}/habits/) - "
                    f"Milestone: {event.streak_length} days ({event.milestone_name})"
                )
            else:
                self.logger.warning(
                    f"⚠️ Habit consistency report generation failed: {result.expect_error().message}"
                )

        except Exception as e:
            # Best-effort: Log error but don't raise
            self.logger.error(f"Error handling habit_streak_milestone event: {e}")

    # ========================================================================
    # SINGLE-DOMAIN REPORT GENERATION (Backward Compatible)
    # ========================================================================

    @with_error_handling("generate_report", error_type="system")
    async def generate_report(
        self, user_uid: str, analytics_domain: AnalyticsDomain, period_start: date, period_end: date
    ) -> Result[AnalyticsSummary]:
        """
        Generate statistical report for any domain and period.

        Args:
            user_uid: User requesting the report,
            analytics_domain: Which domain to report on,
            period_start: Start of reporting period,
            period_end: End of reporting period (inclusive)

        Returns:
            Result[AnalyticsSummary] containing statistical metrics
        """
        self.logger.info(
            f"Generating {analytics_domain.value} report for user {user_uid}, "
            f"period {period_start} to {period_end}"
        )

        # Calculate metrics based on report type (delegate to metrics service)
        metrics_result = await self._calculate_metrics(
            user_uid, analytics_domain, period_start, period_end
        )
        if metrics_result.is_error:
            return Result.fail(metrics_result.expect_error())
        metrics = metrics_result.value

        # Generate markdown content
        markdown_content = self._render_markdown(
            analytics_domain, metrics, period_start, period_end
        )

        # Build DTO
        dto = AnalyticsSummaryDTO(
            uid=UIDGenerator.generate_uid("report"),
            user_uid=user_uid,
            analytics_domain=analytics_domain,
            period_start=period_start,
            period_end=period_end,
            metrics=metrics,
            generated_at=datetime.now(),
            title=self._generate_title(analytics_domain, period_start, period_end),
            markdown_content=markdown_content,
            metadata={"source": "AnalyticsService"},
        )

        # Convert to immutable domain model
        report = dto_to_summary(dto)

        # Save to file
        await self._save_report(report)

        self.logger.info(f"✅ Report generated: {report.uid}")
        return Result.ok(report)

    # ========================================================================
    # CONVENIENCE METHODS FOR COMMON PERIODS
    # ========================================================================

    async def generate_monthly_report(
        self, user_uid: str, analytics_domain: AnalyticsDomain, year: int, month: int
    ) -> Result[AnalyticsSummary]:
        """Generate report for a specific month"""
        start_date = date(year, month, 1)
        end_date = date(year, month, monthrange(year, month)[1])
        return await self.generate_report(user_uid, analytics_domain, start_date, end_date)

    async def generate_yearly_report(
        self, user_uid: str, analytics_domain: AnalyticsDomain, year: int
    ) -> Result[AnalyticsSummary]:
        """Generate report for a full year"""
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        return await self.generate_report(user_uid, analytics_domain, start_date, end_date)

    async def generate_weekly_report(
        self, user_uid: str, analytics_domain: AnalyticsDomain, week_start: date | None = None
    ) -> Result[AnalyticsSummary]:
        """Generate report for a week (defaults to current week)"""
        if not week_start:
            today = date.today()
            week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        return await self.generate_report(user_uid, analytics_domain, week_start, week_end)

    # ========================================================================
    # NEW: CROSS-DOMAIN LIFE REPORTS ✨
    # ========================================================================

    @with_error_handling("generate_weekly_life_summary", error_type="system")
    async def generate_weekly_life_summary(
        self, user_uid: str, week_start: date | None = None
    ) -> Result[dict[str, Any]]:
        """
        Generate weekly life summary across ALL 7 domains.

        NEW: This report synthesizes data from tasks, habits, goals, events,
        finance, choices, and principles to provide a holistic view.
        """
        if not week_start:
            today = date.today()
            week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        summary = await self.aggregation.aggregate_weekly_life_summary(
            user_uid, week_start, week_end
        )
        return Result.ok(summary)

    @with_error_handling("generate_monthly_life_review", error_type="system")
    async def generate_monthly_life_review(
        self, user_uid: str, year: int, month: int
    ) -> Result[dict[str, Any]]:
        """
        Generate monthly life review across ALL 7 domains.

        NEW: Includes trends, goal progress, and monthly patterns.
        """
        start_date = date(year, month, 1)
        end_date = date(year, month, monthrange(year, month)[1])

        review = await self.aggregation.aggregate_monthly_life_review(
            user_uid, start_date, end_date
        )
        return Result.ok(review)

    @with_error_handling("generate_quarterly_progress", error_type="system")
    async def generate_quarterly_progress(
        self, user_uid: str, year: int, quarter: int
    ) -> Result[dict[str, Any]]:
        """
        Generate quarterly progress report across ALL 7 domains.

        NEW: Strategic assessment with long-term trends.
        """
        # Calculate quarter start/end
        month_start = (quarter - 1) * 3 + 1
        start_date = date(year, month_start, 1)
        end_month = month_start + 2
        end_date = date(year, end_month, monthrange(year, end_month)[1])

        progress = await self.aggregation.aggregate_quarterly_progress(
            user_uid, start_date, end_date
        )
        return Result.ok(progress)

    @with_error_handling("generate_yearly_review", error_type="system")
    async def generate_yearly_review(self, user_uid: str, year: int) -> Result[dict[str, Any]]:
        """
        Generate yearly review across ALL 7 domains.

        NEW: Annual retrospective with achievements and growth opportunities.
        """
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)

        review = await self.aggregation.aggregate_yearly_review(user_uid, start_date, end_date)
        return Result.ok(review)

    @with_error_handling("detect_cross_domain_patterns", error_type="system")
    async def detect_cross_domain_patterns(
        self, user_uid: str, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]:
        """
        Detect patterns and relationships across domains.

        NEW: Analyzes correlations like expenses vs productivity,
        choices vs principles, goals vs habits, etc.
        """
        patterns = await self.aggregation.detect_cross_domain_patterns(
            user_uid, start_date, end_date
        )
        return Result.ok(patterns)

    # ========================================================================
    # METRIC CALCULATION (Delegate to AnalyticsMetricsService)
    # ========================================================================

    async def _calculate_metrics(
        self, user_uid: str, analytics_domain: AnalyticsDomain, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]:
        """Calculate metrics based on report type (delegates to metrics service)"""
        if analytics_domain == AnalyticsDomain.TASKS:
            return await self.metrics.calculate_task_metrics(user_uid, start_date, end_date)
        elif analytics_domain == AnalyticsDomain.HABITS:
            return await self.metrics.calculate_habit_metrics(user_uid, start_date, end_date)
        elif analytics_domain == AnalyticsDomain.GOALS:
            return await self.metrics.calculate_goal_metrics(user_uid, start_date, end_date)
        elif analytics_domain == AnalyticsDomain.EVENTS:
            return await self.metrics.calculate_event_metrics(user_uid, start_date, end_date)
        elif analytics_domain == AnalyticsDomain.FINANCE:
            return await self.metrics.calculate_finance_metrics(user_uid, start_date, end_date)
        elif analytics_domain == AnalyticsDomain.CHOICES:
            return await self.metrics.calculate_choice_metrics(user_uid, start_date, end_date)
        elif analytics_domain == AnalyticsDomain.PRINCIPLES:
            return await self.metrics.calculate_principle_metrics(user_uid, start_date, end_date)
        else:
            return Result.ok({})

    # ========================================================================
    # MARKDOWN RENDERING
    # ========================================================================

    def _render_markdown(
        self,
        analytics_domain: AnalyticsDomain,
        metrics: dict[str, Any],
        start_date: date,
        end_date: date,
    ) -> str:
        """Render metrics as markdown report"""
        lines = []

        # Header
        title = self._generate_title(analytics_domain, start_date, end_date)
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"**Period**: {start_date} to {end_date}")
        lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Metrics section
        lines.append("## Metrics")
        lines.append("")

        for key, value in metrics.items():
            if isinstance(value, dict):
                lines.append(f"### {key.replace('_', ' ').title()}")
                for sub_key, sub_value in value.items():
                    lines.append(f"- **{sub_key}**: {sub_value}")
                lines.append("")
            else:
                lines.append(f"- **{key.replace('_', ' ').title()}**: {value}")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("*Generated by SKUEL Analytics Service*")

        return "\n".join(lines)

    def _generate_title(
        self, analytics_domain: AnalyticsDomain, start_date: date, end_date: date
    ) -> str:
        """Generate human-readable report title"""
        domain = analytics_domain.value.title()

        # Determine period type
        if (end_date - start_date).days == 6:
            period = f"Week of {start_date.strftime('%b %d, %Y')}"
        elif (
            start_date.day == 1 and end_date.day == monthrange(start_date.year, start_date.month)[1]
        ):
            period = start_date.strftime("%B %Y")
        elif start_date == date(start_date.year, 1, 1) and end_date == date(
            start_date.year, 12, 31
        ):
            period = str(start_date.year)
        else:
            period = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"

        return f"{domain} Report - {period}"

    # ========================================================================
    # LIFE PATH ALIGNMENT TRACKING (Layer 3 Cross-Layer Metric!)
    # ========================================================================

    async def calculate_life_path_alignment(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Calculate user's alignment with their ultimate life goal.

        This is THE most important metric in SKUEL - measures whether
        user is LIVING their life path or just learning about it.

        Delegates to AnalyticsLifePathService.

        Args:
            user_uid: User identifier

        Returns:
            Result containing comprehensive alignment analysis:
            {
                "life_path_uid": "lp:...",
                "life_path_title": "...",
                "alignment_score": 0.73,  # 0.0-1.0
                "knowledge_count": 15,
                "embodied_knowledge": 8,
                "theoretical_knowledge": 7,
                "domain_contributions": {...},
                "gaps": [...],
                "trends": {...},
                "recommendations": [...]
            }
        """
        return await self.life_path.calculate_life_path_alignment(user_uid)

    # ========================================================================
    # FILE STORAGE
    # ========================================================================

    async def _save_report(self, report: AnalyticsSummary) -> None:
        """Save report markdown to file"""
        try:
            # Create domain-specific subdirectory
            domain_dir = self.report_dir / report.analytics_domain.value
            domain_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename
            filename = f"{report.period_start.strftime('%Y%m%d')}_{report.uid}.md"
            filepath = domain_dir / filename

            # Write markdown
            filepath.write_text(report.markdown_content)
            self.logger.info(f"Report saved to {filepath}")

        except Exception as e:
            self.logger.error(f"Failed to save report: {e}")
