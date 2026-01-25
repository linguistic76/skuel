"""
Goals Service Sub-Services
===========================

Specialized sub-services for goal management operations.

Sub-Services:
- GoalsCoreService: CRUD operations
- GoalsSearchService: Search and discovery (DomainSearchOperations[Goal] protocol)
- GoalsProgressService: Progress tracking and milestones
- GoalsLearningService: Learning path integration
- GoalsPlanningService: UserContext-dependent planning methods
- GoalsSchedulingService: Capacity management and schedule optimization (January 2026)
- GoalsIntelligenceService: pure Cypher analytics + predictive analytics

NOTE: GoalsRelationshipService replaced by UnifiedRelationshipService (December 2025)
See: core/services/relationships/unified_relationship_service.py

NOTE: GoalsGraphNativeService removed (January 2026)
Replaced by UnifiedRelationshipService - see ADR-029

Version: 6.0.0
Date: 2026-01-19
Architecture: Facade pattern with specialized sub-services
"""

from core.services.goals.goals_core_service import GoalsCoreService
from core.services.goals.goals_intelligence_service import (
    GoalPrediction,
    GoalsIntelligenceService,
    HabitImpactAnalysis,
)
from core.services.goals.goals_learning_service import GoalsLearningService
from core.services.goals.goals_planning_service import GoalsPlanningService
from core.services.goals.goals_progress_service import GoalsProgressService
from core.services.goals.goals_recommendation_service import GoalsRecommendationService
from core.services.goals.goals_scheduling_service import (
    AchievabilityResult,
    GoalCapacityResult,
    GoalSequenceItem,
    GoalsSchedulingService,
    TimelineSuggestion,
)
from core.services.goals.goals_search_service import GoalsSearchService

__all__ = [
    "AchievabilityResult",
    "GoalCapacityResult",
    "GoalPrediction",
    "GoalSequenceItem",
    "GoalsCoreService",
    "GoalsIntelligenceService",
    "GoalsLearningService",
    "GoalsPlanningService",
    "GoalsProgressService",
    "GoalsRecommendationService",
    "GoalsSchedulingService",
    "GoalsSearchService",
    "HabitImpactAnalysis",
    "TimelineSuggestion",
]
