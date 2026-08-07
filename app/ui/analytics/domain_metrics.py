"""Per-domain analytics metrics rendering."""

from typing import Any

from fasthtml.common import H3, H4, Div, Span

from core.models.enums import AnalyticsDomain
from ui.components import Card
from ui.data import TableFromDicts, TableT
from ui.feedback import Alert, AlertT
from ui.patterns.stats_grid import StatCard, StatItem, StatsGrid


def render_metrics_cards(report: Any) -> Any:
    """Render metric cards based on analytics domain."""
    metrics = report.metrics
    domain = report.analytics_domain

    renderers = {
        AnalyticsDomain.TASKS: render_tasks_metrics,
        AnalyticsDomain.HABITS: render_habits_metrics,
        AnalyticsDomain.GOALS: render_goals_metrics,
        AnalyticsDomain.EVENTS: render_events_metrics,
        AnalyticsDomain.CHOICES: render_choices_metrics,
    }

    renderer = renderers.get(domain, render_generic_metrics)
    return renderer(metrics)


def render_tasks_metrics(metrics: dict) -> Any:
    """Render task metrics."""
    return Div(
        H3("Task Metrics", cls="text-lg font-semibold mb-4"),
        StatsGrid(
            [
                StatItem(label="Total Tasks", value=str(metrics.get("total_count", 0))),
                StatItem(label="Completed", value=str(metrics.get("completed_count", 0))),
                StatItem(label="In Progress", value=str(metrics.get("in_progress_count", 0))),
                StatItem(label="Pending", value=str(metrics.get("pending_count", 0))),
            ],
            cls="mb-6",
        ),
        StatCard(
            label="Completion Rate",
            value=f"{metrics.get('completion_rate', 0)}%",
            change="Tasks completed in period",
            color="success",
        ),
        (
            Card(
                H4("Priority Distribution", cls="font-semibold mb-3"),
                TableFromDicts(
                    header_data=["Priority", "Count"],
                    body_data=[
                        {"Priority": p.title(), "Count": str(c)}
                        for p, c in metrics.get("priority_distribution", {}).items()
                    ],
                    cls=(TableT.striped,),
                ),
                cls="bg-background shadow-xs p-4 mb-4",
            )
            if metrics.get("priority_distribution")
            else ""
        ),
        (
            Alert(
                Div(
                    Span(f"{metrics.get('overdue_count', 0)} Overdue Tasks", cls="font-semibold"),
                    cls="flex items-center",
                ),
                variant=AlertT.warning,
            )
            if metrics.get("overdue_count", 0) > 0
            else ""
        ),
    )


def render_habits_metrics(metrics: dict) -> Any:
    """Render habit metrics."""
    return Div(
        H3("Habit Metrics", cls="text-lg font-semibold mb-4"),
        StatsGrid(
            [
                StatItem(label="Active Habits", value=str(metrics.get("total_active", 0))),
                StatItem(label="Consistency", value=f"{metrics.get('consistency_rate', 0)}%"),
            ],
            cols=2,
            cls="mb-6",
        ),
        (
            Card(
                H4("Current Streaks", cls="font-semibold mb-3"),
                *[
                    Div(
                        Span(habit_name, cls="font-medium"),
                        Span(f"{days} days", cls="text-success"),
                        cls="flex justify-between py-2",
                    )
                    for habit_name, days in metrics.get("current_streaks", {}).items()
                ],
                cls="bg-background shadow-xs p-4",
            )
            if metrics.get("current_streaks")
            else ""
        ),
    )


def render_goals_metrics(metrics: dict) -> Any:
    """Render goal metrics."""
    return Div(
        H3("Goal Metrics", cls="text-lg font-semibold mb-4"),
        StatsGrid(
            [
                StatItem(label="Active Goals", value=str(metrics.get("total_active", 0))),
                StatItem(label="On Track", value=str(metrics.get("on_track_count", 0))),
                StatItem(label="At Risk", value=str(metrics.get("at_risk_count", 0))),
                StatItem(
                    label="Avg Progress",
                    value=f"{metrics.get('avg_progress_percentage', 0)}%",
                ),
            ]
        ),
    )


def render_events_metrics(metrics: dict) -> Any:
    """Render event metrics."""
    return Div(
        H3("Event Metrics", cls="text-lg font-semibold mb-4"),
        StatsGrid(
            [
                StatItem(label="Total Events", value=str(metrics.get("total_count", 0))),
                StatItem(label="Upcoming", value=str(metrics.get("upcoming_count", 0))),
                StatItem(label="Completed", value=str(metrics.get("completed_count", 0))),
                StatItem(
                    label="Hours Scheduled",
                    value=str(metrics.get("total_hours_scheduled", 0)),
                ),
            ]
        ),
    )


def render_choices_metrics(metrics: dict) -> Any:
    """Render choice metrics."""
    return Div(
        H3("Choice Metrics", cls="text-lg font-semibold mb-4"),
        StatsGrid(
            [
                StatItem(label="Total Choices", value=str(metrics.get("total_choices", 0))),
                StatItem(label="Reviewed", value=str(metrics.get("choices_reviewed_count", 0))),
            ],
            cols=2,
        ),
    )


def render_generic_metrics(metrics: dict) -> Any:
    """Fallback for generic metrics display."""
    return Card(
        H4("Metrics", cls="font-semibold mb-3"),
        TableFromDicts(
            header_data=["Metric", "Value"],
            body_data=[
                {"Metric": k.replace("_", " ").title(), "Value": str(v)}
                for k, v in metrics.items()
                if not isinstance(v, dict)
            ],
            cls=(TableT.striped,),
        ),
        cls="bg-background shadow-xs p-4",
    )
