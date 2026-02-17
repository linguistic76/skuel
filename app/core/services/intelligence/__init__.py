"""
Intelligence Services Module
=============================

Shared intelligence patterns for all domains.

Provides:
- QueryIntelligenceService: Query intelligence (intent detection, facet suggestion, ranking)
- GraphContextOrchestrator[T]: Generic APOC orchestration (Phase 2 consolidation)
- Typed Context Dataclasses: Type-safe containers for cross-domain context data
- Metrics Calculators: Domain-specific metrics calculation functions
- RecommendationEngine: Fluent builder for recommendation generation (Phase 5 consolidation)
- MetricsCalculator: Shared calculation utilities (Phase 5 consolidation)
- PatternAnalyzer: Pattern detection utilities (Phase 5 consolidation)
- TrendAnalyzer: Trend classification utilities (Phase 5 consolidation)
"""

from core.services.intelligence.cross_domain_contexts import (
    ChoiceCrossContext,
    CrossDomainContext,
    EventCrossContext,
    FinanceCrossContext,
    GoalCrossContext,
    HabitCrossContext,
    KnowledgeCrossContext,
    PrincipleCrossContext,
    TaskCrossContext,
)
from core.services.intelligence.graph_context_orchestrator import GraphContextOrchestrator
from core.services.intelligence.metrics_calculator import MetricsCalculator
from core.services.intelligence.metrics_calculators import (
    calculate_choice_metrics,
    calculate_event_metrics,
    calculate_finance_metrics,
    calculate_goal_metrics,
    calculate_habit_metrics,
    calculate_knowledge_metrics,
    calculate_principle_metrics,
    calculate_task_metrics,
)
from core.services.intelligence.pattern_analyzer import PatternAnalyzer
from core.services.intelligence.query_intelligence_service import (
    FacetDetector,
    IntentScorer,
    QueryIntelligenceService,
    ResultRanker,
)

# Phase 5 consolidation: Shared helper utilities (January 2026)
from core.services.intelligence.recommendation_engine import (
    RecommendationEngine,
    RecommendationLevel,
)
from core.services.intelligence.trend_analyzer import (
    Trend,
    analyze_activity_trajectory,
    analyze_completion_trend,
    analyze_trend_with_details,
    compare_progress_to_expected,
    determine_trend_from_rate,
)

__all__ = [
    # Query intelligence (renamed from BaseIntelligenceService January 2026)
    "QueryIntelligenceService",
    "FacetDetector",
    "IntentScorer",
    "ResultRanker",
    # Graph context orchestrator
    "GraphContextOrchestrator",
    # Typed context dataclasses
    "ChoiceCrossContext",
    "CrossDomainContext",
    "EventCrossContext",
    "FinanceCrossContext",
    "GoalCrossContext",
    "HabitCrossContext",
    "KnowledgeCrossContext",
    "PrincipleCrossContext",
    "TaskCrossContext",
    # Metrics calculators
    "calculate_choice_metrics",
    "calculate_event_metrics",
    "calculate_finance_metrics",
    "calculate_goal_metrics",
    "calculate_habit_metrics",
    "calculate_knowledge_metrics",
    "calculate_principle_metrics",
    "calculate_task_metrics",
    # Phase 5 consolidation: Shared helper utilities (January 2026)
    "MetricsCalculator",
    "PatternAnalyzer",
    "RecommendationEngine",
    "RecommendationLevel",
    "Trend",
    "analyze_activity_trajectory",
    "analyze_completion_trend",
    "analyze_trend_with_details",
    "compare_progress_to_expected",
    "determine_trend_from_rate",
]
