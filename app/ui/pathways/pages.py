"""Pathways page trees — pure rendering for the /pathways route family.

Extracted from ``adapters/inbound/pathways_ui.py`` per the routes-in-adapters /
rendering-in-``ui/`` convention: routes parse the request and call the
orchestrator; every FT tree lives here. Shell pages load their bodies via HTMX
(``content_loading_placeholder``); the ``*_content`` builders render those
fragments from already-fetched data.
"""

from typing import Any

from fasthtml.common import Div, P

from ui.components import ButtonT, Card, CardBody, CardHeader, CardTitle
from ui.pathways.components import (
    PathwaysUIComponents,
    render_step_browser_card,
)
from ui.patterns.error_banner import render_inline_error
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.primitives import ButtonLink
from ui.ui_types import ActivePathData, LearningStatsData


def dashboard_shell() -> Any:
    """/pathways shell — content loads via HTMX."""
    return Div(
        PageHeader(
            "Pathways Dashboard",
            subtitle="Track your learning journey and discover new knowledge",
        ),
        content_loading_placeholder("/pathways/content", "pathways-dashboard-content"),
        cls="container mx-auto px-4 py-6",
    )


def dashboard_content_error(message: str) -> Any:
    """G7: an all-zeros dashboard on a query failure reads as "you have no
    paths" — render the error instead of a fabricated empty state."""
    return Div(
        render_inline_error(f"Could not load your learning overview: {message}"),
        cls="max-w-xl mx-auto py-8",
    )


def dashboard_content(active_paths: list[ActivePathData], stats: LearningStatsData) -> Any:
    """HTMX fragment: pathways dashboard body."""
    if active_paths:
        paths_section = Div(
            *[PathwaysUIComponents.render_learning_path_card(p) for p in active_paths],
            cls="space-y-4",
        )
    else:
        paths_section = Div(
            P(
                "No active learning paths yet. Start exploring!",
                cls="text-muted-foreground text-center py-8",
            ),
            Div(
                ButtonLink(
                    "Browse Learning Paths",
                    href="/pathways/browse",
                    cls=ButtonT.primary,
                ),
                ButtonLink(
                    "Browse Learning Steps",
                    href="/pathways/steps",
                    cls=ButtonT.secondary,
                ),
                cls="flex flex-wrap gap-3 justify-center",
            ),
            cls="text-center",
        )

    return Div(
        Card(
            CardHeader(CardTitle("Learning Overview")),
            CardBody(
                StatsGrid(
                    [
                        StatItem(
                            label="Learning Hours",
                            value=f"{stats.total_hours:.0f}",
                            color="primary",
                        ),
                        StatItem(
                            label="Concepts Mastered",
                            value=str(stats.concepts_mastered),
                            color="success",
                        ),
                        StatItem(
                            label="Active Paths",
                            value=str(len(active_paths)),
                            color="primary",
                        ),
                        StatItem(
                            label="Completion Rate",
                            value=f"{stats.completion_rate * 100:.0f}%",
                            color="warning",
                        ),
                    ],
                ),
            ),
            cls="mb-8",
        ),
        Card(
            CardHeader(
                Div(
                    CardTitle("Active Learning Paths"),
                    Div(
                        ButtonLink(
                            "Browse Learning Paths",
                            href="/pathways/browse",
                            cls=ButtonT.primary,
                            size="sm",
                        ),
                        ButtonLink(
                            "Browse Learning Steps",
                            href="/pathways/steps",
                            cls=ButtonT.secondary,
                            size="sm",
                        ),
                        cls="flex flex-wrap gap-2",
                    ),
                    cls="flex justify-between items-center",
                ),
            ),
            CardBody(paths_section),
            cls="mb-8",
        ),
        Card(
            CardHeader(CardTitle("Quick Actions")),
            CardBody(
                Div(
                    ButtonLink(
                        "View Analytics",
                        href="/pathways/analytics",
                        cls=ButtonT.secondary,
                    ),
                    ButtonLink(
                        "Browse Paths",
                        href="/pathways/browse",
                        cls=ButtonT.secondary,
                    ),
                    ButtonLink(
                        "Browse Steps",
                        href="/pathways/steps",
                        cls=ButtonT.secondary,
                    ),
                    cls="flex flex-wrap gap-3",
                ),
            ),
            cls="mb-8",
        ),
        id="pathways-dashboard-content",
    )


