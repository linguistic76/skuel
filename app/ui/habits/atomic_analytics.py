"""
Advanced Analytics Dashboards - Atomic Habits Insights

This module provides comprehensive analytics dashboards for understanding habit systems,
tracking progress over time, and identifying optimization opportunities.

Dashboard Categories:
1. System Comparison - Compare habit systems across multiple goals
2. Historical Trends - Track system strength, velocity, and identity progress over time
3. Habit Migration - Visualize essentiality changes and habit evolution
4. Benchmarking - Compare performance against community averages (anonymized)

All dashboards support filtering, date ranges, and export functionality.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, TypedDict

from fasthtml.common import H1, H2, H3, Div, Option, P, Span, Tbody, Td, Th, Thead, Tr

from ui.buttons import Button
from ui.cards import Card, CardBody
from ui.data import Table
from ui.forms import Input, Label, Select
from ui.habits.atomic_animations import AtomicHabitsAnimations
from ui.ui_types import BenchmarkData, HabitMigration


class HistoricalDataPoint(TypedDict):
    """Historical trend data point with date and metrics."""

    date: date
    system_strength: float
    velocity: float


@dataclass(frozen=True)
class SystemMetric:
    """Single metric data point for analytics."""

    date: date
    value: float
    label: str = ""


@dataclass(frozen=True)
class GoalSystemSnapshot:
    """Snapshot of a goal's habit system at a point in time."""

    goal_uid: str
    goal_title: str
    system_strength: float
    velocity: float
    essential_count: int
    critical_count: int
    supporting_count: int
    optional_count: int
    identity_votes: int
    date: date


