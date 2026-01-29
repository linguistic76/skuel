"""
Habits Sub-Services
===================

This package contains focused sub-services that compose the unified HabitsService facade.

Architecture: Facade Pattern (8 sub-services)
- Each sub-service handles ONE specific responsibility
- HabitsService (facade) auto-delegates to appropriate sub-service via FacadeDelegationMixin
- ~50+ auto-generated delegation methods + explicit orchestration methods
- Most complex Activity Domain (streaks, consistency, event integration)
- Zero breaking changes to external code

Sub-Services:
- HabitsCoreService: CRUD operations, event publishing
- HabitSearchService: Search, discovery, filtering
- HabitsProgressService: Streaks, consistency tracking, keystone habits
- HabitsLearningService: Learning path integration, knowledge reinforcement
- HabitsPlanningService: Context-aware habit recommendations
- HabitsSchedulingService: Smart scheduling, capacity management
- HabitsEventIntegrationService: Cross-domain event scheduling integration
- HabitsIntelligenceService: Pure Cypher analytics (NO AI dependencies)

Common Import Pattern (Production):
    from core.services.habits_service import HabitsService  # Facade
    result = await habits_service.create_habit(request, user_uid)

Direct Sub-Service Import (Testing/Composition):
    from core.services.habits import HabitsCoreService
    core = HabitsCoreService(backend=mock_backend)

Documentation:
- Quick Start: /docs/guides/BASESERVICE_QUICK_START.md
- Sub-Service Catalog: /docs/reference/SUB_SERVICE_CATALOG.md
- Method Index: /docs/reference/BASESERVICE_METHOD_INDEX.md
- Service Topology: /docs/architecture/SERVICE_TOPOLOGY.md

Architecture Notes:
- HabitsRelationshipService replaced by UnifiedRelationshipService (December 2025)

Version: 3.1.0
Date: 2026-01-29
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
