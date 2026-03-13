"""
Shared UI Components Library
============================

Reusable DaisyUI components following Dynamic Enum Pattern.

Core Principle: "Single source of truth for UI component patterns"

All components use dynamic enum methods from `/ui/enum_helpers.py`
for presentation (colors, icons, status). This ensures:
- Zero hardcoded presentation dictionaries
- UI updates automatically when enums change
- Consistent presentation across all dashboards

Components:
- MetricCard: Display metrics with trend indicators
- HealthStatusCard: System health visualization
- StatusBadge: Dynamic status badges
- ProgressMetric: Named progress bars with color coding
- InsightCard: AI insight display with confidence
- RecommendationCard: Action recommendations with CTA buttons
- TrendIndicator: Trend direction with icons/colors
- SettingToggle: Toggle settings display

Usage:
    from ui.shared_components import (
        MetricCard,
        HealthStatusCard,
        StatusBadge,
        ProgressMetric
    )

    # In route
    return Div(
        MetricCard(
            title="Productivity Score",
            value="82%",
            subtitle="Based on recent patterns",
            trend="increasing",
            color="blue"
        ),
        HealthStatusCard(health_data),
        ...
    )
"""

from typing import Any

from fasthtml.common import H3, H4, Details, Div, P, Span, Summary

from ui.buttons import Button
from ui.cards import Card, CardBody
from ui.enum_helpers import get_health_color, get_health_icon, get_trend_color, get_trend_icon
from ui.feedback import Alert, AlertT, Badge, Progress, ProgressT

# ============================================================================
# METRIC CARDS
# ============================================================================


def MetricCard(
    title: str,
    value: str,
    subtitle: str | None = None,
    trend: str | None = None,
    color: str = "blue",
) -> Any:
    """
    Display a key metric in a card with optional trend indicator.

    Args:
        title: Metric title/label,
        value: Main value to display (formatted string),
        subtitle: Additional context or description,
        trend: Trend direction string ("increasing", "decreasing", "stable"),
        color: Base color theme (Tailwind color name)

    Returns:
        Card component with metric display,

    Example:
        >>> MetricCard(
        ...     title="Productivity Score",
        ...     value="82%",
        ...     subtitle="Based on recent patterns",
        ...     trend="increasing",
        ...     color="blue",
        ... )
    """
    # Dynamic enum methods - updates when shared_enums.py changes
    trend_icon = get_trend_icon(trend) if trend else ""
    trend_color = get_trend_color(trend) if trend else "text-muted-foreground"

    return Card(
        CardBody(
            Div(
                Div(
                    P(title, cls="text-sm text-muted-foreground mb-1"),
                    H3(value, cls=f"text-3xl font-bold text-{color}-600 mb-1"),
                    P(subtitle, cls="text-xs text-muted-foreground") if subtitle else None,
                ),
                Span(trend_icon, cls=f"text-2xl {trend_color}") if trend else None,
                cls="flex justify-between items-start",
            ),
        ),
        cls=f"border-l-4 border-{color}-500",
    )


def QuickMetricCard(title: str, value: str, color: str = "primary") -> Div:
    """
    Compact metric display for grid layouts.

    Args:
        title: Metric title,
        value: Value to display,
        color: CSS class suffix (primary, accent, success)

    Returns:
        Div with compact metric display,

    Example:
        >>> QuickMetricCard("Tasks", "24", "primary")
    """
    return Card(
        CardBody(
            H3(title, cls="text-lg font-semibold"),
            P(value, cls=f"text-4xl font-bold text-{color}"),
            cls="text-center",
        ),
    )


# ============================================================================
# HEALTH STATUS COMPONENTS
# ============================================================================


