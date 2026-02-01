"""
Reports Dashboard UI - Statistical Domain Analysis
===================================================

Clean dashboard for viewing statistical reports.
Following SKUEL principles: just numbers and charts, no AI recommendations.

✅ MIGRATED TO SHARED UI COMPONENTS (October 10, 2025)
- Previously: Custom metric_card() implementation
- Now: Uses /core/ui/shared_components.py for MetricCard and QuickMetricCard
- Benefit: Consistent styling across all dashboards
"""

from datetime import date, timedelta
from typing import Any

from fasthtml.common import (
    H1,
    H2,
    H3,
    H4,
    Div,
    Form,
    Input,
    Label,
    Option,
    P,
    Select,
    Span,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
)

from core.models.shared_enums import ReportType
from core.ui.daisy_components import Button, ButtonT
from core.ui.shared_components import MetricCard, QuickMetricCard
from core.utils.logging import get_logger
from ui.layouts.navbar import create_navbar_for_request

logger = get_logger("skuel.routes.reports.ui")


# ============================================================================
# UI COMPONENT LIBRARY
# ============================================================================


class ReportsUIComponents:
    """Reusable report UI components"""

    @staticmethod
    def render_reports_dashboard(request) -> Any:
        """Main reports dashboard - select domain and period"""
        navbar = create_navbar_for_request(request, active_page="reports")

        return Div(
            navbar,
            H1("📊 Reports Dashboard", cls="text-2xl font-bold mb-6"),
            P(
                "Generate statistical reports for any domain. "
                "Pure metrics - completion rates, totals, distributions. "
                "No AI recommendations, just transparent data.",
                cls="text-base-content/60 mb-6",
            ),
            # Report generator form
            Div(
                H3("Generate Report", cls="text-lg font-semibold mb-4"),
                Form(
                    # Domain selection
                    Div(
                        Label("Domain", cls="label"),
                        Select(
                            Option("Tasks", value="tasks"),
                            Option("Habits", value="habits"),
                            Option("Goals", value="goals"),
                            Option("Events", value="events"),
                            Option("Finance", value="finance"),
                            Option("Choices", value="choices"),
                            name="report_type",
                            id="report-type-select",
                            cls="select select-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Period selection
                    Div(
                        Label("Period", cls="label"),
                        Select(
                            Option("This Week", value="week_current"),
                            Option("Last Week", value="week_last"),
                            Option("This Month", value="month_current"),
                            Option("Last Month", value="month_last"),
                            Option("This Year", value="year_current"),
                            Option("Custom Range", value="custom"),
                            name="period",
                            id="period-select",
                            cls="select select-bordered w-full",
                            **{
                                "hx-get": "/ui/reports/period-fields",
                                "hx-target": "#period-fields",
                                "hx-trigger": "change",
                            },
                        ),
                        cls="mb-4",
                    ),
                    # Dynamic period fields (for custom range)
                    Div(id="period-fields"),
                    # Submit button
                    Div(
                        Button(
                            "📈 Generate Report",
                            type="button",
                            hx_get="/ui/reports/view",
                            hx_include="[name='report_type'],[name='period'],[name='start_date'],[name='end_date']",
                            hx_target="#report-display",
                            variant=ButtonT.primary,
                        ),
                        cls="mb-4",
                    ),
                ),
                cls="card bg-base-100 shadow-sm p-6 mb-6",
            ),
            # Report display area
            Div(id="report-display", cls="mt-6"),
            cls="container mx-auto p-6",
        )

    @staticmethod
    def render_period_fields(period) -> Any:
        """Dynamic period input fields"""
        if period == "custom":
            return Div(
                Div(
                    Label("Start Date", cls="label"),
                    Input(type="date", name="start_date", cls="input input-bordered w-full"),
                    cls="mb-4",
                ),
                Div(
                    Label("End Date", cls="label"),
                    Input(type="date", name="end_date", cls="input input-bordered w-full"),
                    cls="mb-4",
                ),
            )
        return ""

    @staticmethod
    def render_report(report) -> Any:
        """Render a generated report"""
        return Div(
            # Report header
            Div(
                H2(report.title, cls="text-xl font-bold mb-2"),
                P(
                    f"{report.format_period()} • Generated {report.generated_at.strftime('%Y-%m-%d %H:%M')}",
                    cls="text-base-content/60 text-sm",
                ),
                cls="card bg-base-100 shadow-sm p-6 mb-4",
            ),
            # Metrics cards
            ReportsUIComponents.render_metrics_cards(report),
            # Markdown view toggle
            Div(
                Button(
                    "📄 View as Markdown",
                    hx_get=f"/ui/reports/{report.uid}/markdown",
                    hx_target="#markdown-view",
                    variant=ButtonT.ghost,
                    cls="mb-4",
                ),
                Div(id="markdown-view"),
            ),
            cls="mt-6",
        )

    @staticmethod
    def render_metrics_cards(report) -> Any:
        """Render metric cards based on report type"""
        metrics = report.metrics

        if report.report_type == ReportType.TASKS:
            return ReportsUIComponents.render_tasks_metrics(metrics)
        elif report.report_type == ReportType.HABITS:
            return ReportsUIComponents.render_habits_metrics(metrics)
        elif report.report_type == ReportType.GOALS:
            return ReportsUIComponents.render_goals_metrics(metrics)
        elif report.report_type == ReportType.EVENTS:
            return ReportsUIComponents.render_events_metrics(metrics)
        elif report.report_type == ReportType.FINANCE:
            return ReportsUIComponents.render_finance_metrics(metrics)
        elif report.report_type == ReportType.CHOICES:
            return ReportsUIComponents.render_choices_metrics(metrics)
        else:
            return ReportsUIComponents.render_generic_metrics(metrics)

    @staticmethod
    def render_tasks_metrics(metrics) -> Any:
        """Render task metrics using shared components"""
        return Div(
            H3("📋 Task Metrics", cls="text-lg font-semibold mb-4"),
            # Summary cards using shared QuickMetricCard
            Div(
                QuickMetricCard("Total Tasks", str(metrics.get("total_count", 0)), "primary"),
                QuickMetricCard("Completed", str(metrics.get("completed_count", 0)), "success"),
                QuickMetricCard("In Progress", str(metrics.get("in_progress_count", 0)), "accent"),
                QuickMetricCard("Pending", str(metrics.get("pending_count", 0)), "secondary"),
                cls="grid grid-cols-4 gap-4 mb-6",
            ),
            # Completion rate using shared MetricCard
            MetricCard(
                title="Completion Rate",
                value=f"{metrics.get('completion_rate', 0)}%",
                subtitle="Tasks completed in period",
                color="green",
            ),
            # Priority distribution
            (
                Div(
                    H4("Priority Distribution", cls="font-semibold mb-3"),
                    Table(
                        Thead(Tr(Th("Priority"), Th("Count"), cls="text-left")),
                        Tbody(
                            *[
                                Tr(Td(priority.title()), Td(str(count)))
                                for priority, count in metrics.get(
                                    "priority_distribution", {}
                                ).items()
                            ]
                        ),
                        cls="table table-zebra",
                    ),
                    cls="card bg-base-100 shadow-sm p-4 mb-4",
                )
                if metrics.get("priority_distribution")
                else ""
            ),
            # Overdue tasks
            (
                Div(
                    Div(
                        Span("⚠️", cls="text-2xl mr-2"),
                        Span(
                            f"{metrics.get('overdue_count', 0)} Overdue Tasks", cls="font-semibold"
                        ),
                        cls="flex items-center",
                    ),
                    cls="alert alert-warning",
                )
                if metrics.get("overdue_count", 0) > 0
                else ""
            ),
        )

    @staticmethod
    def render_habits_metrics(metrics) -> Any:
        """Render habit metrics using shared components"""
        return Div(
            H3("🎯 Habit Metrics", cls="text-lg font-semibold mb-4"),
            Div(
                QuickMetricCard("Active Habits", str(metrics.get("total_active", 0)), "primary"),
                QuickMetricCard("Consistency", f"{metrics.get('consistency_rate', 0)}%", "success"),
                cls="grid grid-cols-2 gap-4 mb-6",
            ),
            # Streaks
            (
                Div(
                    H4("Current Streaks", cls="font-semibold mb-3"),
                    *[
                        Div(
                            Span(habit_name, cls="font-medium"),
                            Span(f"{days} days", cls="text-success"),
                            cls="flex justify-between py-2",
                        )
                        for habit_name, days in metrics.get("current_streaks", {}).items()
                    ],
                    cls="card bg-base-100 shadow-sm p-4",
                )
                if metrics.get("current_streaks")
                else ""
            ),
        )

    @staticmethod
    def render_goals_metrics(metrics) -> Any:
        """Render goal metrics using shared components"""
        return Div(
            H3("🎯 Goal Metrics", cls="text-lg font-semibold mb-4"),
            Div(
                QuickMetricCard("Active Goals", str(metrics.get("total_active", 0)), "primary"),
                QuickMetricCard("On Track", str(metrics.get("on_track_count", 0)), "success"),
                QuickMetricCard("At Risk", str(metrics.get("at_risk_count", 0)), "error"),
                QuickMetricCard(
                    "Avg Progress", f"{metrics.get('avg_progress_percentage', 0)}%", "accent"
                ),
                cls="grid grid-cols-4 gap-4",
            ),
        )

    @staticmethod
    def render_events_metrics(metrics) -> Any:
        """Render event metrics using shared components"""
        return Div(
            H3("📅 Event Metrics", cls="text-lg font-semibold mb-4"),
            Div(
                QuickMetricCard("Total Events", str(metrics.get("total_count", 0)), "primary"),
                QuickMetricCard("Upcoming", str(metrics.get("upcoming_count", 0)), "accent"),
                QuickMetricCard("Completed", str(metrics.get("completed_count", 0)), "success"),
                QuickMetricCard(
                    "Hours Scheduled", str(metrics.get("total_hours_scheduled", 0)), "secondary"
                ),
                cls="grid grid-cols-4 gap-4",
            ),
        )

    @staticmethod
    def render_finance_metrics(metrics) -> Any:
        """Render finance metrics using shared components"""
        net_balance = metrics.get("net_balance", 0)
        balance_color = "success" if net_balance >= 0 else "error"

        return Div(
            H3("💰 Finance Metrics", cls="text-lg font-semibold mb-4"),
            Div(
                QuickMetricCard(
                    "Total Expenses", f"${metrics.get('total_expenses', 0):,.2f}", "error"
                ),
                QuickMetricCard(
                    "Total Income", f"${metrics.get('total_income', 0):,.2f}", "success"
                ),
                QuickMetricCard("Net Balance", f"${net_balance:,.2f}", balance_color),
                cls="grid grid-cols-3 gap-4",
            ),
        )

    @staticmethod
    def render_choices_metrics(metrics) -> Any:
        """Render choice metrics using shared components"""
        return Div(
            H3("🤔 Choice Metrics", cls="text-lg font-semibold mb-4"),
            Div(
                QuickMetricCard("Total Choices", str(metrics.get("total_choices", 0)), "primary"),
                QuickMetricCard(
                    "Reviewed", str(metrics.get("choices_reviewed_count", 0)), "success"
                ),
                cls="grid grid-cols-2 gap-4",
            ),
        )

    @staticmethod
    def render_generic_metrics(metrics) -> Any:
        """Fallback for generic metrics display"""
        return Div(
            H4("Metrics", cls="font-semibold mb-3"),
            Table(
                Tbody(
                    *[
                        Tr(Td(key.replace("_", " ").title()), Td(str(value)))
                        for key, value in metrics.items()
                        if not isinstance(value, dict)
                    ]
                ),
                cls="table table-zebra",
            ),
            cls="card bg-base-100 shadow-sm p-4",
        )

    # Note: metric_card() removed - now using QuickMetricCard from shared components

    @staticmethod
    def render_markdown_view(markdown_content) -> Any:
        """Render markdown content"""
        return Div(
            Div(markdown_content, cls="prose max-w-none"), cls="card bg-base-100 shadow-sm p-6 mt-4"
        )

    # ========================================================================
    # LIFE PATH ALIGNMENT DASHBOARD (Phase 1 - NEW)
    # ========================================================================

    @staticmethod
    def render_life_path_alignment_dashboard(alignment_data: dict[str, Any]) -> Any:
        """
        Render Life Path alignment dashboard (Phase 1).

        Shows comprehensive alignment analysis:
        - Alignment score (0.0-1.0)
        - Knowledge embodiment breakdown
        - Domain contributions
        - Gaps and recommendations
        """
        if not alignment_data or not alignment_data.get("life_path_uid"):
            return Div(
                P("No Life Path designated yet. Set your Life Path to track alignment."),
                cls="text-base-content/60 p-4",
            )

        life_path_title = alignment_data.get("life_path_title", "Unknown")
        alignment_score = alignment_data.get("alignment_score", 0.0)
        knowledge_count = alignment_data.get("knowledge_count", 0)
        embodied = alignment_data.get("embodied_knowledge", 0)
        theoretical = alignment_data.get("theoretical_knowledge", 0)
        domain_contributions = alignment_data.get("domain_contributions", {})
        gaps = alignment_data.get("gaps", [])
        recommendations = alignment_data.get("recommendations", [])

        # Alignment score color
        score_color = (
            "red" if alignment_score < 0.5 else "yellow" if alignment_score < 0.7 else "green"
        )
        score_percentage = int(alignment_score * 100)

        return Div(
            # Header
            H1(f"Life Path: {life_path_title}", cls="text-3xl font-bold mb-6"),
            # Alignment Score Card
            QuickMetricCard("Alignment Score", f"{score_percentage}%", score_color),
            # Knowledge Breakdown
            Div(
                H2("Knowledge Embodiment", cls="text-xl font-semibold mb-4"),
                Div(
                    QuickMetricCard("Total Knowledge", str(knowledge_count), "primary"),
                    QuickMetricCard("Embodied (0.8+)", str(embodied), "success"),
                    QuickMetricCard("Theoretical (<0.5)", str(theoretical), "error"),
                    cls="grid grid-cols-3 gap-4",
                ),
                cls="card bg-base-100 shadow-sm mb-6 p-6",
            ),
            # Domain Contributions
            Div(
                H2("Domain Contributions to Life Path", cls="text-xl font-semibold mb-4"),
                Div(
                    *[
                        ReportsUIComponents._render_domain_contribution_bar(domain, contribution)
                        for domain, contribution in domain_contributions.items()
                    ],
                    cls="space-y-3",
                )
                if domain_contributions
                else P("No domain activity detected."),
                cls="card bg-base-100 shadow-sm mb-6 p-6",
            ),
            # Gaps
            Div(
                H2("Knowledge Gaps", cls="text-xl font-semibold mb-4"),
                Div(
                    *[ReportsUIComponents._render_gap_item(gap) for gap in gaps[:5]],
                    cls="space-y-2",
                )
                if gaps
                else P("No gaps detected - excellent embodiment!", cls="text-success"),
                cls="card bg-base-100 shadow-sm mb-6 p-6",
            ),
            # Recommendations
            Div(
                H2("Recommendations", cls="text-xl font-semibold mb-4"),
                Div(*[P(f"• {rec}", cls="mb-2") for rec in recommendations], cls="space-y-1")
                if recommendations
                else P("Keep up the great work!", cls="text-success"),
                cls="card bg-base-100 shadow-sm p-6",
            ),
            cls="max-w-4xl mx-auto p-6",
        )

    @staticmethod
    def _render_domain_contribution_bar(domain: str, contribution: float) -> Any:
        """Render single domain contribution bar"""
        contribution_percentage = int(contribution * 100)
        bar_width = f"{contribution_percentage}%"

        return Div(
            Div(
                Span(domain.title(), cls="font-medium"),
                Span(f"{contribution_percentage}%", cls="ml-auto text-base-content/60"),
                cls="flex justify-between mb-1",
            ),
            Div(
                Div(cls="bg-primary h-2 rounded", style=f"width: {bar_width}"),
                cls="bg-base-200 h-2 rounded overflow-hidden",
            ),
        )

    @staticmethod
    def _render_gap_item(gap: dict[str, Any]) -> Any:
        """Render single knowledge gap item"""
        title = gap.get("title", "Unknown")
        substance = gap.get("substance", 0.0)

        return Div(
            Span(title, cls="font-medium"),
            Span(f"({substance:.1f} substance)", cls="ml-2 text-base-content/60 text-sm"),
            cls="p-2 bg-error/10 rounded",
        )

    # ========================================================================
    # CROSS-LAYER LIFE SUMMARY (Phase 3 - NEW)
    # ========================================================================

    @staticmethod
    def render_weekly_life_summary(summary_data: dict[str, Any]) -> Any:
        """
        Render weekly life summary across ALL 4 layers (Phase 3).

        Shows:
        - Layer 1: Activity across 7 domains
        - Layer 0: Knowledge substance
        - Layer 2: Reflection patterns
        - Cross-layer insights
        """
        if not summary_data:
            return Div(P("No data available for this period."), cls="text-base-content/60 p-4")

        period = summary_data.get("period", {})
        start_date = period.get("start", "")
        end_date = period.get("end", "")

        total_activity = summary_data.get("total_activity_score", 0.0)
        summary_text = summary_data.get("summary", "")

        layer0_knowledge = summary_data.get("layer_0_knowledge", {})
        layer2_reflection = summary_data.get("layer_2_reflection", {})
        cross_layer_insights = summary_data.get("cross_layer_insights", {})

        return Div(
            # Header
            H1("Weekly Life Summary", cls="text-3xl font-bold mb-2"),
            P(f"{start_date} to {end_date}", cls="text-base-content/60 mb-6"),
            # Overall Activity Score
            QuickMetricCard("Overall Activity", str(int(total_activity)), "primary"),
            # Summary Text
            Div(
                H2("Summary", cls="text-xl font-semibold mb-4"),
                P(summary_text, cls="text-base-content/70"),
                cls="card bg-base-100 shadow-sm mb-6 p-6",
            ),
            # Layer 0: Knowledge
            ReportsUIComponents._render_knowledge_layer_card(layer0_knowledge),
            # Layer 2: Reflection
            ReportsUIComponents._render_reflection_layer_card(layer2_reflection),
            # Cross-Layer Insights
            ReportsUIComponents._render_cross_layer_insights_card(cross_layer_insights),
            cls="max-w-4xl mx-auto p-6",
        )

    @staticmethod
    def _render_knowledge_layer_card(layer0_data: dict[str, Any]) -> Any:
        """Render Layer 0 knowledge metrics card"""
        if not layer0_data:
            return Div()

        substance_metrics = layer0_data.get("substance_metrics", {})
        curriculum_progress = layer0_data.get("curriculum_progress", {})

        avg_substance = substance_metrics.get("avg_substance_score", 0.0)
        embodied = substance_metrics.get("embodied_knowledge", 0)
        active_paths = curriculum_progress.get("active_learning_paths", 0)
        in_progress_steps = curriculum_progress.get("in_progress_learning_steps", 0)

        return Div(
            H2("Layer 0: Knowledge & Learning", cls="text-xl font-semibold mb-4"),
            Div(
                QuickMetricCard("Avg Substance", f"{int(avg_substance * 100)}%", "primary"),
                QuickMetricCard("Embodied", str(embodied), "success"),
                QuickMetricCard("Active Paths", str(active_paths), "accent"),
                QuickMetricCard("In-Progress Steps", str(in_progress_steps), "accent"),
                cls="grid grid-cols-4 gap-4",
            ),
            cls="card bg-base-100 shadow-sm mb-6 p-6",
        )

    @staticmethod
    def _render_reflection_layer_card(layer2_data: dict[str, Any]) -> Any:
        """Render Layer 2 reflection metrics card"""
        if not layer2_data:
            return Div()

        entry_count = layer2_data.get("total_entries", 0)
        reflection_frequency = layer2_data.get("reflection_frequency", 0.0)
        metacognition_score = layer2_data.get("metacognition_score", 0.0)
        top_themes = layer2_data.get("top_themes", [])

        return Div(
            H2("Layer 2: Reflection & Journals", cls="text-xl font-semibold mb-4"),
            Div(
                QuickMetricCard("Entries", str(entry_count), "primary"),
                QuickMetricCard("Frequency", f"{reflection_frequency:.1f}/day", "accent"),
                QuickMetricCard("Metacognition", f"{int(metacognition_score * 100)}%", "success"),
                cls="grid grid-cols-3 gap-4 mb-4",
            ),
            Div(
                P("Top Themes:", cls="font-medium mb-2"),
                P(", ".join(top_themes[:3]) if top_themes else "None", cls="text-base-content/60"),
            ),
            cls="card bg-base-100 shadow-sm mb-6 p-6",
        )

    @staticmethod
    def _render_cross_layer_insights_card(insights: dict[str, Any]) -> Any:
        """Render cross-layer synthesis insights card"""
        if not insights:
            return Div()

        knowledge_correlation = insights.get("knowledge_activity_correlation", {})
        journal_impact = insights.get("journal_reflection_impact", {})
        learning_doing = insights.get("learning_doing_alignment", {})

        return Div(
            H2("Cross-Layer Insights", cls="text-xl font-semibold mb-4"),
            P(
                "Synthesis across all architectural layers:",
                cls="text-sm text-base-content/60 mb-4",
            ),
            # Knowledge-Activity Correlation
            Div(
                H3("Knowledge → Activity", cls="font-semibold mb-2"),
                P(
                    knowledge_correlation.get("insight", ""),
                    cls="text-sm text-base-content/70 mb-4",
                ),
            ),
            # Journal Impact
            Div(
                H3("Reflection Impact", cls="font-semibold mb-2"),
                P(journal_impact.get("insight", ""), cls="text-sm text-base-content/70 mb-4"),
            ),
            # Learning-Doing Alignment
            Div(
                H3("Learning ↔ Doing", cls="font-semibold mb-2"),
                P(learning_doing.get("insight", ""), cls="text-sm text-base-content/70"),
            ),
            cls="card bg-secondary/10 mb-6 p-6",
        )


# ============================================================================
# TYPED QUERY PARAMETERS
# ============================================================================


from dataclasses import dataclass
from starlette.requests import Request


@dataclass
class PeriodParams:
    """Typed parameters for period selection."""

    period: str


@dataclass
class ReportViewParams:
    """Typed parameters for report viewing."""

    user_uid: str
    report_type: str
    period: str


@dataclass
class UserReportParams:
    """Typed parameters for user-specific reports."""

    user_uid: str
    start_date: str | None


def parse_period_params(request: Request) -> PeriodParams:
    """Extract period parameters from request query params."""
    return PeriodParams(
        period=request.query_params.get("period", ""),
    )


def parse_report_view_params(request: Request) -> ReportViewParams:
    """Extract report view parameters from request query params."""
    return ReportViewParams(
        user_uid=request.query_params.get("user_uid", "user.default"),
        report_type=request.query_params.get("report_type", "tasks"),
        period=request.query_params.get("period", "month_current"),
    )


def parse_user_report_params(request: Request) -> UserReportParams:
    """Extract user report parameters from request query params."""
    return UserReportParams(
        user_uid=request.query_params.get("user_uid", "user.default"),
        start_date=request.query_params.get("start_date"),
    )


# ============================================================================
# ROUTE HANDLERS
# ============================================================================


def create_reports_ui_routes(app, rt, reports_service):
    """
    Register report UI routes.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        reports_service: Reports service instance

    Returns:
        List of registered route functions
    """

    @app.get("/ui/reports")
    async def reports_dashboard(request) -> Any:
        """Reports dashboard"""
        return ReportsUIComponents.render_reports_dashboard(request)

    @app.get("/ui/reports/period-fields")
    async def get_period_fields(request) -> Any:
        """Get dynamic period input fields"""
        # Parse typed parameters
        params = parse_period_params(request)

        return ReportsUIComponents.render_period_fields(params.period)

    @app.get("/ui/reports/view")
    async def view_report(request) -> Any:
        """Generate and view a report"""
        try:
            # Parse typed parameters
            params = parse_report_view_params(request)

            # Parse report type
            report_type = ReportType(params.report_type)

            # Calculate dates based on period
            if params.period == "week_current":
                today = date.today()
                week_start = today - timedelta(days=today.weekday())
                result = await reports_service.generate_weekly_report(
                    params.user_uid, report_type, week_start
                )
            elif params.period == "month_current":
                today = date.today()
                result = await reports_service.generate_monthly_report(
                    params.user_uid, report_type, today.year, today.month
                )
            elif params.period == "year_current":
                today = date.today()
                result = await reports_service.generate_yearly_report(
                    params.user_uid, report_type, today.year
                )
            # Add more period handling...
            else:
                return Div(P("Invalid period selection", cls="text-error"))

            if result.is_error:
                return Div(P(f"Error generating report: {result.error}", cls="text-error"))

            report = result.value

            return ReportsUIComponents.render_report(report)

        except Exception as e:
            logger.error(f"Error viewing report: {e}")
            return Div(P(f"Error: {e}", cls="text-error"))

    @app.get("/ui/reports/{uid}/markdown")
    async def view_markdown(_request, _uid: str) -> Any:
        """View report as markdown"""
        # For now, just show the markdown from a stored report
        # In production, you'd fetch the report from storage
        return ReportsUIComponents.render_markdown_view("# Report markdown would go here...")

    # ========================================================================
    # LIFE PATH ALIGNMENT UI (Phase 1 - NEW)
    # ========================================================================

    @app.get("/ui/reports/life-path-alignment")
    async def life_path_alignment_ui(request) -> Any:
        """Render Life Path alignment dashboard UI"""
        # Parse typed parameters
        params = parse_user_report_params(request)

        try:
            # Get alignment data from service
            result = await reports_service.calculate_life_path_alignment(params.user_uid)

            if result.is_error:
                return Div(P(f"Error: {result.expect_error().message}", cls="text-error p-4"))

            # Render dashboard
            return ReportsUIComponents.render_life_path_alignment_dashboard(result.value)

        except Exception as e:
            logger.error(f"Error rendering Life Path alignment: {e}")
            return Div(P(f"Error: {e}", cls="text-error p-4"))

    # ========================================================================
    # CROSS-LAYER LIFE SUMMARY UI (Phase 3 - NEW)
    # ========================================================================

    @app.get("/ui/reports/weekly-life-summary")
    async def weekly_life_summary_ui(request) -> Any:
        """Render weekly life summary UI (ALL layers)"""
        # Parse typed parameters
        params = parse_user_report_params(request)

        try:
            # Parse start date if provided
            if params.start_date:
                try:
                    start_date = date.fromisoformat(params.start_date)
                except ValueError:
                    return Div(P("Invalid date format. Use YYYY-MM-DD.", cls="text-error p-4"))

                result = await reports_service.generate_weekly_life_summary(
                    params.user_uid, week_start=start_date
                )
            else:
                # Default to current week
                result = await reports_service.generate_weekly_life_summary(params.user_uid)

            if result.is_error:
                return Div(P(f"Error: {result.expect_error().message}", cls="text-error p-4"))

            # Render summary
            return ReportsUIComponents.render_weekly_life_summary(result.value)

        except Exception as e:
            logger.error(f"Error rendering weekly life summary: {e}")
            return Div(P(f"Error: {e}", cls="text-error p-4"))

    logger.info("✅ Reports UI routes registered (including Life Path + cross-layer)")


__all__ = ["ReportsUIComponents", "create_reports_ui_routes"]
