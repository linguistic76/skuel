"""
Habits Sub-Services
===================

Decomposed habits service following the facade pattern.

Sub-services:
- HabitsCoreService: Basic CRUD operations
- HabitSearchService: Search and discovery (DomainSearchOperations[Habit] protocol)
- HabitsProgressService: Streaks, consistency, keystone habits
- HabitsLearningService: Learning path integration
- HabitsIntelligenceService: pure Cypher analytics
- HabitsEventIntegrationService: Cross-domain event scheduling integration
- HabitsPlanningService: Context-aware habit recommendations (January 2026)
- HabitsSchedulingService: Smart scheduling and capacity management (January 2026)

NOTE: HabitsRelationshipService replaced by UnifiedRelationshipService (December 2025)
See: core/services/relationships/unified_relationship_service.py

Version: 3.0.0
Date: 2026-01-19
"""

from core.services.habits.habit_search_service import HabitSearchService
from core.services.habits.habits_core_service import HabitsCoreService
from core.services.habits.habits_event_integration_service import HabitsEventIntegrationService
from core.services.habits.habits_intelligence_service import HabitsIntelligenceService
from core.services.habits.habits_learning_service import HabitsLearningService
from core.services.habits.habits_planning_service import HabitsPlanningService
from core.services.habits.habits_progress_service import HabitsProgressService
from core.services.habits.habits_scheduling_service import HabitsSchedulingService

__all__ = [
    "HabitSearchService",
    "HabitsCoreService",
    "HabitsEventIntegrationService",
    "HabitsIntelligenceService",
    "HabitsLearningService",
    "HabitsPlanningService",
    "HabitsProgressService",
    "HabitsSchedulingService",
]