def browse_shell() -> Any:
    """/pathways/browse shell — content loads via HTMX."""
    return Div(
        PageHeader(
            "Browse Learning Paths",
            subtitle="Discover structured learning paths to achieve your goals",
        ),
        content_loading_placeholder("/pathways/browse/content", "pathways-browse-content"),
        cls="container mx-auto px-4 py-6",
    )


def browse_content(available_paths: list[dict[str, Any]]) -> Any:
    """HTMX fragment: browse learning paths body."""
    return Div(
        Card(
            CardHeader(CardTitle("Filter Learning Paths")),
            CardBody(
                Div(
                    PathwaysUIComponents.render_filter_form(),
                    cls="grid grid-cols-1 md:grid-cols-3 gap-4",
                ),
            ),
            cls="mb-8",
        ),
        Div(paths_grid(available_paths), id="learning-paths-grid", cls="mb-8"),
        id="pathways-browse-content",
    )


def paths_grid(
    paths: list[dict[str, Any]], empty_message: str = "No learning paths available yet."
) -> Any:
    """Browser-card grid over path display dicts (shared by browse + filter)."""
    if paths:
        return Div(
            *[PathwaysUIComponents.render_learning_path_browser_card(p) for p in paths],
            cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6",
        )
    return Div(
        P(empty_message, cls="text-muted-foreground text-center py-8"),
    )


def steps_browser_page(steps: list[Any]) -> Any:
    """/pathways/steps page content."""
    if steps:
        grid_content = Div(
            *[render_step_browser_card(s) for s in steps],
            cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6",
        )
    else:
        grid_content = Div(
            P(
                "No path steps available yet.",
                cls="text-muted-foreground text-center py-8",
            ),
        )

    return Div(
        PageHeader(
            "Browse Learning Steps", subtitle="Explore individual path steps across all paths"
        ),
        Div(
            grid_content,
            id="path-steps-grid",
            cls="mb-8",
        ),
        cls="container mx-auto px-4 py-6",
    )


def analytics_shell() -> Any:
    """/pathways/analytics shell — content loads via HTMX."""
    return Div(
        PageHeader("Learning Analytics", subtitle="Insights into your learning journey"),
        content_loading_placeholder("/pathways/analytics/content", "pathways-analytics-content"),
        cls="container mx-auto px-4 py-6",
    )


def analytics_content(analytics: dict[str, Any]) -> Any:
    """HTMX fragment: learning analytics body."""
    concepts_mastered = analytics.get("concepts_mastered", 0)
    in_progress = analytics.get("in_progress", 0)
    active_paths_count = analytics.get("active_paths_count", 0)
    avg_retention = analytics.get("avg_retention")

    # The former "Learning Health" card is folded in here (SKUEL030 tranche 3):
    # two of its three tiles ("Needs Review", "Struggling") read analytics keys
    # fed by writer-less :NEEDS_REVIEW / :STRUGGLING_WITH edges, so they always
    # rendered 0. With those gone only "Active Paths" remained — a lone tile in
    # a 3-column grid — so it joins the Knowledge Profile row.
    return Div(
        Card(
            CardHeader(CardTitle("Knowledge Profile")),
            CardBody(
                StatsGrid(
                    [
                        StatItem(
                            label="Concepts Mastered",
                            value=str(concepts_mastered),
                            color="success",
                        ),
                        StatItem(label="In Progress", value=str(in_progress), color="primary"),
                        StatItem(
                            label="Avg Retention",
                            value="—" if avg_retention is None else f"{avg_retention * 100:.0f}%",
                            color="warning",
                        ),
                        StatItem(label="Active Paths", value=str(active_paths_count)),
                    ],
                    cols=4,
                ),
            ),
            cls="mb-8",
        ),
        id="pathways-analytics-content",
    )
