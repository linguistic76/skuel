"""
Trend Analyzer
==============

Threshold-based trend classification utilities for intelligence services.

Consolidates trend analysis patterns across:
- TasksIntelligenceService: _analyze_performance_trends
- GoalsIntelligenceService: _determine_trend
- PrinciplesIntelligenceService: _analyze_trajectory, _determine_trend

Created: January 2026
ADR: Intelligence Service Helper Consolidation

Usage:
    from core.services.intelligence import Trend, analyze_completion_trend

    # Completion-based trend
    result = analyze_completion_trend(completed=80, total=100)
    # Returns {"trend": "excellent", "completion_rate": 80.0, "analyzed_count": 100}

    # Activity trajectory
    trend, avg = analyze_activity_trajectory(activities=12, periods=4)
    # Returns ("improving", 3.0)

    # Progress comparison
    trend = compare_progress_to_expected(
        actual=0.6, expected=0.5, improving_items=5, declining_items=2
    )
    # Returns "improving"
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class Trend(str, Enum):
    """
    Standard trend classification values.

    Used across all intelligence services for consistent trend reporting.
    """

    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    EXCELLENT = "excellent"
    NEEDS_ATTENTION = "needs_attention"
    INSUFFICIENT_DATA = "insufficient_data"


def analyze_completion_trend(
    completed_count: int,
    total_count: int,
    thresholds: list[tuple[float, str]] | None = None,
) -> dict[str, Any]:
    """
    Analyze completion rate and classify trend.

    Used by TasksIntelligenceService for performance trends.

    Args:
        completed_count: Number of completed items
        total_count: Total number of items
        thresholds: Optional list of (rate, label) tuples (default: 80/60/40 thresholds)

    Returns:
        Dict with "trend", "completion_rate", "analyzed_count"

    Example:
        result = analyze_completion_trend(80, 100)
        # Returns {
        #     "trend": "excellent",
        #     "completion_rate": 80.0,
        #     "analyzed_count": 100
        # }
    """
    if total_count == 0:
        return {
            "trend": Trend.INSUFFICIENT_DATA.value,
            "completion_rate": 0.0,
            "analyzed_count": 0,
        }

    rate = (completed_count / total_count) * 100
    default_thresholds = [
        (80, Trend.EXCELLENT.value),
        (60, Trend.IMPROVING.value),
        (40, Trend.STABLE.value),
    ]

    trend = Trend.NEEDS_ATTENTION.value
    for threshold, label in thresholds or default_thresholds:
        if rate >= threshold:
            trend = label
            break

    return {
        "trend": trend,
        "completion_rate": round(rate, 1),
        "analyzed_count": total_count,
    }


def analyze_activity_trajectory(
    activity_count: int,
    period_count: int,
    improving_threshold: float = 3.0,
    declining_threshold: float = 1.0,
) -> tuple[str, float]:
    """
    Analyze activity trajectory over time periods.

    Used by PrinciplesIntelligenceService for adherence trends.

    Args:
        activity_count: Total activities in the period
        period_count: Number of periods (e.g., weeks)
        improving_threshold: Average above this = improving (default: 3.0)
        declining_threshold: Average below this = declining (default: 1.0)

    Returns:
        Tuple of (trend_label, average_per_period)

    Example:
        trend, avg = analyze_activity_trajectory(12, 4)
        # Returns ("improving", 3.0)  since 12/4 = 3.0 >= 3.0
    """
    avg = activity_count / period_count if period_count > 0 else 0

    if avg > improving_threshold:
        return Trend.IMPROVING.value, avg
    elif avg < declining_threshold:
        return Trend.DECLINING.value, avg
    return Trend.STABLE.value, avg


def compare_progress_to_expected(
    actual_progress: float,
    expected_progress: float,
    improving_items: int = 0,
    declining_items: int = 0,
) -> str:
    """
    Compare actual vs expected progress with item trend tiebreaker.

    Used by GoalsIntelligenceService for trend determination.

    Args:
        actual_progress: Current progress (0.0-1.0 or 0-100)
        expected_progress: Expected progress at this point
        improving_items: Count of improving sub-items (e.g., habits with streak)
        declining_items: Count of declining sub-items (e.g., habits with broken streak)

    Returns:
        Trend label ("improving", "declining", or "stable")

    Example:
        trend = compare_progress_to_expected(
            actual=0.6, expected=0.5, improving_items=5, declining_items=2
        )
        # Returns "improving" (ahead of schedule AND more improving than declining)
    """
    if actual_progress > expected_progress and improving_items > declining_items:
        return Trend.IMPROVING.value
    elif declining_items > improving_items:
        return Trend.DECLINING.value
    return Trend.STABLE.value


def analyze_trend_with_details(
    activity_count: int,
    period_count: int,
    improving_threshold: float = 3.0,
    declining_threshold: float = 1.0,
) -> dict[str, Any]:
    """
    Analyze trajectory with additional statistics.

    Extended version of analyze_activity_trajectory that also calculates
    most/least active period estimates.

    Used by PrinciplesIntelligenceService for detailed adherence trends.

    Args:
        activity_count: Total activities in the period
        period_count: Number of periods (e.g., weeks)
        improving_threshold: Average above this = improving
        declining_threshold: Average below this = declining

    Returns:
        Dict with "trajectory", "avg_per_period", "most_active", "least_active"

    Example:
        result = analyze_trend_with_details(12, 4)
        # Returns {
        #     "trajectory": "improving",
        #     "avg_per_period": 3.0,
        #     "most_active": {"period": 1, "count": 4},
        #     "least_active": {"period": 4, "count": 1}
        # }
    """
    trajectory, avg = analyze_activity_trajectory(
        activity_count, period_count, improving_threshold, declining_threshold
    )

    # Estimate most/least active (simplified - in reality would need per-period data)
    most_active = {"period": 1, "count": int(avg * 1.5)}
    least_active = {"period": period_count, "count": max(0, int(avg * 0.5))}

    return {
        "trajectory": trajectory,
        "avg_per_period": avg,
        "most_active": most_active,
        "least_active": least_active,
    }


def determine_trend_from_rate(
    rate: float,
    thresholds: list[tuple[float, str]] | None = None,
    default: str = Trend.STABLE.value,
) -> str:
    """
    Determine trend from a single rate value.

    Simpler variant for cases where you have a pre-calculated rate.

    Args:
        rate: Rate value (typically 0-100 or 0.0-1.0)
        thresholds: List of (threshold, label) pairs, checked in order
        default: Fallback if no threshold matches

    Returns:
        Trend label

    Example:
        trend = determine_trend_from_rate(75, [(80, "excellent"), (60, "good")])
        # Returns "good"
    """
    default_thresholds = [
        (80, Trend.EXCELLENT.value),
        (60, Trend.IMPROVING.value),
        (40, Trend.STABLE.value),
    ]

    for threshold, label in thresholds or default_thresholds:
        if rate >= threshold:
            return label
    return default