def HealthStatusCard(health_data: dict[str, Any]) -> Any:
    """
    Display system health status with components and alerts.

    Args:
        health_data: Health status information with structure:
            {
                "status": "healthy|warning|critical|unknown",
                "timestamp": "ISO timestamp or formatted string",
                "components": {
                    "component_name": {"status": "healthy|warning|critical"}
                },
                "alerts": ["alert message 1", ...],
                "recommendations": ["recommendation 1", ...]
            }

    Returns:
        Card component with health visualization,

    Example:
        >>> health_data = {
        ...     "status": "healthy",
        ...     "timestamp": "2025-10-10 14:30",
        ...     "components": {
        ...         "database": {"status": "healthy"},
        ...         "cache": {"status": "warning"},
        ...     },
        ...     "alerts": ["Cache hit rate below threshold"],
        ...     "recommendations": ["Consider increasing cache size"],
        ... }
        >>> HealthStatusCard(health_data)
    """
    status = health_data.get("status", "unknown")

    # Dynamic enum methods - updates when shared_enums.py changes
    status_color = get_health_color(status)
    status_icon = get_health_icon(status)

    components = health_data.get("components", {})
    alerts = health_data.get("alerts", [])
    recommendations = health_data.get("recommendations", [])

    # Build components section
    components_section = None
    if components:
        components_section = Div(
            H4("Components", cls="text-sm font-medium text-muted-foreground mb-2"),
            Div(
                *[
                    Div(
                        Span(name.replace("_", " "), cls="capitalize"),
                        StatusBadge(
                            comp.get("status", "unknown"),
                            get_health_color(comp.get("status", "unknown")),
                            size="xs",
                        ),
                        cls="flex justify-between items-center text-sm",
                    )
                    for name, comp in components.items()
                ],
                cls="space-y-2",
            ),
            cls="mb-4",
        )

    # Build alerts section
    alerts_section = None
    if alerts:
        alerts_section = Div(
            H4(f"Alerts ({len(alerts)})", cls="text-sm font-medium text-muted-foreground mb-2"),
            Div(
                *[
                    Alert(alert, variant=AlertT.warning, cls="text-xs p-2")
                    for alert in alerts[:3]  # Show max 3 alerts
                ],
                cls="space-y-1",
            ),
            cls="mb-4",
        )

    # Build recommendations section
    recommendations_section = None
    if recommendations:
        recommendations_section = Details(
            Summary(
                f"View {len(recommendations)} recommendations",
                cls="cursor-pointer text-blue-600 hover:text-blue-800",
            ),
            Div(
                *[P(f"* {rec}", cls="pl-4 text-xs") for rec in recommendations],
                cls="mt-2 space-y-1 text-muted-foreground",
            ),
            cls="text-sm",
        )

    return Card(
        CardBody(
            # Header
            Div(
                Div(
                    H3("System Health", cls="text-lg font-semibold"),
                    StatusBadge(status.upper(), status_color, status_icon),
                    cls="flex items-center justify-between mb-2",
                ),
                P(
                    f"Last checked: {health_data.get('timestamp', 'Never')}",
                    cls="text-sm text-muted-foreground",
                ),
                cls="mb-4",
            ),
            components_section,
            alerts_section,
            recommendations_section,
        ),
    )


# ============================================================================
# STATUS & BADGES
# ============================================================================


def StatusBadge(label: str, color: str = "gray", icon: str | None = None, size: str = "md") -> Span:
    """
    Display a status badge with dynamic color and optional icon.

    Args:
        label: Badge text,
        color: Base color (from enum helpers or Tailwind color),
        icon: Optional icon/emoji to prepend,
        size: Badge size (xs, sm, md, lg)

    Returns:
        Badge component,

    Example:
        >>> StatusBadge("HEALTHY", "green", "✅")
        >>> StatusBadge("Active", get_status_color("active"))
    """
    size_classes = {
        "xs": "text-xs px-2 py-0.5",
        "sm": "text-sm px-2 py-1",
        "md": "text-sm px-3 py-1",
        "lg": "text-base px-4 py-2",
    }

    size_class = size_classes.get(size, size_classes["md"])
    content = f"{icon} {label}" if icon else label

    return Badge(
        content,
        cls=f"{size_class} bg-{color}-100 text-{color}-800 font-medium rounded",
    )


# ============================================================================
# PROGRESS METRICS
# ============================================================================


