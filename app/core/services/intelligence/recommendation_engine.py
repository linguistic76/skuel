"""
Recommendation Engine
=====================

Parameterized recommendation generation for all intelligence services.

Consolidates 30+ separate _generate_*_recommendations methods into a single
fluent builder pattern.

Created: January 2026
ADR: Intelligence Service Helper Consolidation

Usage:
    from core.services.intelligence import RecommendationEngine, RecommendationLevel

    engine = RecommendationEngine()
    recommendations = (
        engine.with_metrics(metrics)
        .add_threshold_check("consistency", 0.5, "Low consistency - build habits")
        .add_threshold_check("progress", 0.3, "Behind schedule - increase focus")
        .add_range_check("streak", [(0, 1, "Start a streak!"), (7, 100, "Great streak!")])
        .add_conditional(score > 0.9, "Excellent performance!")
        .build()
    )
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


class RecommendationLevel(str, Enum):
    """Severity level for recommendations."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    SUCCESS = "success"


class RecommendationEngine:
    """
    Fluent builder + threshold-based recommendation generator.

    This engine consolidates the common recommendation generation pattern
    found across all intelligence services:

    1. Check metric thresholds
    2. Build recommendation list
    3. Return list[str]

    Example:
        engine = RecommendationEngine()
        recommendations = (
            engine.with_metrics({"consistency": 0.4, "progress": 0.2, "streak": 5})
            .add_threshold_check("consistency", 0.5, "Improve consistency")
            .add_threshold_check("progress", 0.3, "Increase focus", comparison="lt")
            .add_range_check("streak", [(0, 3, "Build streak"), (7, 100, "Great streak!")])
            .add_conditional(True, "General tip")
            .build()
        )
    """

    def __init__(self) -> None:
        """Initialize empty recommendation builder."""
        self._recommendations: list[tuple[RecommendationLevel, str]] = []
        self._metrics: dict[str, float] = {}

    def with_metrics(self, metrics: dict[str, Any]) -> RecommendationEngine:
        """
        Set metrics dict for threshold checks.

        Args:
            metrics: Dict of metric_name -> value (numeric values extracted)

        Returns:
            Self for chaining
        """
        self._metrics = {k: float(v) for k, v in metrics.items() if isinstance(v, int | float)}
        return self

    def add_threshold_check(
        self,
        metric_name: str,
        threshold: float,
        message: str,
        level: RecommendationLevel = RecommendationLevel.WARNING,
        comparison: str = "lt",
    ) -> RecommendationEngine:
        """
        Add recommendation if metric crosses threshold.

        Args:
            metric_name: Key in metrics dict
            threshold: Threshold value to compare against
            message: Recommendation message if triggered
            level: Severity level (default: WARNING)
            comparison: One of "lt", "gt", "le", "ge" (default: "lt")

        Returns:
            Self for chaining

        Example:
            .add_threshold_check("consistency", 0.5, "Low consistency", comparison="lt")
            # Triggers if consistency < 0.5
        """
        value = self._metrics.get(metric_name, 0.0)
        comparisons = {
            "lt": value < threshold,
            "gt": value > threshold,
            "le": value <= threshold,
            "ge": value >= threshold,
        }
        triggered = comparisons.get(comparison, False)

        if triggered:
            self._recommendations.append((level, message))
        return self

    def add_range_check(
        self,
        metric_name: str,
        ranges: list[tuple[float, float, str]],
        level: RecommendationLevel = RecommendationLevel.INFO,
    ) -> RecommendationEngine:
        """
        Add recommendation based on value falling in range.

        Args:
            metric_name: Key in metrics dict
            ranges: List of (min_val, max_val, message) tuples, first match wins
            level: Severity level (default: INFO)

        Returns:
            Self for chaining

        Example:
            .add_range_check("streak", [
                (0, 1, "Start a streak!"),
                (1, 7, "Keep building!"),
                (7, 100, "Great streak!")
            ])
        """
        value = self._metrics.get(metric_name, 0.0)
        for min_val, max_val, message in ranges:
            if min_val <= value < max_val:
                self._recommendations.append((level, message))
                break
        return self

    def add_conditional(
        self,
        condition: bool,
        message: str,
        level: RecommendationLevel = RecommendationLevel.INFO,
    ) -> RecommendationEngine:
        """
        Add recommendation if condition is True.

        Args:
            condition: Boolean condition to check
            message: Recommendation message if True
            level: Severity level (default: INFO)

        Returns:
            Self for chaining

        Example:
            .add_conditional(habits_count == 0, "Add habits to support this goal")
        """
        if condition:
            self._recommendations.append((level, message))
        return self

    def add_from_template(
        self,
        template_fn: Callable[[dict[str, Any]], list[str]],
    ) -> RecommendationEngine:
        """
        Add recommendations from domain-specific template function.

        Use this for complex domain-specific logic that doesn't fit
        the threshold/range patterns.

        Args:
            template_fn: Function taking metrics dict, returning list of messages

        Returns:
            Self for chaining

        Example:
            def goal_specific_recs(metrics):
                recs = []
                if metrics.get("habits_supporting") == 0:
                    recs.append("Add habits to support this goal")
                return recs

            .add_from_template(goal_specific_recs)
        """
        for msg in template_fn(self._metrics):
            self._recommendations.append((RecommendationLevel.INFO, msg))
        return self

    def add_message(
        self,
        message: str,
        level: RecommendationLevel = RecommendationLevel.INFO,
    ) -> RecommendationEngine:
        """
        Add a recommendation unconditionally.

        Args:
            message: Recommendation message
            level: Severity level (default: INFO)

        Returns:
            Self for chaining
        """
        self._recommendations.append((level, message))
        return self

    def build(self) -> list[str]:
        """
        Return accumulated recommendations (strings only).

        Returns:
            List of recommendation messages
        """
        return [msg for _, msg in self._recommendations]

    def build_with_levels(self) -> list[tuple[RecommendationLevel, str]]:
        """
        Return recommendations with severity levels.

        Returns:
            List of (level, message) tuples
        """
        return self._recommendations.copy()

    def clear(self) -> RecommendationEngine:
        """
        Clear accumulated recommendations for reuse.

        Returns:
            Self for chaining
        """
        self._recommendations = []
        return self

    def __len__(self) -> int:
        """Return count of accumulated recommendations."""
        return len(self._recommendations)

    def __bool__(self) -> bool:
        """Return True if any recommendations accumulated."""
        return len(self._recommendations) > 0
