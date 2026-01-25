"""
Tasks Service Sub-Services
===========================

This package contains focused sub-services that compose the unified TasksService.

Architecture: Facade Pattern
- Each sub-service handles a specific responsibility
- TasksService (facade) delegates to appropriate sub-service
- Zero breaking changes to external code

Sub-services:
- TasksCoreService: CRUD operations
- TasksSearchService: Search and discovery
- TasksProgressService: Progress tracking and completion
- TasksSchedulingService: Scheduling and recurrence
- TasksIntelligenceService: Graph-based intelligence + Task model analysis (NO AI dependencies)
- TasksAIService: AI-powered features (LLM/embeddings) - OPTIONAL
- TasksPlanningService: Context-first user planning methods

NOTE: TasksRelationshipService replaced by UnifiedRelationshipService (December 2025)
See: core/services/relationships/unified_relationship_service.py

NOTE: TasksGraphNativeService removed (January 2026)
Replaced by UnifiedRelationshipService - see ADR-029

NOTE: Intelligence Layer Separation (January 2026) - ADR-030
- TasksIntelligenceService now uses BaseAnalyticsService (NO AI deps)
- TasksAIService added for future AI-powered features
- App works fully without LLM/embeddings

NOTE: TasksAnalyticsService removed (January 2026)
- KU analytics methods moved to TasksService (direct KuAnalyticsEngine calls)
- Task model analysis methods moved to TasksIntelligenceService
- Simplifies architecture by removing unnecessary orchestration layer

Version: 2.2.0
Date: 2026-01-18
"""

# Import implemented services
from core.services.tasks.tasks_ai_service import TasksAIService
from core.services.tasks.tasks_core_service import TasksCoreService
from core.services.tasks.tasks_intelligence_service import TasksIntelligenceService
from core.services.tasks.tasks_planning_service import TasksPlanningService
from core.services.tasks.tasks_progress_service import TasksProgressService
from core.services.tasks.tasks_scheduling_service import TasksSchedulingService
from core.services.tasks.tasks_search_service import TasksSearchService

__all__ = [
    "TasksAIService",
    "TasksCoreService",
    "TasksIntelligenceService",
    "TasksPlanningService",
    "TasksProgressService",
    "TasksSchedulingService",
    "TasksSearchService",
]