def ProgressMetric(
    name: str,
    value: float,
    max_value: float = 1.0,
    show_percentage: bool = True,
    color_threshold_fn=None,
) -> Div:
    """
    Display a named progress bar with automatic color coding.

    Args:
        name: Metric name/label,
        value: Current value (0.0 to max_value),
        max_value: Maximum value (default 1.0 for percentages),
        show_percentage: Display percentage next to name,
        color_threshold_fn: Optional function(value) -> ProgressT variant

    Returns:
        Div with progress bar,

    Example:
        >>> ProgressMetric("Data Quality", 0.88)
        >>> ProgressMetric("Tasks Complete", 12, max_value=20)
    """
    # Normalize to percentage
    percentage = (value / max_value) * 100 if max_value > 0 else 0

    # Default color threshold (green >= 80%, yellow >= 60%, red < 60%)
    if color_threshold_fn:
        progress_variant = color_threshold_fn(value)
    else:
        progress_variant = (
            ProgressT.success
            if percentage >= 80
            else ProgressT.warning
            if percentage >= 60
            else ProgressT.error
        )

    return Div(
        Div(
            Span(name, cls="font-medium"),
            Span(f"{percentage:.0f}%", cls="text-sm text-muted-foreground")
            if show_percentage
            else None,
            cls="flex justify-between mb-1",
        ),
        Progress(value=int(percentage), variant=progress_variant),
        cls="mb-4",
    )


# ============================================================================
# INSIGHT CARDS
# ============================================================================


def InsightCard(
    text: str, confidence: float = 0.0, category: str = "General", icon: str = "💡"
) -> Div:
    """
    Display an AI insight with confidence and category.

    Args:
        text: Insight text/description,
        confidence: Confidence score (0.0 to 1.0),
        category: Insight category,
        icon: Icon/emoji to display

    Returns:
        Div with insight display,

    Example:
        >>> InsightCard(
        ...     "Your productivity peaks at 10am consistently",
        ...     ConfidenceLevel.STANDARD,
        ...     category="Productivity",
        ... )
    """
    return Div(
        Div(
            Span(icon, cls="text-xl mr-3"),
            Div(
                P(text, cls="text-foreground mb-2"),
                Div(
                    Span(f"Confidence: {confidence:.0%}", cls="text-muted-foreground"),
                    Span(category, cls="text-primary font-medium"),
                    cls="flex gap-4 text-sm",
                ),
                cls="flex-1",
            ),
            cls="flex items-start",
        ),
        cls="p-4 bg-muted rounded shadow-sm",
    )


# ============================================================================
# RECOMMENDATION CARDS
# ============================================================================


def RecommendationCard(
    title: str,
    description: str,
    impact: str = "Medium",
    effort: str = "Medium",
    action_label: str = "Apply",
    learn_more: bool = True,
) -> Div:
    """
    Display an action recommendation with impact/effort and CTA buttons.

    Args:
        title: Recommendation title,
        description: Detailed description,
        impact: Impact level (High, Medium, Low),
        effort: Required effort (High, Medium, Low),
        action_label: Primary action button label,
        learn_more: Show "Learn More" button

    Returns:
        Div with recommendation display,

    Example:
        >>> RecommendationCard(
        ...     title="Optimize morning routine",
        ...     description="Your peak energy hours align with deep work",
        ...     impact="High",
        ...     effort="Low",
        ... )
    """
    return Div(
        H4(title, cls="font-semibold text-foreground mb-2"),
        P(description, cls="text-muted-foreground text-sm mb-3"),
        # Impact/Effort metrics
        Div(
            Span(f"Impact: {impact}", cls="text-green-600 font-medium"),
            Span(f"Effort: {effort}", cls="text-blue-600 font-medium"),
            cls="flex gap-4 mb-3 text-sm",
        ),
        # Action buttons
        Div(
            Button(action_label, cls="btn btn-sm btn-primary"),
            Button("Learn More", cls="btn btn-sm btn-outline") if learn_more else None,
            cls="flex gap-2",
        ),
        cls="p-4 border border-border rounded bg-background shadow-sm",
    )


# ============================================================================
# TREND INDICATORS
# ============================================================================


def TrendIndicator(
    label: str, direction: str, current: float, average: float, unit: str = ""
) -> Div:
    """
    Display a trend indicator with current vs. average comparison.

    Args:
        label: Metric label,
        direction: Trend direction ("increasing", "decreasing", "stable"),
        current: Current value,
        average: Average/baseline value,
        unit: Optional unit suffix (%, ms, etc.)

    Returns:
        Div with trend display,

    Example:
        >>> TrendIndicator(
        ...     label="Query Volume", direction="increasing", current=245.0, average=198.0
        ... )
    """
    # Dynamic enum methods
    direction_icon = get_trend_icon(direction)
    direction_color = get_trend_color(direction)

    return Div(
        Div(
            P(label, cls="text-sm font-medium text-muted-foreground"),
            Span(direction_icon, cls=f"text-lg {direction_color}"),
            cls="flex justify-between items-center mb-2",
        ),
        Div(
            Div(
                P("Current", cls="text-muted-foreground"),
                P(f"{current:.1f}{unit}", cls="font-medium"),
            ),
            Div(
                P("Average", cls="text-muted-foreground"),
                P(f"{average:.1f}{unit}", cls="font-medium"),
            ),
            cls="grid grid-cols-2 gap-2 text-xs",
        ),
        cls="p-3 bg-muted rounded",
    )