class AtomicHabitsAnalytics:
    """Advanced analytics dashboards for Atomic Habits insights."""

    @staticmethod
    def render_analytics_dashboard(
        date_range: tuple[date, date] | None = None,
    ) -> Div:
        """
        Main analytics dashboard with all visualizations.

        Args:
            date_range: (start_date, end_date) tuple
        """
        if not date_range:
            end_date = date.today()
            start_date = end_date - timedelta(days=90)
            date_range = (start_date, end_date)

        return Div(
            H1("📊 Advanced Analytics", cls="text-3xl font-bold mb-6"),
            # Date range selector
            AtomicHabitsAnalytics._render_date_range_selector(date_range),
            # Quick stats summary
            AtomicHabitsAnalytics._render_analytics_summary(),
            # Dashboard sections
            Div(
                # System Comparison
                AtomicHabitsAnalytics._render_system_comparison_section(),
                # Historical Trends
                AtomicHabitsAnalytics._render_historical_trends_section(date_range),
                # Habit Migration
                AtomicHabitsAnalytics._render_habit_migration_section(),
                # Community Benchmarking
                AtomicHabitsAnalytics._render_benchmarking_section(),
                cls="space-y-8",
            ),
            cls="container mx-auto p-6",
        )

    @staticmethod
    def _render_date_range_selector(date_range: tuple[date, date]) -> Any:
        """Date range selector for analytics."""
        start_date, end_date = date_range

        return Card(
            CardBody(
                Div(
                    Label("Date Range:", cls="font-medium mr-4"),
                    Select(
                        Option("Last 7 days", value="7d"),
                        Option("Last 30 days", value="30d", selected=True),
                        Option("Last 90 days", value="90d"),
                        Option("Last 365 days", value="365d"),
                        Option("All time", value="all"),
                        full_width=False,
                        hx_get="/analytics/update",
                        hx_target="#analytics-content",
                    ),
                    Span(
                        f"{start_date.strftime('%b %d, %Y')} - {end_date.strftime('%b %d, %Y')}",
                        cls="text-sm text-muted-foreground ml-4",
                    ),
                    Button(
                        "Export Data",
                        cls="btn btn-secondary btn-sm ml-4",
                        hx_get="/analytics/export",
                    ),
                    cls="flex items-center justify-between",
                ),
            ),
            cls="mb-6",
        )

    @staticmethod
    def _render_analytics_summary() -> Div:
        """Quick stats summary cards."""
        # Mock data - would come from backend
        stats = {
            "avg_system_strength": 82.5,
            "total_identity_votes": 287,
            "habits_in_optimal_essentiality": 8,
            "total_habits": 12,
            "velocity_trend": "+12%",
            "strongest_goal": "Write First Novel (95%)",
        }

        return Div(
            Card(
                CardBody(
                    Div(
                        Span(
                            f"{stats['avg_system_strength']:.1f}%",
                            cls="text-3xl font-bold text-blue-600",
                        ),
                        P("Avg System Strength", cls="text-sm text-muted-foreground"),
                        cls="text-center",
                    ),
                ),
            ),
            Card(
                CardBody(
                    Div(
                        Span(
                            str(stats["total_identity_votes"]),
                            cls="text-3xl font-bold text-purple-600",
                        ),
                        P("Total Identity Votes", cls="text-sm text-muted-foreground"),
                        cls="text-center",
                    ),
                ),
            ),
            Card(
                CardBody(
                    Div(
                        Span(
                            f"{stats['habits_in_optimal_essentiality']}/{stats['total_habits']}",
                            cls="text-3xl font-bold text-green-600",
                        ),
                        P("Optimal Essentiality", cls="text-sm text-muted-foreground"),
                        cls="text-center",
                    ),
                ),
            ),
            Card(
                CardBody(
                    Div(
                        Span(stats["velocity_trend"], cls="text-3xl font-bold text-orange-600"),
                        P("Velocity Trend", cls="text-sm text-muted-foreground"),
                        cls="text-center",
                    ),
                ),
            ),
            cls="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8",
        )

    @staticmethod
    def _render_system_comparison_section() -> Any:
        """Compare habit systems across all active goals."""
        # Mock goal snapshots
        mock_goals = [
            GoalSystemSnapshot(
                goal_uid="goal_1",
                goal_title="Write First Novel",
                system_strength=0.95,
                velocity=130.5,
                essential_count=3,
                critical_count=2,
                supporting_count=1,
                optional_count=0,
                identity_votes=45,
                date=date.today(),
            ),
            GoalSystemSnapshot(
                goal_uid="goal_2",
                goal_title="Master Python",
                system_strength=0.78,
                velocity=95.0,
                essential_count=2,
                critical_count=3,
                supporting_count=2,
                optional_count=1,
                identity_votes=28,
                date=date.today(),
            ),
            GoalSystemSnapshot(
                goal_uid="goal_3",
                goal_title="Get Fit",
                system_strength=0.62,
                velocity=85.5,
                essential_count=2,
                critical_count=1,
                supporting_count=2,
                optional_count=2,
                identity_votes=15,
                date=date.today(),
            ),
        ]

        # Build comparison table
        def get_system_strength(goal) -> Any:
            return goal.system_strength

        comparison_rows = []
        for goal in sorted(mock_goals, key=get_system_strength, reverse=True):
            strength_color = (
                "text-green-600"
                if goal.system_strength >= 0.8
                else "text-blue-600"
                if goal.system_strength >= 0.6
                else "text-yellow-600"
                if goal.system_strength >= 0.4
                else "text-red-600"
            )

            comparison_rows.append(
                Tr(
                    Td(goal.goal_title, cls="font-medium"),
                    Td(f"{goal.system_strength * 100:.1f}%", cls=f"font-bold {strength_color}"),
                    Td(f"{goal.velocity:.1f}", cls="text-muted-foreground"),
                    Td(
                        f"{goal.essential_count}/{goal.critical_count}/{goal.supporting_count}/{goal.optional_count}",
                        cls="text-sm text-muted-foreground",
                    ),
                    Td(str(goal.identity_votes), cls="text-purple-600"),
                    Td(
                        Button(
                            "Details",
                            cls="btn btn-sm btn-secondary",
                            hx_get=f"/goals/{goal.goal_uid}/system-health",
                            hx_target="#modal",
                        )
                    ),
                )
            )

        return Card(
            CardBody(
                H2("🔍 System Comparison", cls="text-2xl font-bold mb-4"),
                P(
                    "Compare habit systems across all your active goals",
                    cls="text-muted-foreground mb-6",
                ),
                Table(
                    Thead(
                        Tr(
                            Th("Goal", cls="text-left"),
                            Th("System Strength", cls="text-left"),
                            Th("Velocity", cls="text-left"),
                            Th("E/C/S/O Habits", cls="text-left"),
                            Th("Identity Votes", cls="text-left"),
                            Th("Actions", cls="text-left"),
                        )
                    ),
                    Tbody(*comparison_rows),
                    cls="table w-full",
                ),
                # Insights
                Div(
                    H3("💡 Insights", cls="font-semibold mb-2 mt-6"),
                    Div(
                        P(
                            '✅ "Write First Novel" has excellent system strength (95%) - well-designed and executed',
                            cls="text-sm text-green-700 mb-2",
                        ),
                        P(
                            '⚠️ "Get Fit" could benefit from more essential habits - currently only 2',
                            cls="text-sm text-yellow-700 mb-2",
                        ),
                        P(
                            '🎯 Consider migrating 1 supporting habit in "Master Python" to critical tier',
                            cls="text-sm text-blue-700",
                        ),
                        cls="p-4 bg-muted rounded-lg",
                    ),
                ),
            ),
            cls="mb-8",
        )

    @staticmethod
    def _render_historical_trends_section(date_range: tuple[date, date]) -> Any:
        """Historical trend visualization for system metrics."""
        start_date, end_date = date_range

        # Mock historical data (would come from backend)
        mock_data: list[HistoricalDataPoint] = [
            {
                "date": end_date - timedelta(days=i),
                "system_strength": 75 + i * 0.5,
                "velocity": 85 + i * 1.2,
            }
            for i in range(30, -1, -3)
        ]

        # Generate trend chart (using animation component)
        velocities = [d["velocity"] for d in mock_data]
        labels = [d["date"].strftime("%b %d") for d in mock_data]

        return Card(
            CardBody(
                H2("📈 Historical Trends", cls="text-2xl font-bold mb-4"),
                P(
                    f"System performance from {start_date.strftime('%b %d')} to {end_date.strftime('%b %d')}",
                    cls="text-muted-foreground mb-6",
                ),
                # System Strength Trend
                Div(
                    H3("System Strength Over Time", cls="text-lg font-semibold mb-3"),
                    AtomicHabitsAnimations.render_velocity_chart_animated(
                        velocities=[d["system_strength"] for d in mock_data], labels=labels
                    ),
                    cls="mb-8",
                ),
                # Velocity Trend
                Div(
                    H3("Habit Velocity Over Time", cls="text-lg font-semibold mb-3"),
                    AtomicHabitsAnimations.render_velocity_chart_animated(
                        velocities=velocities, labels=labels
                    ),
                    cls="mb-6",
                ),
                # Trend analysis
                Div(
                    H3("📊 Trend Analysis", cls="font-semibold mb-2"),
                    Div(
                        P(
                            "📈 System strength improved by 18.5% over the last 30 days",
                            cls="text-sm text-green-700 mb-2",
                        ),
                        P(
                            "🚀 Velocity increased by 25.3% - excellent momentum",
                            cls="text-sm text-green-700 mb-2",
                        ),
                        P(
                            "✨ Identity votes accelerating: +45 in last 2 weeks vs +28 prior 2 weeks",
                            cls="text-sm text-blue-700",
                        ),
                        cls="p-4 bg-blue-50 rounded-lg",
                    ),
                ),
            ),
            cls="mb-8",
        )

    @staticmethod
    def _render_habit_migration_section() -> Any:
        """Visualize habit essentiality changes over time."""
        # Mock migration data - using frozen dataclass for type safety
        migrations: list[HabitMigration] = [
            HabitMigration(
                habit="Daily Writing (500 words)",
                from_level="critical",
                to_level="essential",
                migration_date=date.today() - timedelta(days=7),
                reason="Consistently completed for 30 days",
            ),
            HabitMigration(
                habit="Code Review Study",
                from_level="supporting",
                to_level="critical",
                migration_date=date.today() - timedelta(days=14),
                reason='High impact on "Master Python" goal',
            ),
            HabitMigration(
                habit="Evening Stretching",
                from_level="optional",
                to_level="supporting",
                migration_date=date.today() - timedelta(days=21),
                reason="Improved consistency (80%+)",
            ),
        ]

        migration_rows = []
        for migration in migrations:
            # Color code essentiality levels
            from_color = AtomicHabitsAnalytics._get_essentiality_color(migration.from_level)
            to_color = AtomicHabitsAnalytics._get_essentiality_color(migration.to_level)

            migration_rows.append(
                Tr(
                    Td(migration.habit, cls="font-medium"),
                    Td(
                        Span(
                            migration.from_level.upper(),
                            cls=f"px-2 py-1 rounded text-xs font-bold {from_color}",
                        ),
                        cls="text-center",
                    ),
                    Td("→", cls="text-2xl text-muted-foreground text-center"),
                    Td(
                        Span(
                            migration.to_level.upper(),
                            cls=f"px-2 py-1 rounded text-xs font-bold {to_color}",
                        ),
                        cls="text-center",
                    ),
                    Td(
                        migration.migration_date.strftime("%b %d, %Y"),
                        cls="text-sm text-muted-foreground",
                    ),
                    Td(migration.reason, cls="text-sm italic text-muted-foreground"),
                )
            )

        return Card(
            CardBody(
                H2("🔄 Habit Migration Tracking", cls="text-2xl font-bold mb-4"),
                P(
                    "See how your habits evolve in importance over time",
                    cls="text-muted-foreground mb-6",
                ),
                Table(
                    Thead(
                        Tr(
                            Th("Habit", cls="text-left"),
                            Th("From", cls="text-center"),
                            Th("", cls="text-center"),
                            Th("To", cls="text-center"),
                            Th("Date", cls="text-left"),
                            Th("Reason", cls="text-left"),
                        )
                    ),
                    Tbody(*migration_rows),
                    cls="table w-full",
                ),
                # Migration insights
                Div(
                    H3("🎯 Migration Insights", cls="font-semibold mb-2 mt-6"),
                    Div(
                        P(
                            "✨ 3 habits promoted to higher tiers in the last 30 days",
                            cls="text-sm text-green-700 mb-2",
                        ),
                        P(
                            "📈 Average time from optional → supporting: 14 days",
                            cls="text-sm text-blue-700 mb-2",
                        ),
                        P(
                            '🏆 Fastest promotion: "Daily Writing" (critical → essential in 30 days)',
                            cls="text-sm text-purple-700",
                        ),
                        cls="p-4 bg-purple-50 rounded-lg",
                    ),
                ),
            ),
            cls="mb-8",
        )

    @staticmethod
    def _render_benchmarking_section() -> Any:
        """Compare user performance against anonymized community averages."""
        # Mock benchmarking data - using frozen dataclass for type safety
        benchmarks: list[BenchmarkData] = [
            BenchmarkData(metric="Avg System Strength", user=82.5, community=68.2, percentile=78),
            BenchmarkData(metric="Habits per Goal", user=4.3, community=3.1, percentile=85),
            BenchmarkData(metric="Identity Votes/Month", user=95.0, community=42.5, percentile=92),
            BenchmarkData(metric="Essential Habit %", user=35.0, community=22.0, percentile=71),
            BenchmarkData(metric="Velocity", user=118.0, community=75.0, percentile=88),
        ]

        benchmark_rows = []
        for benchmark in benchmarks:
            user_val = benchmark.user
            community_val = benchmark.community
            percentile = benchmark.percentile

            # Determine if user is above/below community
            comparison = "text-green-600" if user_val > community_val else "text-red-600"
            comparison_icon = "📈" if user_val > community_val else "📉"

            benchmark_rows.append(
                Tr(
                    Td(benchmark.metric, cls="font-medium"),
                    Td(f"{user_val:.1f}", cls=f"font-bold {comparison}"),
                    Td(f"{community_val:.1f}", cls="text-muted-foreground"),
                    Td(
                        Span(
                            f"{percentile}th",
                            cls=f"badge {'badge-success' if percentile >= 75 else 'badge-info' if percentile >= 50 else 'badge-ghost'} font-bold",
                        ),
                        cls="text-center",
                    ),
                    Td(f"{comparison_icon}", cls="text-2xl text-center"),
                )
            )

        return Card(
            CardBody(
                H2("🌍 Community Benchmarking", cls="text-2xl font-bold mb-4"),
                P(
                    "Compare your performance against anonymized community averages",
                    cls="text-muted-foreground mb-2",
                ),
                P("Data from 12,487 active SKUEL users", cls="text-xs text-muted-foreground mb-6"),
                Table(
                    Thead(
                        Tr(
                            Th("Metric", cls="text-left"),
                            Th("You", cls="text-left"),
                            Th("Community Avg", cls="text-left"),
                            Th("Your Percentile", cls="text-center"),
                            Th("Trend", cls="text-center"),
                        )
                    ),
                    Tbody(*benchmark_rows),
                    cls="table w-full",
                ),
                # Performance summary
                Div(
                    H3("🏆 Performance Summary", cls="font-semibold mb-2 mt-6"),
                    Div(
                        P(
                            "✨ You're in the top 15% of SKUEL users for habit system design",
                            cls="text-sm text-green-700 mb-2",
                        ),
                        P(
                            "🎯 Your identity voting rate is 2.2x the community average",
                            cls="text-sm text-purple-700 mb-2",
                        ),
                        P(
                            "📈 System strength 21% above average - excellent execution",
                            cls="text-sm text-blue-700",
                        ),
                        cls="p-4 bg-green-50 rounded-lg",
                    ),
                ),
            ),
            cls="mb-8",
        )

    @staticmethod
    def _get_essentiality_color(essentiality: str) -> str:
        """Get color class for essentiality level."""
        from ui.badge_classes import essentiality_badge_class

        return essentiality_badge_class(essentiality)

    @staticmethod
    def render_export_modal(export_format: str = "csv") -> Div:
        """Export analytics data modal."""
        return Div(
            Card(
                CardBody(
                    H2("📥 Export Analytics", cls="text-2xl font-bold mb-4"),
                    P(
                        "Download your complete habit analytics data",
                        cls="text-muted-foreground mb-6",
                    ),
                    # Export options
                    Div(
                        Label("Format:", cls="font-medium mb-2"),
                        Select(
                            Option("CSV (Excel)", value="csv", selected=export_format == "csv"),
                            Option(
                                "JSON (Developers)", value="json", selected=export_format == "json"
                            ),
                            Option("PDF Report", value="pdf", selected=export_format == "pdf"),
                            cls="mb-4",
                        ),
                        Label("Include:", cls="font-medium mb-2"),
                        Div(
                            Label(
                                Input(type="checkbox", checked=True, cls="checkbox mr-2"),
                                "System metrics",
                            ),
                            Label(
                                Input(type="checkbox", checked=True, cls="checkbox mr-2 ml-4"),
                                "Velocity data",
                            ),
                            Label(
                                Input(type="checkbox", checked=True, cls="checkbox mr-2 ml-4"),
                                "Identity votes",
                            ),
                            Label(
                                Input(type="checkbox", checked=False, cls="checkbox mr-2 ml-4"),
                                "Migration history",
                            ),
                            cls="flex flex-wrap gap-2 mb-6",
                        ),
                        cls="mb-6",
                    ),
                    # Actions
                    Div(
                        Button("Cancel", cls="btn btn-ghost", onclick="closeModal()"),
                        Button(
                            "📥 Export", cls="btn btn-primary", hx_get="/analytics/export/download"
                        ),
                        cls="flex gap-4 justify-end",
                    ),
                ),
            ),
            cls="modal modal-open",
        )
