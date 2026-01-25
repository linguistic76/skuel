"""
Metrics Calculator
==================

Shared metric calculation utilities for all intelligence services.

Consolidates threshold classification, weighted averages, and scaling functions
that were duplicated across 6 Activity Domain intelligence services.

Created: January 2026
ADR: Intelligence Service Helper Consolidation

Usage:
    from core.services.intelligence import MetricsCalculator

    # Threshold classification
    trend = MetricsCalculator.classify_by_threshold(
        75, [(80, "excellent"), (60, "good")], "needs_work"
    )

    # Weighted average (define extractors as named functions)
    def get_success_rate(h): return h.success_rate
    def get_priority_weight(h): return h.priority_weight
    avg = MetricsCalculator.weighted_average(habits, get_success_rate, get_priority_weight)

    # Combine factors
    probability = MetricsCalculator.combine_weighted_factors(
        {"progress": 0.8, "consistency": 0.6},
        {"progress": 0.35, "consistency": 0.35}
    )
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


class MetricsCalculator:
    """
    Static utility methods for common metric calculations.

    Consolidates calculation patterns from:
    - GoalsIntelligenceService: _calculate_progress_factor, _calculate_time_factor
    - HabitsIntelligenceService: _calculate_practice_effectiveness
    - PrinciplesIntelligenceService: _analyze_consistency, _calculate_harmony_score
    """

    @staticmethod
    def classify_by_threshold(
        value: float,
        thresholds: list[tuple[float, str]],
        default: str = "stable",
    ) -> str:
        """
        Classify a value based on threshold ranges.

        Thresholds are checked in order - first match wins.
        Use descending threshold order for typical "higher is better" metrics.

        Args:
            value: The value to classify
            thresholds: List of (threshold, label) pairs, checked in order
            default: Label if no threshold matches

        Returns:
            Classification label

        Example:
            classify_by_threshold(75, [(80, "excellent"), (60, "good")], "needs_work")
            # Returns "good" since 75 >= 60 but < 80
        """
        for threshold, label in thresholds:
            if value >= threshold:
                return label
        return default

    @staticmethod
    def weighted_average(
        items: Sequence[Any],
        value_fn: Callable[[Any], float],
        weight_fn: Callable[[Any], float],
    ) -> float:
        """
        Calculate weighted average from items.

        Args:
            items: Sequence of items to analyze
            value_fn: Function to extract value from each item
            weight_fn: Function to extract weight from each item

        Returns:
            Weighted average (0.0 if no items or zero total weight)

        Example:
            # Average habit success rate weighted by priority
            def get_success_rate(h): return h.success_rate
            def get_priority_weight(h): return h.priority_weight
            avg = MetricsCalculator.weighted_average(
                habits, get_success_rate, get_priority_weight
            )
        """
        if not items:
            return 0.0
        total_value = sum(value_fn(item) * weight_fn(item) for item in items)
        total_weight = sum(weight_fn(item) for item in items)
        return total_value / total_weight if total_weight > 0 else 0.0

    @staticmethod
    def simple_average(
        items: Sequence[Any],
        value_fn: Callable[[Any], float],
    ) -> float:
        """
        Calculate simple (unweighted) average from items.

        Args:
            items: Sequence of items to analyze
            value_fn: Function to extract value from each item

        Returns:
            Simple average (0.0 if no items)

        Example:
            def get_completion_score(t): return 1.0 if t.is_completed else 0.0
            avg_completion = MetricsCalculator.simple_average(tasks, get_completion_score)
        """
        if not items:
            return 0.0
        return sum(value_fn(item) for item in items) / len(items)

    @staticmethod
    def sigmoid_scale(
        value: float,
        midpoint: float = 0.5,
        steepness: float = 10.0,
        output_range: tuple[float, float] = (0.0, 1.0),
    ) -> float:
        """
        Apply sigmoid scaling to a value.

        Creates an S-curve transformation, useful for:
        - Converting linear progress to non-linear "feeling of progress"
        - Dampening extreme values while preserving mid-range sensitivity

        Used by GoalsIntelligenceService for progress factor calculations.

        Args:
            value: Input value (typically 0.0-1.0)
            midpoint: Value that maps to 0.5 output (default: 0.5)
            steepness: How sharp the S-curve is (higher = sharper, default: 10.0)
            output_range: (min, max) output values (default: (0.0, 1.0))

        Returns:
            Sigmoid-scaled value within output_range

        Example:
            # Progress feeling (50% feels like more than 50% done)
            feeling = MetricsCalculator.sigmoid_scale(0.5, midpoint=0.4, steepness=8)
        """
        min_out, max_out = output_range
        scaled = 1 / (1 + math.exp(-steepness * (value - midpoint)))
        return min_out + (max_out - min_out) * scaled

    @staticmethod
    def logarithmic_scale(
        value: float,
        base: float = 30.0,
        output_range: tuple[float, float] = (0.0, 1.0),
    ) -> float:
        """
        Apply logarithmic scaling (useful for time-based metrics).

        Creates diminishing returns effect - early units matter more.
        Commonly used for "days remaining" calculations.

        Used by GoalsIntelligenceService for time factor calculations.

        Args:
            value: Input value (e.g., days remaining)
            base: Log base for scaling (default: 30.0)
            output_range: (min, max) output values (default: (0.0, 1.0))

        Returns:
            Logarithmically-scaled value within output_range

        Example:
            # Time pressure factor (more urgent as deadline approaches)
            urgency = MetricsCalculator.logarithmic_scale(days_remaining, base=30)
        """
        min_out, max_out = output_range
        if value <= 0:
            return max_out  # Plenty of time / no time pressure
        scaled = 1.0 - (math.log(value + 1) / math.log(base + 1))
        return max(min_out, min(max_out, min_out + (max_out - min_out) * (1 - scaled)))

    @staticmethod
    def combine_weighted_factors(
        factors: dict[str, float],
        weights: dict[str, float],
        normalize: bool = True,
    ) -> float:
        """
        Combine multiple factors with weights.

        Used by GoalsIntelligenceService for probability calculation:
        probability = progress * 0.35 + consistency * 0.35 + time * 0.15 + momentum * 0.15

        Args:
            factors: Dict of factor_name -> factor_value (typically 0.0-1.0)
            weights: Dict of factor_name -> weight
            normalize: If True, normalize weights to sum to 1.0 (default: True)

        Returns:
            Weighted combination of factors

        Example:
            probability = MetricsCalculator.combine_weighted_factors(
                {"progress": 0.8, "consistency": 0.6, "time": 0.9, "momentum": 0.5},
                {"progress": 0.35, "consistency": 0.35, "time": 0.15, "momentum": 0.15}
            )
        """
        if not factors or not weights:
            return 0.0

        total_weight = sum(weights.values()) if normalize else 1.0
        weighted_sum = sum(factors.get(name, 0.0) * weight for name, weight in weights.items())
        return weighted_sum / total_weight if total_weight > 0 else 0.0

    @staticmethod
    def calculate_consistency_score(
        active_periods: int,
        total_periods: int,
        streak_length: int = 0,
        streak_bonus_weight: float = 0.1,
    ) -> float:
        """
        Calculate consistency score with optional streak bonus.

        Used by Habits, Principles for adherence tracking.

        Args:
            active_periods: Number of periods with activity
            total_periods: Total number of periods tracked
            streak_length: Current consecutive streak (default: 0)
            streak_bonus_weight: Weight per streak unit, capped at 0.2 (default: 0.1)

        Returns:
            Consistency score from 0.0 to 1.0

        Example:
            score = MetricsCalculator.calculate_consistency_score(
                active_periods=8, total_periods=10, streak_length=4
            )
            # Base: 0.8, streak bonus: 0.2 (capped), total: 1.0
        """
        if total_periods <= 0:
            return 0.0
        base_score = active_periods / total_periods
        streak_bonus = min(streak_length * streak_bonus_weight, 0.2)
        return min(1.0, base_score + streak_bonus)

    @staticmethod
    def calculate_ratio(
        numerator: int | float,
        denominator: int | float,
        default: float = 0.0,
    ) -> float:
        """
        Safely calculate a ratio with divide-by-zero protection.

        Args:
            numerator: Top of fraction
            denominator: Bottom of fraction
            default: Value to return if denominator is 0 (default: 0.0)

        Returns:
            Ratio or default value

        Example:
            completion_rate = MetricsCalculator.calculate_ratio(completed, total)
        """
        if denominator == 0:
            return default
        return float(numerator) / float(denominator)

    @staticmethod
    def clamp(
        value: float,
        min_val: float = 0.0,
        max_val: float = 1.0,
    ) -> float:
        """
        Clamp a value to a range.

        Args:
            value: Value to clamp
            min_val: Minimum allowed value (default: 0.0)
            max_val: Maximum allowed value (default: 1.0)

        Returns:
            Clamped value

        Example:
            score = MetricsCalculator.clamp(raw_score, 0.0, 1.0)
        """
        return max(min_val, min(max_val, value))

    @staticmethod
    def calculate_harmony_score(
        total_items: int,
        conflict_count: int,
    ) -> float:
        """
        Calculate harmony score based on conflicts vs possible conflicts.

        Used by PrinciplesIntelligenceService for principle harmony.

        Args:
            total_items: Total number of items (e.g., principles)
            conflict_count: Number of detected conflicts

        Returns:
            Harmony score from 0.0 to 1.0 (1.0 = no conflicts)

        Example:
            harmony = MetricsCalculator.calculate_harmony_score(
                total_items=5, conflict_count=2
            )
            # Max possible conflicts for 5 items: 5*4/2 = 10
            # Harmony: 1.0 - (2/10) = 0.8
        """
        # Maximum possible pairwise conflicts
        max_conflicts = total_items * (total_items - 1) // 2
        if max_conflicts == 0:
            return 1.0
        return 1.0 - (conflict_count / max_conflicts)

    @staticmethod
    def linear_interpolate(
        value: float,
        input_range: tuple[float, float],
        output_range: tuple[float, float],
    ) -> float:
        """
        Linearly interpolate a value from one range to another.

        Args:
            value: Input value within input_range
            input_range: (min, max) of input values
            output_range: (min, max) of output values

        Returns:
            Interpolated value in output_range

        Example:
            # Map 0-100 score to 0.0-1.0
            normalized = MetricsCalculator.linear_interpolate(75, (0, 100), (0.0, 1.0))
        """
        in_min, in_max = input_range
        out_min, out_max = output_range

        if in_max == in_min:
            return out_min

        # Normalize to 0-1, then scale to output range
        normalized = (value - in_min) / (in_max - in_min)
        return out_min + normalized * (out_max - out_min)