# ============================================================================
# SETTING TOGGLES
# ============================================================================


def SettingToggle(name: str, description: str, enabled: bool = True) -> Div:
    """
    Display a setting toggle with status.

    Args:
        name: Setting name,
        description: Setting description,
        enabled: Current enabled state

    Returns:
        Div with toggle display,

    Example:
        >>> SettingToggle(
        ...     "Auto-scheduling",
        ...     "Automatically schedule tasks based on context",
        ...     enabled=True,
        ... )
    """
    status_color = "text-green-600" if enabled else "text-muted-foreground"
    status_text = "Enabled" if enabled else "Disabled"

    return Div(
        Div(
            Span(name, cls="font-medium"),
            Span(status_text, cls=f"text-sm {status_color}"),
            cls="flex justify-between items-center",
        ),
        P(description, cls="text-sm text-muted-foreground mt-1"),
        cls="p-3 border border-border rounded cursor-pointer hover:bg-muted",
    )


# ============================================================================
# ANALYTICS SUMMARY BAR
# ============================================================================


def QuickStatsBar(metrics: dict[str, Any]) -> Div:
    """
    Display quick statistics bar with multiple metrics.

    Args:
        metrics: Dict with metric keys and values
            Expected keys: queries, avg_response_ms, cache_hit_rate,
                         semantic_rate, cross_domain_rate

    Returns:
        Div with stats bar,

    Example:
        >>> QuickStatsBar(
        ...     {
        ...         "queries": 1234,
        ...         "avg_response_ms": 45,
        ...         "cache_hit_rate": 0.82,
        ...         "semantic_rate": 0.67,
        ...     }
        ... )
    """
    # Build metric items conditionally
    items = [
        Div(
            P("Queries", cls="text-xs text-muted-foreground uppercase tracking-wide"),
            P(str(metrics.get("queries", 0)), cls="text-2xl font-bold"),
            cls="text-center",
        ),
        Div(
            P("Avg Response", cls="text-xs text-muted-foreground uppercase tracking-wide"),
            P(f"{metrics.get('avg_response_ms', 0)}ms", cls="text-2xl font-bold"),
            cls="text-center",
        ),
    ]

    if metrics.get("cache_hit_rate") is not None:
        items.append(
            Div(
                P("Cache Hit", cls="text-xs text-muted-foreground uppercase tracking-wide"),
                P(f"{metrics.get('cache_hit_rate', 0):.0%}", cls="text-2xl font-bold"),
                cls="text-center",
            )
        )

    if metrics.get("semantic_rate") is not None:
        items.append(
            Div(
                P("Semantic", cls="text-xs text-muted-foreground uppercase tracking-wide"),
                P(f"{metrics.get('semantic_rate', 0):.0%}", cls="text-2xl font-bold"),
                cls="text-center",
            )
        )

    if metrics.get("cross_domain_rate") is not None:
        items.append(
            Div(
                P("Cross-Domain", cls="text-xs text-muted-foreground uppercase tracking-wide"),
                P(f"{metrics.get('cross_domain_rate', 0):.0%}", cls="text-2xl font-bold"),
                cls="text-center",
            )
        )

    return Div(
        Div(*items, cls="flex justify-around flex-wrap gap-4"),
        cls="bg-gray-800 text-white p-4 rounded-lg shadow-lg",
    )


# ============================================================================
# PUBLIC API
# ============================================================================

__all__ = [
    # Alert
    "Alert",
    # Badge
    "Badge",
    # Health Status
    "HealthStatusCard",
    # Insights & Recommendations
    "InsightCard",
    # Metric Cards
    "MetricCard",
    # Progress
    "ProgressMetric",
    "QuickMetricCard",
    # Analytics
    "QuickStatsBar",
    "RecommendationCard",
    # Settings
    "SettingToggle",
    "StatusBadge",
    # Trends
    "TrendIndicator",
]
