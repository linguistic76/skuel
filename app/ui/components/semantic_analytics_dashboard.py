#!/usr/bin/env python3
"""
Semantic Analytics Dashboard UI Components
==========================================

DaisyUI components for displaying semantic analytics.

✅ MIGRATED TO SHARED UI COMPONENTS (October 10, 2025)
- Previously: Custom component implementations
- Now: Uses /core/ui/shared_components.py for common UI elements
- Retains: Domain-specific components (KnowledgeGapCard, AnalyticsDashboard)

✅ MIGRATED TO DAISYUI (January 2026)
- Replaced MonsterUI/FrankenUI imports with DaisyUI component wrappers

Components:
- KnowledgeGapsList: Display knowledge gaps (domain-specific)
- TrendsCard: Trend analysis visualization (domain-specific)
- AnalyticsDashboard: Main dashboard component
- AnalyticsWidget: Embeddable widget
"""

from typing import Any

from fasthtml.common import H1, H3, H4, Details, P, Summary

from core.ui.daisy_components import Button, Card, CardBody, Div, Span
from core.ui.enum_helpers import get_severity_color
from core.ui.shared_components import (
    Badge,
    HealthStatusCard,
    MetricCard,
    QuickStatsBar,
    TrendIndicator,
)
from core.utils.logging import get_logger

logger = get_logger(__name__)


# Note: MetricCard, HealthStatusCard, TrendIndicator, QuickStatsBar
# are now imported from core.ui.shared_components


def KnowledgeGapCard(gap: dict[str, Any], index: int) -> Div:
    """
    Display a single knowledge gap.

    Args:
        gap: Gap information,
        index: Gap index for display
    """
    severity = gap.get("severity", "low")
    # Dynamic enum method - updates when shared_enums.py changes
    severity_color = get_severity_color(severity)

    return Div(cls=f"p-3 border-l-4 border-{severity_color}-400 bg-white rounded shadow-sm")(
        Div(cls="flex justify-between items-start mb-2")(
            Div()(
                H4(cls="font-medium text-gray-900")(
                    f"{index}. {gap.get('description', 'Unknown gap')}"
                ),
                P(cls="text-xs text-gray-500 mt-1")(
                    f"Type: {gap.get('type', 'unknown').replace('_', ' ').title()}"
                ),
            ),
            Badge(cls=f"px-2 py-1 text-xs bg-{severity_color}-100 text-{severity_color}-800")(
                severity.upper()
            ),
        ),
        # Affected areas
        gap.get("affected_areas")
        and Div(cls="mb-2")(
            P(cls="text-xs text-gray-600")("Affected:"),
            Div(cls="flex flex-wrap gap-1 mt-1")(
                *[
                    Span(area, cls="px-2 py-0.5 text-xs bg-gray-100 rounded")
                    for area in gap.get("affected_areas", [])[:5]
                ]
            ),
        ),
        # Suggested action
        P(cls="text-sm text-gray-700 italic")(
            f"💡 {gap.get('suggested_action', 'No action suggested')}"
        ),
        # Metrics
        gap.get("metrics")
        and Details(cls="mt-2 text-xs")(
            Summary(cls="cursor-pointer text-gray-500")("View metrics"),
            Div(cls="mt-1 pl-4 text-gray-600")(
                *[P()(f"{k}: {v}") for k, v in gap.get("metrics", {}).items()]
            ),
        ),
    )


