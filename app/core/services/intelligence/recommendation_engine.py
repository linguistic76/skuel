"""
Recommendation Engine
=====================

Parameterized recommendation generation for all intelligence services.

Consolidates 30+ separate _generate_*_recommendations methods into a single
fluent builder pattern.

Created: January 2026
ADR: Intelligence Service Helper Consolidation

Usage:
    from core.services.intelligence import RecommendationEngine

    engine = RecommendationEngine()
    recommendations = (
        engine.with_metrics(metrics)
        .add_threshold_check("consistency", 0.5, "Low consistency - build habits")
        .add_threshold_check("progress", 0.3, "Behind schedule - increase focus")
        .add_conditional(score > 0.9, "Excellent performance!")
        .build()
    )
"""

from __future__ import annotations

from typing import Any


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
            engine.with_metrics({"consistency": 0.4, "progress": 0.2})
            .add_threshold_check("consistency", 0.5, "Improve consistency")
            .add_threshold_check("progress", 0.3, "Increase focus", comparison="lt")
            .add_conditional(True, "General tip")
            .build()
        )
    """

    def __init__(self) -> None:
        """Initialize empty recommendation builder."""
        self._recommendations: list[str] = []
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
        comparison: str = "lt",
    ) -> RecommendationEngine:
        """
        Add recommendation if metric crosses threshold.

        Args:
            metric_name: Key in metrics dict
            threshold: Threshold value to compare against
            message: Recommendation message if triggered
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
            self._recommendations.append(message)
        return self

    def add_conditional(
        self,
        condition: bool,
        message: str,
    ) -> RecommendationEngine:
        """
        Add recommendation if condition is True.

        Args:
            condition: Boolean condition to check
            message: Recommendation message if True

        Returns:
            Self for chaining

        Example:
            .add_conditional(habits_count == 0, "Add habits to support this goal")
        """
        if condition:
            self._recommendations.append(message)
        return self

    def add_message(self, message: str) -> RecommendationEngine:
        """
        Add a recommendation unconditionally.

        Args:
            message: Recommendation message

        Returns:
            Self for chaining
        """
        self._recommendations.append(message)
        return self

    def build(self) -> list[str]:
        """
        Return accumulated recommendations.

        Returns:
            List of recommendation messages
        """
        return list(self._recommendations)
