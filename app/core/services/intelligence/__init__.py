"""
Intelligence Services Module
=============================

Shared intelligence patterns for all domains.

Provides:
- Metrics Calculators: Domain-specific path-aware metrics calculation functions
  (over the canonical typed cross-domain reader; path-aware context types live in
  ``core/models/graph/path_aware_types.py``)
- RecommendationEngine: Fluent builder for recommendation generation (consolidation)
- MetricsCalculator: Shared calculation utilities (consolidation)
- PatternAnalyzer: Pattern detection utilities (consolidation)
- TrendAnalyzer: Trend classification utilities (consolidation)
"""

from core.services.intelligence._core_intelligence_mixin import _CoreIntelligenceMixin
from core.services.intelligence.metrics_calculator import MetricsCalculator
from core.services.intelligence.metrics_calculators import (
    calculate_event_performance_metrics,
    calculate_goal_progress_metrics,
    calculate_habit_integration_metrics,
    calculate_principle_alignment_metrics,
    calculate_task_cross_domain_metrics,
    goal_learning_recommendations,
    goal_recommendations,
    habit_recommendations,
    principle_gap_insights,
    principle_gap_recommendations,
    principle_recommendations,
    task_recommendations,
)
from core.services.intelligence.pattern_analyzer import PatternAnalyzer

# consolidation: Shared helper utilities (January 2026)
from core.services.intelligence.recommendation_engine import RecommendationEngine
from core.services.intelligence.trend_analyzer import (
    Trend,
    analyze_activity_trajectory,
    analyze_completion_trend,
    analyze_trend_with_details,
    compare_progress_to_expected,
    determine_trend_from_rate,
)

__all__ = [
    # Shared core intelligence mixin
    "_CoreIntelligenceMixin",
    # Path-aware metrics calculators (over the canonical typed reader)
    "calculate_event_performance_metrics",
    "calculate_goal_progress_metrics",
    "calculate_habit_integration_metrics",
    "calculate_principle_alignment_metrics",
    "calculate_task_cross_domain_metrics",
    "goal_learning_recommendations",
    "goal_recommendations",
    "habit_recommendations",
    "principle_gap_insights",
    "principle_gap_recommendations",
    "principle_recommendations",
    "task_recommendations",
    # consolidation: Shared helper utilities (January 2026)
    "MetricsCalculator",
    "PatternAnalyzer",
    "RecommendationEngine",
    "Trend",
    "analyze_activity_trajectory",
    "analyze_completion_trend",
    "analyze_trend_with_details",
    "compare_progress_to_expected",
    "determine_trend_from_rate",
]