def KnowledgeGapsList(gaps_data: dict[str, Any]) -> Card:
    """
    Display list of knowledge gaps.

    Args:
        gaps_data: Knowledge gaps information
    """
    gaps = gaps_data.get("gaps", [])
    summary = gaps_data.get("summary", {})

    return Card(
        CardBody(
            # Header
            Div(cls="mb-4")(
                H3(cls="text-lg font-semibold mb-2")("Knowledge Gaps Analysis"),
                Div(cls="flex gap-4 text-sm")(
                    Span("Total: " + str(summary.get("total_gaps", 0)), cls="text-gray-600"),
                    summary.get("by_severity", {}).get("high", 0) > 0
                    and Span(
                        f"High: {summary['by_severity']['high']}", cls="text-red-600 font-medium"
                    ),
                    summary.get("by_severity", {}).get("medium", 0) > 0
                    and Span(f"Medium: {summary['by_severity']['medium']}", cls="text-yellow-600"),
                    summary.get("by_severity", {}).get("low", 0) > 0
                    and Span(f"Low: {summary['by_severity']['low']}", cls="text-blue-600"),
                ),
            ),
            # Gaps list
            (
                gaps
                and Div(cls="space-y-3 max-h-96 overflow-y-auto")(
                    *[
                        KnowledgeGapCard(gap, i + 1)
                        for i, gap in enumerate(gaps[:10])  # Show max 10 gaps
                    ]
                )
            )
            or P(cls="text-gray-500 text-center py-8")("No knowledge gaps detected!"),
        ),
        cls="bg-white rounded-lg shadow",
    )


def TrendsCard(trends_data: dict[str, Any]) -> Card:
    """
    Display trend analysis using shared TrendIndicator component.

    Args:
        trends_data: Trend analysis data
    """
    trends = trends_data.get("trends", {})
    period = trends_data.get("period_hours", 24)

    return Card(
        CardBody(
            # Header
            Div(cls="mb-4")(
                H3(cls="text-lg font-semibold")("Trends"),
                P(cls="text-sm text-gray-600")(f"Last {period} hours"),
            ),
            # Trend indicators using shared component
            Div(cls="grid grid-cols-2 gap-3")(
                trends.get("query_volume")
                and TrendIndicator(
                    label="Query Volume",
                    direction=trends["query_volume"].get("direction", "stable"),
                    current=trends["query_volume"].get("current", 0),
                    average=trends["query_volume"].get("average", 0),
                ),
                trends.get("performance")
                and TrendIndicator(
                    label="Response Time",
                    direction=trends["performance"].get("direction", "stable"),
                    current=trends["performance"].get("current", 0),
                    average=trends["performance"].get("average", 0),
                    unit="ms",
                ),
                trends.get("semantic_enhancement")
                and TrendIndicator(
                    label="Semantic Rate",
                    direction=trends["semantic_enhancement"].get("direction", "stable"),
                    current=trends["semantic_enhancement"].get("current", 0),
                    average=trends["semantic_enhancement"].get("average", 0),
                    unit="%",
                ),
                trends.get("cross_domain")
                and TrendIndicator(
                    label="Cross-Domain",
                    direction=trends["cross_domain"].get("direction", "stable"),
                    current=trends["cross_domain"].get("current", 0),
                    average=trends["cross_domain"].get("average", 0),
                    unit="%",
                ),
            ),
        ),
        cls="bg-white rounded-lg shadow",
    )


# Note: QuickStatsBar is now imported from core.ui.shared_components


