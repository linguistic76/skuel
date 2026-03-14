"""
Knowledge Service Sub-Services
================================

This package contains focused sub-services that compose the unified LessonService.

Architecture: Facade Pattern (January 2026 - ADR-031)
- Each sub-service handles a specific responsibility
- LessonService (facade) delegates to appropriate sub-service
- Zero breaking changes to external code

Sub-services:
- LessonCoreService: CRUD operations
- LessonSearchService: Search and discovery
- LessonGraphService: Graph navigation and relationships
- LessonSemanticService: Semantic relationship management
- LessonPracticeService: Event-driven practice tracking
- LessonMasteryService: Pedagogical tracking (VIEWED->IN_PROGRESS->MASTERED)

DELETED (January 2026):
- KuLpService: Redundant delegation to LpService (use LpService directly)
"""

# Import implemented services
from core.services.lesson.lesson_adaptive_service import LessonAdaptiveService
from core.services.lesson.lesson_core_service import LessonCoreService
from core.services.lesson.lesson_graph_service import LessonGraphService
from core.services.lesson.lesson_mastery_service import (
    LessonMasteryService,
    LearningState,
    UserKuProgress,
)
from core.services.lesson.lesson_practice_service import LessonPracticeService
from core.services.lesson.lesson_search_service import LessonSearchService
from core.services.lesson.lesson_semantic_service import LessonSemanticService

__all__ = [
    "LessonAdaptiveService",
    "LessonCoreService",
    "LessonGraphService",
    "LessonMasteryService",
    "LessonPracticeService",
    "LessonSearchService",
    "LessonSemanticService",
    "LearningState",
    "UserKuProgress",
]
