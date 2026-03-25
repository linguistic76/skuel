"""
Lesson Service - Facade
========================

Unified interface for all lesson operations.
Delegates to specialized sub-services for focused responsibilities.

Sub-Services:
- LessonCoreService: CRUD operations
- LessonSearchService: Search and discovery
- LessonGraphService: Graph navigation and relationships
- LessonSemanticService: Semantic relationship management
- LessonPracticeService: Event-driven practice tracking
- LessonMasteryService: Pedagogical tracking (VIEWED->IN_PROGRESS->MASTERED)

Graph and Semantic services are internal implementation details.
External callers should use the LessonService facade methods.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.constants import GraphDepth, QueryLimit
from core.ports.query_types import ListContext

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import SemanticTriple
    from core.models.context_types import ContextualKnowledge
    from core.models.enums.learning_enums import SELCategory
    from core.models.lesson.lesson import Lesson
    from core.models.pathways.learning_progress import LearningJourney
    from core.ports import (
        EventBusOperations,
        LessonOperations,
        QueryBuilderOperations,
    )
    from core.services.lesson.lesson_organization_service import (
        KuNavigation,
        OrganizationView,
    )
    from core.services.user import UserContext

# Import models for type hints
# SemanticRelationshipType needed at runtime for enum conversion
from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.models.curriculum_dto import CurriculumDTO
from core.ports.base_protocols import HasUID
from core.services.filtered_context import build_filtered_context

# Import sub-services
from core.services.lesson.lesson_ai_service import LessonAIService
from core.utils.decorators import with_error_handling
from core.utils.error_boundary import safe_event_handler
from core.utils.list_helpers import FilterConfig, SortConfig, apply_entity_filter, apply_entity_sort
from core.utils.logging import get_logger
from core.utils.metrics import get_metrics_summary
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_created_at_attr, get_second_item, get_title_lower

# Allowlists for substance metric Cypher interpolation (prevents injection)
_VALID_SUBSTANCE_METRICS: frozenset[str] = frozenset(
    {
        "times_applied_in_tasks",
        "times_practiced_in_events",
        "times_built_into_habits",
        "choices_informed_count",
    }
)

_VALID_SUBSTANCE_TIMESTAMP_FIELDS: frozenset[str] = frozenset(
    {
        "last_applied_date",
        "last_practiced_date",
        "last_built_into_habit_date",
        "last_choice_informed_date",
    }
)


def _compute_lesson_stats(all_lessons: list[Any]) -> dict[str, int | float]:
    """Compute pre-filter stats from the full lesson set."""
    from core.models.enums import EntityStatus

    published = sum(
        1 for ls in all_lessons if getattr(ls, "status", None) == EntityStatus.PUBLISHED
    )
    return {
        "total": len(all_lessons),
        "active": published,
        "published": published,
        "draft": sum(1 for ls in all_lessons if getattr(ls, "status", None) == EntityStatus.DRAFT),
    }


def _is_lesson_published(lesson: Any) -> bool:
    """Filter predicate: lesson has PUBLISHED status."""
    from core.models.enums import EntityStatus

    return getattr(lesson, "status", None) == EntityStatus.PUBLISHED


def _is_lesson_draft(lesson: Any) -> bool:
    """Filter predicate: lesson has DRAFT status."""
    from core.models.enums import EntityStatus

    return getattr(lesson, "status", None) == EntityStatus.DRAFT


def _is_lesson_archived(lesson: Any) -> bool:
    """Filter predicate: lesson has ARCHIVED status."""
    from core.models.enums import EntityStatus

    return getattr(lesson, "status", None) == EntityStatus.ARCHIVED


_LESSON_FILTER_CONFIG: FilterConfig = {
    "published": _is_lesson_published,
    "draft": _is_lesson_draft,
    "archived": _is_lesson_archived,
}

_LESSON_SORT_CONFIG: SortConfig = {
    "title": (get_title_lower, False),
    "created_at": (get_created_at_attr, True),
}


def _apply_lesson_sort(lessons: list[Any], sort_by: str) -> list[Any]:
    """Sort lessons using declarative config."""
    return apply_entity_sort(lessons, sort_by, _LESSON_SORT_CONFIG, "title")


class LessonService:
    """
    Unified facade for lesson operations.

    Delegates to specialized sub-services (January 2026 - ADR-031):
    - LessonCoreService: CRUD operations
    - LessonSearchService: Search and discovery
    - LessonGraphService: Graph navigation and relationships
    - LessonSemanticService: Semantic relationship management
    - LessonPracticeService: Event-driven practice tracking
    - LessonMasteryService: Pedagogical tracking
    - UnifiedRelationshipService: Harmonious relationship operations
    - LessonIntelligenceService: Intelligence and analytics
    - LessonOrganizationService: ORGANIZES relationships (any lesson can organize others)

    Access relationship operations via self.relationships:
    - get_related_entities("prerequisites", uid) - Get prerequisite lessons
    - get_related_entities("enables_learning", uid) - Get enabled lessons
    - get_related_entities("applied_in_tasks", uid) - Get tasks that apply this lesson
    - get_related_entities("reinforced_by_habits", uid) - Get habits that reinforce this lesson
    """

    # ========================================================================
    # DELEGATION METHODS
    # ========================================================================

    # Core CRUD delegations
    async def create(
        self,
        title: str,
        body: str,
        summary: str = "",
        tags: list[str] | None = None,
        **metadata: Any,
    ) -> Result[CurriculumDTO]:
        return await self.core.create(title, body, summary, tags, **metadata)

    async def get(self, uid: str) -> Result["Lesson"]:
        return await self.core.get(uid)

    async def update(self, uid: str, **updates: Any) -> Result[CurriculumDTO]:
        return await self.core.update(uid, **updates)

    async def delete(self, uid: str) -> Result[bool]:
        return await self.core.delete(uid)

    async def publish(self, uid: str) -> Result[CurriculumDTO]:
        return await self.core.publish(uid)

    async def archive(self, uid: str) -> Result[CurriculumDTO]:
        return await self.core.archive(uid)

    async def get_user_mastery(self, user_uid: str, ku_uid: str) -> Result[float]:
        return await self.core.get_user_mastery(user_uid, ku_uid)

    async def get_all_user_knowledge_status(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all knowledge entities with per-user VIEWED/BOOKMARKED/MASTERED status."""
        return await self.mastery.get_all_user_knowledge_status(user_uid)

    async def get_chunks(self, uid: str, chunk_type: Any = None) -> Result[list[Any]]:
        return await self.core.get_chunks(uid, chunk_type)

    async def analyze_content(self, uid: str) -> Result[dict[str, Any]]:
        return await self.core.analyze_content(uid)

    async def get_with_template(self, uid: str) -> Result["Lesson"]:
        return await self.core.get(uid)

    async def get_with_content(self, uid: str) -> Result[tuple["Lesson", str]]:
        return await self.core.get_with_content(uid)

    # Search delegations (using search_service attribute)
    async def search_by_title_template(
        self, search_term: str, limit: int = 25
    ) -> Result[list[CurriculumDTO]]:
        return await self.search_service.search_by_title_template(search_term, limit)

    async def search_with_user_context(
        self, query: str, user_context: dict[str, Any] | None = None, limit: int = 25
    ) -> Result[list[CurriculumDTO]]:
        return await self.search_service.search_with_user_context(query, user_context, limit)

    async def find_similar_content(
        self, uid: str, limit: int = 5, prefer_vector_search: bool = True
    ) -> Result[list[CurriculumDTO]]:
        return await self.search_service.find_similar_content(uid, limit, prefer_vector_search)

    async def search_by_tags(
        self, tags: list[str], match_all: bool = False, limit: int = 25
    ) -> Result[list[CurriculumDTO]]:
        return await self.search_service.search_by_tags(tags, match_all, limit)

    async def search_by_facets(
        self,
        tags: list[str] | None = None,
        domain: str | None = None,
        complexity: str | None = None,
        status: str | None = None,
        limit: int = 25,
    ) -> Result[list[CurriculumDTO]]:
        return await self.search_service.search_by_facets(tags, domain, complexity, status, limit)

    async def search_chunks_with_facets(
        self, query: str, facets: dict[str, Any] | None = None, limit: int = 20
    ) -> Result[list[dict[str, Any]]]:
        return await self.search_service.search_chunks_with_facets(query, facets, limit)

    async def search_chunks(
        self, query: str, knowledge_uids: list[str] | None = None, limit: int = 20
    ) -> Result[list[dict[str, Any]]]:
        return await self.search_service.search_chunks(query, knowledge_uids, limit)

    async def search_by_features(
        self, features: dict[str, Any], limit: int = 25
    ) -> Result[list[CurriculumDTO]]:
        return await self.search_service.search_by_features(features, limit)

    async def search_with_semantic_intent(
        self,
        query: str,
        intent: str | None = None,
        _context: dict[str, Any] | None = None,
        limit: int = 25,
    ) -> Result[list[CurriculumDTO]]:
        return await self.search_service.search_with_semantic_intent(query, intent, _context, limit)

    async def get_content_chunks(
        self, uid: str, chunk_type: str | None = None
    ) -> Result[list[dict[str, Any]]]:
        return await self.search_service.get_content_chunks(uid, chunk_type)

    # Graph delegations
    async def find_prerequisites(
        self,
        uid: str,
        depth: int = 3,
        _include_optional: bool = False,
        min_confidence: float = 0.7,
    ) -> Result[list[CurriculumDTO]]:
        return await self.graph.find_prerequisites(uid, depth, _include_optional, min_confidence)

    async def find_next_steps(self, uid: str, limit: int = 10) -> Result[list[CurriculumDTO]]:
        return await self.graph.find_next_steps(uid, limit)

    async def get_lesson_with_context(self, uid: str, depth: int = 2) -> Result[dict[str, Any]]:
        return await self.graph.get_lesson_with_context(uid, depth)

    async def link_prerequisite(
        self, unit_uid: str, prerequisite_uid: str, is_mandatory: bool = True
    ) -> Result[bool]:
        return await self.graph.link_prerequisite(unit_uid, prerequisite_uid, is_mandatory)

    async def link_parent_child(self, parent_uid: str, child_uid: str) -> Result[bool]:
        return await self.graph.link_parent_child(parent_uid, child_uid)

    async def get_prerequisite_chain(
        self, uid: str, user_uid: str | None = None
    ) -> Result[dict[str, Any]]:
        return await self.graph.get_prerequisite_chain(uid, user_uid)

    async def analyze_knowledge_gaps(
        self, target_uid: str, user_uid: str
    ) -> Result[dict[str, Any]]:
        return await self.graph.analyze_knowledge_gaps(target_uid, user_uid)

    async def get_learning_recommendations(
        self, user_uid: str, domain: str | None = None, limit: int = 5
    ) -> Result[list[dict[str, Any]]]:
        return await self.graph.get_learning_recommendations(user_uid, domain, limit)

    async def find_time_aware_learning_path(
        self,
        target_uid: str,
        user_time_budget: int,
        max_complexity: str = "advanced",
        min_confidence: float = 0.7,
        limit: int = 5,
    ) -> Result[list[dict[str, Any]]]:
        return await self.graph.find_time_aware_learning_path(
            target_uid, user_time_budget, max_complexity, min_confidence, limit
        )

    async def update_hub_scores(self) -> Result[None]:
        return await self.graph.update_hub_scores()

    async def get_foundational_knowledge(
        self, domain: str | None = None, min_hub_score: int = 10, limit: int = 20
    ) -> Result[list[CurriculumDTO]]:
        return await self.graph.get_foundational_knowledge(domain, min_hub_score, limit)

    # Application discovery delegations (reverse relationship queries)
    async def find_events_applying_knowledge(
        self, ku_uid: str, user_uid: str, upcoming_only: bool = True
    ) -> Result[list[str]]:
        return await self.application_discovery.find_events_applying_knowledge(
            ku_uid, user_uid, upcoming_only
        )

    async def find_habits_reinforcing_knowledge(
        self, ku_uid: str, user_uid: str, only_active: bool = True
    ) -> Result[list[str]]:
        return await self.application_discovery.find_habits_reinforcing_knowledge(
            ku_uid, user_uid, only_active
        )

    async def find_learning_steps_containing(
        self, ku_uid: str, limit: int = 10
    ) -> Result[list[str]]:
        return await self.application_discovery.find_learning_steps_containing(ku_uid, limit)

    async def find_learning_paths_teaching(self, ku_uid: str, limit: int = 10) -> Result[list[str]]:
        return await self.application_discovery.find_learning_paths_teaching(ku_uid, limit)

    async def find_tasks_applying_knowledge(
        self, ku_uid: str, user_uid: str, status_filter: str | None = None
    ) -> Result[list[str]]:
        return await self.application_discovery.find_tasks_applying_knowledge(
            ku_uid, user_uid, status_filter
        )

    async def find_goals_requiring_knowledge(
        self, ku_uid: str, user_uid: str, status_filter: str | None = None
    ) -> Result[list[str]]:
        return await self.application_discovery.find_goals_requiring_knowledge(
            ku_uid, user_uid, status_filter
        )

    async def find_choices_informed_by_knowledge(
        self, ku_uid: str, user_uid: str, pending_only: bool = False
    ) -> Result[list[str]]:
        return await self.application_discovery.find_choices_informed_by_knowledge(
            ku_uid, user_uid, pending_only
        )

    async def find_principles_embodying_knowledge(
        self, ku_uid: str, user_uid: str, only_active: bool = True
    ) -> Result[list[str]]:
        return await self.application_discovery.find_principles_embodying_knowledge(
            ku_uid, user_uid, only_active
        )

    # Context-first delegations (personalized knowledge recommendations)
    async def get_ready_to_learn_for_user(
        self,
        context: "UserContext",
        domain: str | None = None,
        limit: int = 10,
    ) -> Result[list["ContextualKnowledge"]]:
        return await self.context_service.get_ready_to_learn_for_user(context, domain, limit)

    async def get_learning_gaps_for_user(
        self,
        context: "UserContext",
        goal_uid: str | None = None,
        limit: int = 10,
    ) -> Result[list["ContextualKnowledge"]]:
        return await self.context_service.get_learning_gaps_for_user(context, goal_uid, limit)

    async def get_lessons_to_reinforce_for_user(
        self,
        context: "UserContext",
        mastery_threshold: float = 0.7,
        limit: int = 10,
    ) -> Result[list["ContextualKnowledge"]]:
        return await self.context_service.get_lessons_to_reinforce_for_user(
            context, mastery_threshold, limit
        )

    # Semantic delegations
    async def create_with_semantic_relationships(
        self, ku_data: dict[str, Any], relationships: list["SemanticTriple"]
    ) -> Result[CurriculumDTO]:
        return await self.semantic.create_with_semantic_relationships(ku_data, relationships)

    async def get_semantic_neighborhood(
        self,
        uid: str,
        depth: int = 2,
        semantic_types: list[SemanticRelationshipType] | None = None,
        min_confidence: float = 0.0,
    ) -> Result[dict[str, Any]]:
        return await self.semantic.get_semantic_neighborhood(
            uid, depth, semantic_types, min_confidence
        )

    # Adaptive curriculum delegations
    async def get_personalized_curriculum(
        self, user_uid: str, sel_category: "SELCategory", limit: int = 10
    ) -> Result[list["Lesson"]]:
        return await self.adaptive.get_personalized_curriculum(user_uid, sel_category, limit)

    async def get_sel_journey(self, user_uid: str) -> Result["LearningJourney"]:
        return await self.adaptive.get_sel_journey(user_uid)

    async def track_curriculum_completion(
        self, user_uid: str, ku_uid: str, completion_time_minutes: int = 30
    ) -> Result[None]:
        return await self.adaptive.track_curriculum_completion(
            user_uid, ku_uid, completion_time_minutes
        )

    # Organization delegations (with None guard — organization service is optional)
    async def organize(self, parent_uid: str, child_uid: str, order: int = 0) -> Result[bool]:
        if self.organization is None:
            return Result.fail(Errors.system("Organization service not available", "organize"))
        return await self.organization.organize(parent_uid, child_uid, order)

    async def unorganize(self, parent_uid: str, child_uid: str) -> Result[bool]:
        if self.organization is None:
            return Result.fail(Errors.system("Organization service not available", "unorganize"))
        return await self.organization.unorganize(parent_uid, child_uid)

    async def reorder(self, parent_uid: str, child_uid: str, new_order: int) -> Result[bool]:
        if self.organization is None:
            return Result.fail(Errors.system("Organization service not available", "reorder"))
        return await self.organization.reorder(parent_uid, child_uid, new_order)

    async def is_organizer(self, ku_uid: str) -> Result[bool]:
        if self.organization is None:
            return Result.fail(Errors.system("Organization service not available", "is_organizer"))
        return await self.organization.is_organizer(ku_uid)

    async def get_organization_view(
        self, ku_uid: str, max_depth: int = 3
    ) -> Result["OrganizationView"]:
        if self.organization is None:
            return Result.fail(
                Errors.system("Organization service not available", "get_organization_view")
            )
        return await self.organization.get_organization_view(ku_uid, max_depth)

    async def get_navigation(self, ku_uid: str) -> Result["KuNavigation"]:
        if self.organization is None:
            return Result.fail(
                Errors.system("Organization service not available", "get_navigation")
            )
        return await self.organization.get_navigation(ku_uid)

    async def find_organizers(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        if self.organization is None:
            return Result.fail(
                Errors.system("Organization service not available", "find_organizers")
            )
        return await self.organization.find_organizers(ku_uid)

    async def list_root_organizers(self, limit: int = 50) -> Result[list[dict[str, Any]]]:
        if self.organization is None:
            return Result.fail(
                Errors.system("Organization service not available", "list_root_organizers")
            )
        return await self.organization.list_root_organizers(limit)

    async def get_organized_children(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        if self.organization is None:
            return Result.fail(
                Errors.system("Organization service not available", "get_organized_children")
            )
        return await self.organization.get_organized_children(ku_uid)

    def __init__(
        self,
        repo: "LessonOperations",
        content_repo: "Any | None" = None,  # Was ContentOperations (deleted January 2026)
        neo4j_adapter: "Any | None" = None,
        ku_backend: "Any | None" = None,
        chunking_service: "Any | None" = None,
        graph_intelligence_service: "Any | None" = None,
        query_builder: "QueryBuilderOperations | None" = None,
        event_bus: "EventBusOperations | None" = None,
        _executor: "Any | None" = None,  # Placeholder - LessonOrganizationService now uses backend
        user_service: "Any | None" = None,
        ai_service: LessonAIService | None = None,
        vector_search_service: "Any | None" = None,
        embeddings_service: "Any | None" = None,
    ) -> None:
        """
        Initialize facade with all dependencies via factory.

        FAIL-FAST ARCHITECTURE (per CLAUDE.md):
        The repo (backend) and graph_intelligence_service are REQUIRED.
        Services run at full capacity or fail immediately at startup.

        **January 2026 - Factory Pattern (Architecture Consistency Review):**
        Uses create_lesson_sub_services() factory for consistent initialization.
        Factory handles circular dependency: intelligence created before core.

        Args:
            repo: LessonOperations backend - REQUIRED
            content_repo: Content storage backend (optional)
            neo4j_adapter: Neo4j adapter for sub-service graph operations (optional)
            ku_backend: KuBackend for substance metric operations (REQUIRED)
            chunking_service: Chunking service for RAG (optional)
            graph_intelligence_service: GraphIntelligenceService - REQUIRED for cross-domain queries
            query_builder: QueryBuilder service for optimized queries (optional)
            event_bus: Event bus for publishing domain events (optional)
            driver: Neo4j async driver for event-driven operations (optional)
            user_service: UserService for UserContext access (January 2026 - KU-Activity Integration)
            ai_service: Optional LessonAIService for AI features (ADR-030 separation)
            vector_search_service: Optional Neo4jVectorSearchService for semantic search (January 2026 - GenAI)
            embeddings_service: Optional HuggingFaceEmbeddingsService for embedding generation (January 2026 - GenAI)
        """
        # FAIL-FAST: Backend is REQUIRED
        if not repo:
            raise ValueError(
                "LessonService backend (repo) is REQUIRED. "
                "SKUEL follows fail-fast architecture - all required dependencies "
                "must be provided at initialization."
            )
        if not graph_intelligence_service:
            raise ValueError(
                "LessonService graph_intelligence_service is REQUIRED. "
                "SKUEL follows fail-fast architecture - graph intelligence enables "
                "cross-domain queries for curriculum domains."
            )

        # Create all sub-services via factory (January 2026 - Architecture Consistency)
        from core.services.curriculum_domain_config import create_lesson_sub_services

        subs = create_lesson_sub_services(
            backend=repo,
            content_repo=content_repo,
            neo4j_adapter=neo4j_adapter,
            chunking_service=chunking_service,
            graph_intelligence_service=graph_intelligence_service,
            query_builder=query_builder,
            event_bus=event_bus,
            _driver=_executor,  # Dead param in factory (no sub-service uses it)
            user_service=user_service,
            vector_search_service=vector_search_service,  # NEW: January 2026 GenAI
            embeddings_service=embeddings_service,  # NEW: January 2026 GenAI
        )

        # Assign sub-services from factory result
        self.core = subs.core
        self.search_service = subs.search
        self.graph = subs.graph
        self.semantic = subs.semantic
        self.practice = subs.practice
        self.mastery = subs.mastery
        self.relationships = subs.relationships
        self.intelligence = subs.intelligence
        self.adaptive = subs.adaptive
        self.application_discovery = subs.application_discovery
        self.context_service = subs.context_service

        # Expose search attribute for convenience (test compatibility)
        # Note: We use search_service internally to avoid shadowing
        self.search = self.search_service

        # Store dependencies for backward compatibility
        self.repo = repo
        self.content_repo = content_repo
        self.chunking_service = chunking_service
        self.graph_intel = graph_intelligence_service
        self.ku_backend = ku_backend
        self.user_service = user_service

        # Organization service (ORGANIZES relationships — any Ku can organize others)
        from core.services.lesson.lesson_organization_service import LessonOrganizationService

        self.organization = LessonOrganizationService(ku_service=self, backend=repo)  # type: ignore[arg-type]

        # Optional AI service (ADR-030: AI features are optional)
        self.ai: LessonAIService | None = ai_service

        self.logger = get_logger("skuel.services.lesson")
        self.logger.debug(
            "LessonService initialized via factory (11 sub-services, circular dependency handled)"
        )

    # ========================================================================
    # CORE CRUD OPERATIONS - Delegated to LessonCoreService
    # ========================================================================
    # Note: Simple delegations (create, get, update, delete, publish, archive,
    # get_user_mastery, get_chunks, analyze_content) delegated via explicit methods below.

    async def get_lessons_batch(self, uids: list[str]) -> Result[list[Any]]:
        """
        Get multiple lessons in one batched query.

        Critical for GraphQL DataLoader batching to prevent N+1 queries.

        Args:
            uids: List of lesson UIDs to fetch

        Returns:
            Result containing list of CurriculumDTOs (None for missing UIDs)
            Entities returned in same order as input UIDs
        """
        if not self.repo:
            return Result.fail(
                Errors.system("Lesson repository not available", operation="get_lessons_batch")
            )

        # Use UniversalNeo4jBackend's get_many() method
        return await self.repo.get_many(uids)

    async def list_user_knowledge(self, user_uid: str) -> Result[list]:
        """
        Get all knowledge units available for user's semantic search.

        This method supports Askesis RAG semantic search by returning all knowledge
        units that can be queried. Currently returns ALL knowledge units (global
        knowledge base approach), as Knowledge Units in SKUEL are not user-scoped.

        Future Enhancement: Could scope to user's learning path via:
            MATCH (user:User {uid: $user_uid})-[:LEARNING]->(ku:Entity)

        Args:
            user_uid: User identifier (currently unused, reserved for future scoping)

        Returns:
            Result containing list of Ku domain models

        Implementation Notes:
            - Knowledge Units are global content, not user-specific
            - User scoping happens via LEARNING relationships, not ownership
            - Returns domain models (Ku), not DTOs
            - Used by askesis_service._find_similar_knowledge() for semantic search

        Performance:
            - Fetches up to 10,000 knowledge units (high limit for global access)
            - Results are NOT cached (semantic search caches embeddings instead)
            - Consider adding pagination if knowledge base exceeds 10k units
        """
        if not self.repo:
            return Result.fail(
                Errors.system("Knowledge repository not available", operation="list_user_knowledge")
            )

        # Get all knowledge units from backend (global knowledge base)
        # High limit since knowledge is global, not user-scoped
        result = await self.repo.list(QueryLimit.BULK)

        if result.is_error:
            self.logger.error(f"Failed to list knowledge units: {result.error}")
            return Result.fail(result)

        # Unpack tuple: backend.list() returns (kus, total_count)
        kus_data, _ = result.value

        # Backend returns Ku instances (entity_class=Ku), not CurriculumDTOs
        kus = list(kus_data)

        self.logger.info(
            f"Retrieved {len(kus)} knowledge units for semantic search (user: {user_uid})"
        )

        return Result.ok(kus)

    # ========================================================================
    # SEARCH OPERATIONS - Delegated to LessonSearchService
    # ========================================================================
    # Note: Simple delegations (search_by_title_template, search_with_user_context,
    # find_similar_content, search_by_tags, search_by_facets, search_chunks_with_facets,
    # search_chunks, search_by_features, search_with_semantic_intent, get_content_chunks)
    # delegated via explicit methods below.

    # ========================================================================
    # GRAPH OPERATIONS - Delegated to LessonGraphService
    # ========================================================================
    # Note: Simple delegations (find_prerequisites, find_next_steps, get_lesson_with_context,
    # link_prerequisite, link_parent_child, get_prerequisite_chain, analyze_knowledge_gaps,
    # get_learning_recommendations, find_time_aware_learning_path, update_hub_scores,
    # get_foundational_knowledge) delegated via explicit methods below.

    async def get_prerequisites(self, uid: str) -> Result[list[CurriculumDTO]]:
        """
        Get prerequisite knowledge units (GraphQL-friendly alias).

        Wrapper for find_prerequisites() with sensible defaults for GraphQL resolvers.
        Returns Result[list[CurriculumDTO]].
        """
        return await self.graph.find_prerequisites(uid=uid, depth=GraphDepth.DEFAULT)

    async def get_enables(self, uid: str) -> Result[list[CurriculumDTO]]:
        """
        Get knowledge units enabled by this KU (GraphQL-friendly method).

        Returns Result[list[CurriculumDTO]] - knowledge units that become accessible
        after mastering this one.

        Implementation: Uses graph.find_next_steps (KUs that require this one).
        """
        # find_next_steps returns KUs that have this KU as a prerequisite
        # which is semantically the same as what this KU enables
        return await self.graph.find_next_steps(uid=uid)

    # ========================================================================
    # SEMANTIC OPERATIONS - Delegated to LessonSemanticService
    # ========================================================================
    # Note: Simple delegations (create_with_semantic_relationships, get_semantic_neighborhood)
    # delegated via explicit methods below.

    async def create_lesson_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: "SemanticRelationshipType",
        confidence: float = 0.9,
        strength: float = 1.0,
        notes: str | None = None,
    ) -> Result[bool]:
        """
        Create a semantic relationship between two lessons.

        Args:
            source_uid: Source lesson UID (subject)
            target_uid: Target lesson UID (object)
            relationship_type: SemanticRelationshipType enum value
            confidence: Confidence score (0.0-1.0)
            strength: Strength of relationship (0.0-1.0)
            notes: Optional notes about the relationship

        Returns:
            Result indicating success
        """
        return await self.semantic.add_semantic_relationship(
            subject_uid=source_uid,
            predicate=relationship_type,
            object_uid=target_uid,
            confidence=confidence,
            strength=strength,
            notes=notes,
        )

    async def get_lesson_relationships(
        self, uid: str, relationship_type: str | None = None
    ) -> Result[list[dict[str, Any]]]:
        """
        Get relationships for an lesson.

        Args:
            uid: Knowledge unit UID
            relationship_type: Filter by relationship type (e.g., "learn:requires_theoretical_understanding")

        Returns:
            Result with list of relationships
        """
        if not relationship_type:
            return Result.fail(
                Errors.validation(
                    message="relationship_type is required (e.g., 'learn:requires_theoretical_understanding')",
                    field="relationship_type",
                )
            )

        # Convert string to SemanticRelationshipType enum
        try:
            predicate = SemanticRelationshipType(relationship_type)
        except ValueError:
            return Result.fail(
                Errors.validation(
                    message=f"Invalid relationship_type: {relationship_type}",
                    field="relationship_type",
                )
            )

        return await self.semantic.get_relationships_by_type(uid=uid, predicate=predicate)

    async def get_lesson_dependencies(
        self, uid: str, limit: int = 10
    ) -> Result[list[CurriculumDTO]]:
        """
        Get lessons that depend on this one.

        Args:
            uid: Knowledge unit UID
            limit: Maximum results to return

        Returns:
            Result with list of dependent knowledge units
        """
        return await self.graph.find_next_steps(uid=uid, limit=limit)

    # ========================================================================
    # CONTENT AND TAG MANAGEMENT
    # ========================================================================

    async def update_lesson_content(
        self, uid: str, content: str, title: str | None = None
    ) -> Result[CurriculumDTO]:
        """
        Update an lesson's content.

        Args:
            uid: Knowledge unit UID
            content: New content text
            title: Optional new title

        Returns:
            Result with updated knowledge unit
        """
        updates: dict[str, Any] = {"content": content}
        if title:
            updates["title"] = title
        return await self.core.update(uid, updates)

    async def add_lesson_tags(self, uid: str, tags: list[str]) -> Result[CurriculumDTO]:
        """
        Add tags to an lesson.

        Args:
            uid: Knowledge unit UID
            tags: Tags to add

        Returns:
            Result with updated knowledge unit
        """
        # First get current tags
        ku_result = await self.core.get(uid)
        if ku_result.is_error:
            return Result.fail(ku_result)

        ku = ku_result.value
        if not ku:
            return Result.fail(Errors.not_found(resource="Ku", identifier=uid))

        current_tags = list(ku.tags or [])
        # Add new tags without duplicates
        updated_tags = list(set(current_tags + tags))

        return await self.core.update(uid, {"tags": updated_tags})

    async def remove_lesson_tags(self, uid: str, tags: list[str]) -> Result[CurriculumDTO]:
        """
        Remove tags from an lesson.

        Args:
            uid: Knowledge unit UID
            tags: Tags to remove

        Returns:
            Result with updated knowledge unit
        """
        # First get current tags
        ku_result = await self.core.get(uid)
        if ku_result.is_error:
            return Result.fail(ku_result)

        ku = ku_result.value
        if not ku:
            return Result.fail(Errors.not_found(resource="Ku", identifier=uid))

        current_tags = list(ku.tags or [])
        # Remove specified tags
        updated_tags = [t for t in current_tags if t not in tags]

        return await self.core.update(uid, {"tags": updated_tags})

    # ========================================================================
    # SEARCH AND FILTERING
    # ========================================================================

    async def search_lessons(self, query: str, limit: int = 50) -> Result[list[CurriculumDTO]]:
        """
        Search lessons by text query.

        Args:
            query: Search query string
            limit: Maximum results to return

        Returns:
            Result with list of matching knowledge units
        """
        return await self.search_service.search_by_title_template(query=query, limit=limit)

    async def get_lessons_by_domain(self, domain: str, limit: int = 100) -> Result[list[Any]]:
        """
        Get lessons by domain.

        Args:
            domain: Domain name (e.g., "TECH", "BUSINESS")
            limit: Maximum results

        Returns:
            Result with list of knowledge units in the domain
        """
        if not self.repo:
            return Result.fail(
                Errors.system(
                    message="Lesson repository not available",
                    operation="get_lessons_by_domain",
                )
            )

        # Use backend's find_by with domain filter
        return await self.repo.find_by(domain=domain, limit=limit)

    # ========================================================================
    # TEMPLATE & UTILITY OPERATIONS
    # ========================================================================
    # Note: get_with_template delegates to core.get.

    @with_error_handling("get_query_metrics", error_type="system")
    async def get_query_metrics(self) -> Result[dict[str, Any]]:
        """
        Get query performance metrics for all knowledge operations.

        Returns comprehensive metrics including:
        - Per-operation call counts and timings
        - Statistical distribution (min, max, avg, p95, p99)
        - Error rates and counts
        - Overall system statistics

        Returns:
            Result containing dictionary with:
            - uptime_seconds: Time since metrics started
            - total_operations: Number of unique operations tracked
            - total_calls: Total calls across all operations
            - total_errors: Total errors across all operations
            - overall_error_rate: Percentage of calls that errored
            - calls_per_second: Request throughput
            - slowest_operations: Top 5 slowest operations
            - operations: Detailed per-operation metrics
        """
        metrics = get_metrics_summary()
        return Result.ok(metrics)

    # Note: get_content_chunks delegated via explicit methods below.

    # ========================================================================
    # SUBSTANCE TRACKING EVENT LISTENERS (October 17, 2025)
    # "Applied knowledge, not pure theory" - Track real-world application
    # ========================================================================

    @safe_event_handler("knowledge.applied_in_task")
    async def handle_knowledge_applied_in_task(self, event) -> None:
        """
        Handle KnowledgeAppliedInTask event.

        Increments: times_applied_in_tasks
        Updates: last_applied_date
        Invalidates: substance cache

        Args:
            event: KnowledgeAppliedInTask with knowledge_uid, task_uid, occurred_at
        """
        await self.increment_substance_metric(
            ku_uid=event.knowledge_uid,
            metric="times_applied_in_tasks",
            timestamp_field="last_applied_date",
            timestamp=event.occurred_at,
        )
        self.logger.debug(
            f"Substance updated: {event.knowledge_uid} applied in task {event.task_uid}"
        )

    @safe_event_handler("knowledge.practiced_in_event")
    async def handle_knowledge_practiced_in_event(self, event) -> None:
        """
        Handle KnowledgePracticedInEvent event.

        Increments: times_practiced_in_events
        Updates: last_practiced_date
        Invalidates: substance cache

        Args:
            event: KnowledgePracticedInEvent with knowledge_uid, event_uid, occurred_at
        """
        await self.increment_substance_metric(
            ku_uid=event.knowledge_uid,
            metric="times_practiced_in_events",
            timestamp_field="last_practiced_date",
            timestamp=event.occurred_at,
        )
        self.logger.debug(
            f"Substance updated: {event.knowledge_uid} practiced in event {event.event_uid}"
        )

    @safe_event_handler("knowledge.built_into_habit")
    async def handle_knowledge_built_into_habit(self, event) -> None:
        """
        Handle KnowledgeBuiltIntoHabit event.

        Increments: times_built_into_habits
        Updates: last_built_into_habit_date
        Invalidates: substance cache

        HIGHEST IMPACT EVENT (0.10 weight) - lifestyle integration

        Args:
            event: KnowledgeBuiltIntoHabit with knowledge_uid, habit_uid, occurred_at
        """
        await self.increment_substance_metric(
            ku_uid=event.knowledge_uid,
            metric="times_built_into_habits",
            timestamp_field="last_built_into_habit_date",
            timestamp=event.occurred_at,
        )
        # High-impact event - log at info level
        self.logger.info(
            f"Knowledge {event.knowledge_uid} built into habit {event.habit_uid} "
            f"(substance +0.10, lifestyle integration)"
        )

    @safe_event_handler("knowledge.informed_choice")
    async def handle_knowledge_informed_choice(self, event) -> None:
        """
        Handle KnowledgeInformedChoice event.

        Increments: choices_informed_count
        Updates: last_choice_informed_date
        Invalidates: substance cache

        HIGH IMPACT EVENT (0.07 weight) - decision-making

        Args:
            event: KnowledgeInformedChoice with knowledge_uid, choice_uid, occurred_at
        """
        await self.increment_substance_metric(
            ku_uid=event.knowledge_uid,
            metric="choices_informed_count",
            timestamp_field="last_choice_informed_date",
            timestamp=event.occurred_at,
        )
        self.logger.info(
            f"Knowledge {event.knowledge_uid} informed choice {event.choice_uid} "
            f"(substance +0.07, informed decision-making)"
        )

    # ========================================================================
    # BATCH KNOWLEDGE EVENT HANDLERS (Performance Optimization)
    # ========================================================================

    @safe_event_handler("knowledge.bulk_applied_in_task")
    async def handle_knowledge_bulk_applied_in_task(self, event) -> None:
        """
        Handle KnowledgeBulkAppliedInTask event - batch version.

        More efficient than N individual handle_knowledge_applied_in_task calls.

        Args:
            event: KnowledgeBulkAppliedInTask with knowledge_uids tuple
        """
        await self.batch_increment_substance_metric(
            ku_uids=event.knowledge_uids,
            metric="times_applied_in_tasks",
            timestamp_field="last_applied_date",
            timestamp=event.occurred_at,
        )
        self.logger.debug(
            f"Batch substance updated: {len(event.knowledge_uids)} KUs applied in task {event.task_uid}"
        )

    @safe_event_handler("knowledge.bulk_built_into_habit")
    async def handle_knowledge_bulk_built_into_habit(self, event) -> None:
        """
        Handle KnowledgeBulkBuiltIntoHabit event - batch version.

        HIGHEST IMPACT EVENT (0.10 weight per KU) - lifestyle integration.

        Args:
            event: KnowledgeBulkBuiltIntoHabit with knowledge_uids tuple
        """
        await self.batch_increment_substance_metric(
            ku_uids=event.knowledge_uids,
            metric="times_built_into_habits",
            timestamp_field="last_built_into_habit_date",
            timestamp=event.occurred_at,
        )
        self.logger.info(
            f"Batch: {len(event.knowledge_uids)} KUs built into habit {event.habit_uid} "
            f"(substance +0.10 each, lifestyle integration)"
        )

    @safe_event_handler("knowledge.bulk_informed_choice")
    async def handle_knowledge_bulk_informed_choice(self, event) -> None:
        """
        Handle KnowledgeBulkInformedChoice event - batch version.

        HIGH IMPACT EVENT (0.07 weight per KU) - decision-making.

        Args:
            event: KnowledgeBulkInformedChoice with knowledge_uids tuple
        """
        await self.batch_increment_substance_metric(
            ku_uids=event.knowledge_uids,
            metric="choices_informed_count",
            timestamp_field="last_choice_informed_date",
            timestamp=event.occurred_at,
        )
        self.logger.info(
            f"Batch: {len(event.knowledge_uids)} KUs informed choice {event.choice_uid} "
            f"(substance +0.07 each, informed decision-making)"
        )

    async def batch_increment_substance_metric(
        self, ku_uids: tuple[str, ...], metric: str, timestamp_field: str, timestamp
    ) -> None:
        """
        Atomically increment a substance metric for multiple KUs in one query.

        O(1) database round-trip vs O(n) for individual increments.

        Args:
            ku_uids: Tuple of knowledge unit UIDs
            metric: Field name to increment
            timestamp_field: Timestamp field to update
            timestamp: DateTime value for timestamp field

        Raises:
            Exception: Propagated to caller (typically @safe_event_handler decorator)
        """
        if not ku_uids:
            return
        if metric not in _VALID_SUBSTANCE_METRICS:
            self.logger.error(f"Invalid substance metric rejected: {metric}")
            return
        if timestamp_field not in _VALID_SUBSTANCE_TIMESTAMP_FIELDS:
            self.logger.error(f"Invalid substance timestamp field rejected: {timestamp_field}")
            return

        if not self.ku_backend:
            self.logger.error("ku_backend not wired — cannot batch increment substance metrics")
            return

        timestamp_str = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)

        result = await self.ku_backend.batch_increment_substance(
            ku_uids=list(ku_uids),
            metric=metric,
            timestamp_field=timestamp_field,
            timestamp_str=timestamp_str,
        )
        if result.is_error:
            self.logger.error(f"Failed batch substance increment: {result.error}")
            return
        self.logger.debug(f"Batch substance metric updated: {result.value} KUs.{metric}")

    async def increment_substance_metric(
        self, ku_uid: str, metric: str, timestamp_field: str, timestamp
    ) -> None:
        """
        Atomically increment a substance metric in Neo4j.

        This is a CRITICAL operation - uses atomic Cypher SET to avoid race conditions.

        Args:
            ku_uid: Knowledge unit UID
            metric: Field name to increment (e.g., 'times_applied_in_tasks')
            timestamp_field: Timestamp field to update (e.g., 'last_applied_date')
            timestamp: DateTime value for timestamp field

        Behavior:
            - Increments count atomically
            - Updates timestamp
            - Invalidates substance cache (force recalculation)
            - Creates field if doesn't exist (COALESCE)

        Raises:
            Exception: Propagated to caller (typically @safe_event_handler decorator)
        """
        if metric not in _VALID_SUBSTANCE_METRICS:
            self.logger.error(f"Invalid substance metric rejected: {metric}")
            return
        if timestamp_field not in _VALID_SUBSTANCE_TIMESTAMP_FIELDS:
            self.logger.error(f"Invalid substance timestamp field rejected: {timestamp_field}")
            return

        if not self.ku_backend:
            self.logger.error("ku_backend not wired — cannot increment substance metric")
            return

        # Convert datetime to ISO string if needed
        timestamp_str = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)

        result = await self.ku_backend.increment_substance(
            ku_uid=ku_uid,
            metric=metric,
            timestamp_field=timestamp_field,
            timestamp_str=timestamp_str,
        )
        if result.is_error:
            self.logger.error(f"Failed substance increment for {ku_uid}: {result.error}")
            return
        self.logger.debug(f"Substance metric updated: {ku_uid}.{metric} = {result.value}")

    # ========================================================================
    # ADDITIONAL API METHODS - Required by knowledge_api.py
    # ========================================================================

    async def get_lesson_prerequisites(self, uid: str) -> Result[list[CurriculumDTO]]:
        """
        Get prerequisite lessons (API-compatible wrapper).

        Args:
            uid: Knowledge unit UID

        Returns:
            Result with list of prerequisite lessons
        """
        return await self.get_prerequisites(uid)

    async def find_related_lessons(
        self, uid: str, similarity_threshold: float = 0.7, limit: int = 10
    ) -> Result[list[CurriculumDTO]]:
        """
        Find lessons related to the given one.

        Args:
            uid: Knowledge unit UID
            similarity_threshold: Minimum similarity score
            limit: Maximum results

        Returns:
            Result with list of related knowledge units
        """
        # Get semantic neighborhood which includes related knowledge
        neighborhood_result = await self.semantic.get_semantic_neighborhood(
            uid=uid, depth=2, min_confidence=similarity_threshold
        )

        if neighborhood_result.is_error:
            return Result.fail(neighborhood_result)

        # Extract related UIDs from neighborhood
        neighborhood = neighborhood_result.value
        related_uids = []

        if isinstance(neighborhood, dict):
            # Extract UIDs from neighborhood structure
            for nodes in neighborhood.values():
                if isinstance(nodes, list):
                    for node in nodes[:limit]:
                        if isinstance(node, dict) and "uid" in node:
                            related_uids.append(node["uid"])
                        elif isinstance(node, HasUID):
                            related_uids.append(node.uid)

        # Fetch full CurriculumDTO objects
        kus = []
        for ku_uid in related_uids[:limit]:
            ku_result = await self.core.get(ku_uid)
            if ku_result.is_ok and ku_result.value:
                kus.append(ku_result.value)

        return Result.ok(kus)

    async def get_lesson_recommendations(
        self,
        uid: str,
        user_uid: str | None = None,
        recommendation_type: str = "learning",
    ) -> Result[list[CurriculumDTO]]:
        """
        Get personalized lesson recommendations.

        Args:
            uid: Starting knowledge unit UID
            user_uid: Optional user for personalization
            recommendation_type: Type of recommendation ("learning", "related", "next")

        Returns:
            Result with list of recommended knowledge units
        """
        if recommendation_type == "next":
            # Get next steps in learning path
            return await self.graph.find_next_steps(uid=uid, limit=5)
        elif recommendation_type == "related":
            # Get related knowledge
            return await self.find_related_lessons(uid, limit=10)
        else:
            # Default: learning recommendations starting from the given uid
            # Note: get_learning_recommendations is user-global, so for uid-specific
            # recommendations we use find_next_steps which traverses from the starting point
            return await self.graph.find_next_steps(uid=uid, limit=10)

    async def list_lesson_domains(self) -> Result[list[str]]:
        """
        List all lesson domains.

        Returns:
            Result with list of unique domain names
        """
        from core.models.enums import Domain

        # Return all domain enum values
        domains = [d.value for d in Domain]
        return Result.ok(domains)

    async def list_lesson_categories(self) -> Result[list[str]]:
        """
        List all lesson categories.

        Returns:
            Result with list of unique categories
        """
        if not self.repo:
            return Result.fail(
                Errors.system(
                    message="Lesson repository not available",
                    operation="list_lesson_categories",
                )
            )

        # Get all knowledge units and extract unique categories
        result = await self.repo.list(QueryLimit.COMPREHENSIVE)

        if result.is_error:
            return Result.fail(result)

        kus, _ = result.value
        categories = set()
        for ku in kus:
            sel_category = getattr(ku, "sel_category", None)
            if sel_category:
                categories.add(sel_category)

        return Result.ok(sorted(list(categories)))

    async def list_lesson_tags(self, min_usage: int = 1) -> Result[list[dict[str, Any]]]:
        """
        List all lesson tags with usage counts.

        Args:
            min_usage: Minimum usage count to include tag

        Returns:
            Result with list of tag dictionaries (tag, count)
        """
        if not self.repo:
            return Result.fail(
                Errors.system(
                    message="Lesson repository not available",
                    operation="list_lesson_tags",
                )
            )

        # Get all knowledge units and count tag usage
        result = await self.repo.list(QueryLimit.COMPREHENSIVE)

        if result.is_error:
            return Result.fail(result)

        kus, _ = result.value
        tag_counts: dict[str, int] = {}
        for ku in kus:
            if ku.tags:
                for tag in ku.tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Filter by min_usage and format (sorted descending by count)
        tags_list = [
            {"tag": tag, "count": count}
            for tag, count in sorted(tag_counts.items(), key=get_second_item, reverse=True)
            if count >= min_usage
        ]

        return Result.ok(tags_list)

    async def get_lesson_stats(self, uid: str) -> Result[dict[str, Any]]:
        """
        Get statistics for an lesson.

        Args:
            uid: Knowledge unit UID

        Returns:
            Result with statistics dictionary
        """
        # Get the knowledge unit
        ku_result = await self.core.get(uid)
        if ku_result.is_error:
            return Result.fail(ku_result)

        ku = ku_result.value
        if not ku:
            return Result.fail(Errors.not_found(resource="Ku", identifier=uid))

        # Get prerequisites count
        prereqs_result = await self.get_prerequisites(uid)
        prereq_count = len(prereqs_result.value) if prereqs_result.is_ok else 0

        # Get dependents count
        deps_result = await self.get_lesson_dependencies(uid)
        deps_count = len(deps_result.value) if deps_result.is_ok else 0

        stats = {
            "uid": uid,
            "title": ku.title,
            "domain": ku.domain.value if ku.domain else None,
            "word_count": ku.word_count,
            "tag_count": len(ku.tags or []),
            "prerequisite_count": prereq_count,
            "dependent_count": deps_count,
            "created_at": ku.created_at.isoformat() if ku.created_at else None,
            "updated_at": ku.updated_at.isoformat() if ku.updated_at else None,
        }

        return Result.ok(stats)

    # ========================================================================
    # USER CONTEXT OPERATIONS - KU-Activity Integration (January 2026)
    # ========================================================================

    async def get_user_lesson_context(
        self, ku_uid: str, user_context: "UserContext"
    ) -> Result[dict[str, Any]]:
        """
        Get personalized lesson context showing how a user applies this knowledge.

        Calculates per-user substance score based on their activity domains
        (tasks, habits, events, journals, choices) that reference this KU.

        Args:
            ku_uid: Knowledge Unit identifier
            user_context: UserContext with user's activity data

        Returns:
            Result with personalized context including:
            - user_substance_score: 0.0-1.0 (how much user has applied knowledge)
            - global_substance_score: 0.0-1.0 (how much all users have applied)
            - breakdown: counts per activity type with entity UIDs
            - mastery_level: user's mastery of this KU
            - recommendations: personalized next steps
            - status_message: human-readable status

        Example response:
            {
                "ku_uid": "ku.python-basics",
                "user_substance_score": 0.45,
                "breakdown": {
                    "tasks": {"count": 3, "uids": [...], "score": 0.15},
                    "habits": {"count": 1, "uids": [...], "score": 0.10},
                    ...
                },
                "recommendations": [
                    {"type": "journal", "message": "Reflect on...", "impact": "+0.07"}
                ]
            }
        """
        return await self.intelligence.calculate_user_substance(ku_uid, user_context)

    # =========================================================================
    # KU COMPOSITION (Lesson → atomic Ku via USES_KU)
    # =========================================================================

    async def link_to_ku(self, lesson_uid: str, ku_uid: str) -> Result[bool]:
        """Link this Lesson to an atomic Ku via USES_KU."""
        return await self.core.backend.link_to_ku(lesson_uid, ku_uid)  # type: ignore[attr-defined]

    async def get_used_kus(self, lesson_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all atomic Kus used by this Lesson."""
        return await self.core.backend.get_used_kus(lesson_uid)  # type: ignore[attr-defined]

    # ========================================================================
    # QUERY LAYER (FilteredContextProvider)
    # ========================================================================

    async def get_filtered_context(
        self,
        user_uid: str,
        status_filter: str = "all",
        sort_by: str = "title",
    ) -> Result[ListContext]:
        """Get filtered and sorted lessons with pre-filter stats."""

        async def fetch_all() -> Result[list[Any]]:
            result = await self.core.list(limit=500)
            if result.is_error:
                return Result.fail(result)
            entities, _ = result.value
            return Result.ok(list(entities))

        def apply_filters(all_lessons: list[Any]) -> list[Any]:
            return apply_entity_filter(all_lessons, status_filter, _LESSON_FILTER_CONFIG)

        return await build_filtered_context(
            fetch_all=fetch_all,
            compute_stats=_compute_lesson_stats,
            apply_filters=apply_filters,
            apply_sort=_apply_lesson_sort,
            sort_by=sort_by,
        )