def AnalyticsDashboard(
    dashboard_data: dict[str, Any] | None = None, auto_refresh: bool = True
) -> Div:
    """
    Main analytics dashboard component.

    Args:
        dashboard_data: Pre-loaded dashboard data,
        auto_refresh: Enable auto-refresh
    """
    if not dashboard_data:
        # Empty state - will be populated via HTMX
        return Div(
            id="analytics-dashboard",
            cls="container mx-auto p-6",
            hx_get="/api/semantic/analytics/dashboard",
            hx_trigger="load" + (", every 30s" if auto_refresh else ""),
            hx_swap="innerHTML",
        )(Div(cls="text-center py-12")(P(cls="text-gray-500")("Loading analytics...")))

    # Extract data
    current_metrics = dashboard_data.get("current_metrics", {})
    health = dashboard_data.get("health", {})
    gaps = dashboard_data.get("gaps", {})
    trends = dashboard_data.get("trends", {})

    return Div(id="analytics-dashboard", cls="container mx-auto p-6")(
        # Header
        Div(cls="mb-6")(
            Div(cls="flex justify-between items-center")(
                H1(cls="text-3xl font-bold text-gray-900")("📊 Semantic Analytics Dashboard"),
                Div(cls="flex gap-2")(
                    Button(
                        "Refresh",
                        cls="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700",
                        hx_get="/api/semantic/analytics/dashboard",
                        hx_target="#analytics-dashboard",
                        hx_swap="innerHTML",
                    ),
                    auto_refresh
                    and Badge(
                        "Auto-refresh ON", cls="px-3 py-2 bg-green-100 text-green-800 text-sm"
                    ),
                ),
            ),
            P(cls="text-sm text-gray-600 mt-1")(
                f"Last updated: {dashboard_data.get('timestamp', 'Never')}"
            ),
        ),
        # Quick stats bar
        QuickStatsBar(current_metrics),
        # Main grid
        Div(cls="grid grid-cols-1 lg:grid-cols-3 gap-6")(
            # Left column - Metrics (using shared MetricCard)
            Div(cls="space-y-4")(
                MetricCard(
                    title="Total Queries",
                    value=str(current_metrics.get("queries", 0)),
                    subtitle="Last 5 minutes",
                    trend=trends.get("query_volume"),
                    color="blue",
                ),
                MetricCard(
                    title="Avg Response Time",
                    value=f"{current_metrics.get('avg_response_ms', 0)}ms",
                    subtitle="P95 included",
                    trend=trends.get("performance"),
                    color="green",
                ),
                MetricCard(
                    title="Cache Hit Rate",
                    value=f"{current_metrics.get('cache_hit_rate', 0):.1%}",
                    subtitle="Efficiency metric",
                    trend=None,
                    color="purple",
                ),
                MetricCard(
                    title="Semantic Enhancement",
                    value=f"{current_metrics.get('semantic_rate', 0):.1%}",
                    subtitle="Intent-based queries",
                    trend=trends.get("semantic"),
                    color="indigo",
                ),
            ),
            # Middle column - Health & Trends
            Div(cls="space-y-4")(
                HealthStatusCard(health),
                TrendsCard(
                    {
                        "trends": {
                            "query_volume": {"direction": trends.get("query_volume", "stable")},
                            "performance": {"direction": trends.get("performance", "stable")},
                            "semantic_enhancement": {"direction": trends.get("semantic", "stable")},
                        }
                    }
                ),
            ),
            # Right column - Knowledge Gaps
            KnowledgeGapsList(gaps),
        ),
        # Auto-refresh indicator
        auto_refresh
        and Div(
            cls="fixed bottom-4 right-4",
            hx_get="/api/semantic/analytics/dashboard",
            hx_trigger="every 30s",
            hx_target="#analytics-dashboard",
            hx_swap="innerHTML",
        ),
    )


def AnalyticsWidget(widget_type: str = "metrics", refresh_seconds: int = 60) -> Div:
    """
    Standalone analytics widget for embedding.

    Args:
        widget_type: Type of widget (metrics, health, gaps, trends),
        refresh_seconds: Auto-refresh interval
    """
    endpoints = {
        "metrics": "/api/semantic/analytics/metrics",
        "health": "/api/semantic/analytics/health",
        "gaps": "/api/semantic/analytics/gaps",
        "trends": "/api/semantic/analytics/trends",
    }

    endpoint = endpoints.get(widget_type, endpoints["metrics"])

    return Div(
        cls="analytics-widget p-4 bg-white rounded-lg shadow",
        hx_get=endpoint,
        hx_trigger=f"load, every {refresh_seconds}s",
        hx_swap="innerHTML",
    )(Div(cls="text-center py-8")(P(cls="text-gray-500")(f"Loading {widget_type}...")))


# Export components
# Note: MetricCard, HealthStatusCard, TrendIndicator, QuickStatsBar
# are now available from core.ui.shared_components
__all__ = [
    "AnalyticsDashboard",
    "AnalyticsWidget",
    "KnowledgeGapCard",
    "KnowledgeGapsList",
    "TrendsCard",
]
