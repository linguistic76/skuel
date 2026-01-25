"""
Events Sub-Services
===================

Decomposed events service following the facade pattern.

Sub-services:
- EventsCoreService: Basic CRUD operations
- EventsSearchService: Search and discovery (DomainSearchOperations[Event] protocol)
- EventsHabitIntegrationService: Cross-domain habits integration
- EventsLearningService: Learning and knowledge integration
- EventsIntelligenceService: pure Cypher analytics

NOTE: EventsRelationshipService replaced by UnifiedRelationshipService (December 2025)
See: core/services/relationships/unified_relationship_service.py

Version: 2.0.0
Date: 2025-12-03
"""

from core.services.events.events_core_service import EventsCoreService
from core.services.events.events_habit_integration_service import EventsHabitIntegrationService
from core.services.events.events_intelligence_service import EventsIntelligenceService
from core.services.events.events_learning_service import EventsLearningService
from core.services.events.events_progress_service import EventsProgressService
from core.services.events.events_scheduling_service import EventsSchedulingService
from core.services.events.events_search_service import EventsSearchService

__all__ = [
    "EventsCoreService",
    "EventsHabitIntegrationService",
    "EventsIntelligenceService",
    "EventsLearningService",
    "EventsProgressService",
    "EventsSchedulingService",
    "EventsSearchService",
]
