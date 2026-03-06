"""
Knowledge Service Sub-Services
================================

This package contains focused sub-services that compose the unified ArticleService.

Architecture: Facade Pattern (January 2026 - ADR-031)
- Each sub-service handles a specific responsibility
- ArticleService (facade) delegates to appropriate sub-service
- Zero breaking changes to external code

Sub-services:
- ArticleCoreService: CRUD operations
- ArticleSearchService: Search and discovery
- ArticleGraphService: Graph navigation and relationships
- ArticleSemanticService: Semantic relationship management
- ArticlePracticeService: Event-driven practice tracking
- ArticleMasteryService: Pedagogical tracking (VIEWED->IN_PROGRESS->MASTERED)

DELETED (January 2026):
- KuLpService: Redundant delegation to LpService (use LpService directly)
"""

# Import implemented services
from core.services.article.article_adaptive_service import ArticleAdaptiveService
from core.services.article.article_core_service import ArticleCoreService
from core.services.article.article_graph_service import ArticleGraphService
from core.services.article.article_mastery_service import (
    ArticleMasteryService,
    LearningState,
    UserKuProgress,
)
from core.services.article.article_practice_service import ArticlePracticeService
from core.services.article.article_search_service import ArticleSearchService
from core.services.article.article_semantic_service import ArticleSemanticService

__all__ = [
    "ArticleAdaptiveService",
    "ArticleCoreService",
    "ArticleGraphService",
    "ArticleMasteryService",
    "ArticlePracticeService",
    "ArticleSearchService",
    "ArticleSemanticService",
    "LearningState",
    "UserKuProgress",
]
