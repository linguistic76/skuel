"""
PathStep Service - Facade
==========================

THE single owner for all path step management in SKUEL.
Absorbs all former LessonService capabilities (Phase 3 merge).

Delegates to specialized sub-services:
- PsCoreService: CRUD operations + persistence (extends BaseService)
- PsSearchService: Search and discovery
- PsGraphService: Graph navigation and relationships
- PsSemanticService: Semantic relationship management
- PsPracticeService: Event-driven practice tracking
- PsMasteryService: Pedagogical tracking (VIEWED->IN_PROGRESS->MASTERED)
- PsIntelligenceService: Intelligence and analytics
- PsAdaptiveService: Personalized curriculum
- PsApplicationDiscoveryService: Reverse relationship queries
- PsContextService: Context-first knowledge recommendations
- PsOrganizationService: ORGANIZES relationships
- UnifiedRelationshipService: All relationship operations
- PsProgressService: KU completion progress
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.constants import GraphDepth, QueryLimit
from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.models.curriculum_dto import CurriculumDTO
from core.models.type_hints import UserUID
from core.ports.base_protocols import HasUID
from core.ports.query_types import ListContext, OrganizerResult, RootOrganizerResult
from core.services.filtered_context import build_filtered_context
from core.services.ps.ps_ai_service import PsAIService
from core.services.ps.ps_progress_service import PsProgressService
from core.utils.decorators import with_error_handling
from core.utils.error_boundary import safe_event_handler
from core.utils.list_helpers import (
    FilterConfig,
    SortConfig,
    apply_entity_filter,
    apply_entity_sort,
    get_sequence_attr,
)
from core.utils.logging import get_logger
from core.utils.metrics import get_metrics_summary
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_created_at_attr, get_second_item, get_title_lower

if TYPE_CHECKING:
    import builtins

    from core.infrastructure.relationships.semantic_relationships import SemanticTriple
    from core.models.context_types import ContextualKnowledge
    from core.models.enums.learning_enums import SELCategory
    from core.models.pathways.learning_progress import LearningJourney
    from core.models.pathways.path_step import PathStep
    from core.services.ps.ps_intelligence_service import PsIntelligenceService
    from core.services.ps.ps_organization_service import StepNavigation, StepOrganizationView
    from core.services.user import UserContext

logger = get_logger(__name__)

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


def _compute_ps_stats(all_steps: list[Any]) -> dict[str, int | float]:
    """Compute pre-filter stats from the full path step set."""
    from core.models.enums import EntityStatus
    from core.models.enums.learning_enums import KnowledgeStatus

    published = sum(
        bool(getattr(s, "status", None) == KnowledgeStatus.PUBLISHED) for s in all_steps
    )
    return {
        "total": len(all_steps),
        "active": published,
        "published": published,
        "draft": sum(bool(getattr(s, "status", None) == EntityStatus.DRAFT) for s in all_steps),
    }


def _is_ps_published(step: Any) -> bool:
    from core.models.enums.learning_enums import KnowledgeStatus

    return getattr(step, "status", None) == KnowledgeStatus.PUBLISHED


def _is_ps_draft(step: Any) -> bool:
    from core.models.enums import EntityStatus

    return getattr(step, "status", None) == EntityStatus.DRAFT


def _is_ps_archived(step: Any) -> bool:
    from core.models.enums import EntityStatus

    return getattr(step, "status", None) == EntityStatus.ARCHIVED


_PS_FILTER_CONFIG: FilterConfig = {
    "published": _is_ps_published,
    "draft": _is_ps_draft,
    "archived": _is_ps_archived,
}

_PS_SORT_CONFIG: SortConfig = {
    "title": (get_title_lower, False),
    "sequence": (get_sequence_attr, False),
    "created_at": (get_created_at_attr, True),
}


def _apply_ps_sort(steps: list[Any], sort_by: str) -> list[Any]:
    """Sort path steps using declarative config."""
    return apply_entity_sort(steps, sort_by, _PS_SORT_CONFIG, "title")


class PsService:
    """Facade for path step management (merged Lesson capabilities).

    Coordinates 12 sub-services (via create_ps_sub_services factory):
    - Core: CRUD operations + persistence
    - Search: Discovery operations
    - Graph: Graph navigation and relationships
    - Semantic: Semantic relationship management
    - Practice: Event-driven practice tracking
    - Mastery: Pedagogical tracking
    - Relationships: Step-path associations
    - Intelligence: Readiness assessment, practice analysis
    - Adaptive: Personalized curriculum
    - ApplicationDiscovery: Reverse relationship queries
    - ContextService: Context-first knowledge recommendations
    - Organization: ORGANIZES relationships
    """

    def __init__(
        self,
        backend: Any = None,
        executor: Any = None,
        graph_intel: Any = None,
        event_bus: Any = None,
        ai_service: PsAIService | None = None,
        # Merged lesson dependencies
        content_repo: Any | None = None,
        ku_backend: Any | None = None,
        chunking_service: Any | None = None,
        query_builder: Any | None = None,
        user_service: Any | None = None,
        vector_search_service: Any | None = None,
        embeddings_service: Any | None = None,
    ) -> None:
        """Initialize facade with sub-services via factory.

        Args:
            backend: PsBackend (REQUIRED)
            executor: Query executor (REQUIRED for persistence)
            graph_intel: GraphIntelligenceService (REQUIRED)
            event_bus: Event bus for domain events (optional)
            ai_service: Optional PsAIService for AI features
            content_repo: Content storage backend (optional)
            ku_backend: KuBackend for substance metric operations (optional)
            chunking_service: Chunking service for RAG (optional)
            query_builder: QueryBuilder for optimized queries (optional)
            user_service: UserService for UserContext access (optional)
            vector_search_service: Optional for semantic search
            embeddings_service: Optional for embedding generation
        """
        if not backend:
            raise ValueError(
                "PsService backend is REQUIRED. "
                "SKUEL follows fail-fast architecture - all required dependencies "
                "must be provided at initialization."
            )
        if not executor:
            raise ValueError(
                "PsService executor is REQUIRED. "
                "SKUEL follows fail-fast architecture - all required dependencies "
                "must be provided at initialization."
            )
        if not graph_intel:
            raise ValueError(
                "PsService graph_intel is REQUIRED. "
                "SKUEL follows fail-fast architecture - graph intelligence enables "
                "cross-domain queries for curriculum domains."
            )

        from core.services.curriculum_domain_config import (
            PsSubServices,
            create_ps_sub_services,
        )

        # Create all 12 sub-services via factory
        subs: PsSubServices = create_ps_sub_services(
            backend=backend,
            content_repo=content_repo,
            chunking_service=chunking_service,
            graph_intelligence_service=graph_intel,
            query_builder=query_builder,
            event_bus=event_bus,
            executor=executor,
            user_service=user_service,
            vector_search_service=vector_search_service,
            embeddings_service=embeddings_service,
        )

        # Assign sub-services from factory
        self.core = subs.core
        self.search = subs.search
        self.search_service = subs.search  # alias for compatibility
        self.graph = subs.graph
        self.semantic = subs.semantic
        self.practice = subs.practice
        self.mastery = subs.mastery
        self.relationships = subs.relationships
        self.intelligence: PsIntelligenceService = subs.intelligence
        self.adaptive = subs.adaptive
        self.application_discovery = subs.application_discovery
        self.context_service = subs.context_service

        # Organization needs facade reference — set post-init
        self.organization = subs.organization
        self.organization.ps_service = self  # type: ignore[attr-defined]

        # Progress sub-service (event-driven)
        self.progress = PsProgressService(backend=backend, event_bus=event_bus)

        # Store dependencies
        self.repo = backend
        self.executor = executor
        self.event_bus = event_bus
        self.content_repo = content_repo
        self.ku_backend = ku_backend
        self.user_service = user_service
        self.graph_intel = graph_intel

        # Optional AI service
        self.ai: PsAIService | None = ai_service

        self.logger = logger
        logger.debug("PsService facade initialized with 12 sub-services (merged Lesson)")

    # ============================================================================
    # CORE CRUD OPERATIONS - Delegated to PsCoreService
    # ============================================================================

    async def create_step(self, step: PathStep, path_uid: str | None = None) -> Result[PathStep]:
        """Create a path step."""
        return await self.core.create_step(step, path_uid)

    async def get_step(self, step_uid: str) -> Result[PathStep | None]:
        """Get a path step by UID."""
        return await self.core.get_step(step_uid)

    async def update_step(self, step_uid: str, updates: dict[str, Any]) -> Result[PathStep]:
        """Update a path step."""
        return await self.core.update_step(step_uid, updates)

    async def delete_step(self, step_uid: str) -> Result[bool]:
        """Delete a path step."""
        return await self.core.delete_step(step_uid)

    async def list_steps(
        self, path_uid: str | None = None, limit: int = 100, **kwargs: Any
    ) -> Result[list[PathStep]]:
        """List path steps."""
        return await self.core.list_steps(path_uid=path_uid, limit=limit, **kwargs)

    # ============================================================================
    # CRUD OPERATIONS PROTOCOL COMPATIBILITY
    # ============================================================================

    async def create(
        self,
        title: str,
        body: str,
        summary: str = "",
        tags: list[str] | None = None,
        **metadata: Any,
    ) -> Result[CurriculumDTO]:
        return await self.core.create(title, body, summary, tags, **metadata)

    async def get(self, uid: str) -> Result[PathStep | None]:
        """Get method for compatibility."""
        return await self.core.get(uid)

    async def update(self, uid: str, **updates: Any) -> Result[CurriculumDTO]:
        return await self.core.update(uid, **updates)

    async def delete(self, uid: str) -> Result[bool]:
        return await self.core.delete(uid)

    async def publish(self, uid: str) -> Result[CurriculumDTO]:
        return await self.core.publish(uid)

    async def archive(self, uid: str) -> Result[CurriculumDTO]:
        return await self.core.archive(uid)

    async def get_user_mastery(self, user_uid: UserUID, ku_uid: str) -> Result[float]:
        return await self.core.get_user_mastery(user_uid, ku_uid)

    async def get_all_user_knowledge_status(
        self, user_uid: UserUID
    ) -> Result[list[dict[str, Any]]]:
        return await self.mastery.get_all_user_knowledge_status(user_uid)

    async def get_chunks(self, uid: str, chunk_type: Any = None) -> Result[list[Any]]:
        return await self.core.get_chunks(uid, chunk_type)

    async def analyze_content(self, uid: str) -> Result[dict[str, Any]]:
        return await self.core.analyze_content(uid)

    async def get_with_content(self, uid: str) -> Result[tuple[PathStep, str]]:
        return await self.core.get_with_content(uid)

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
        user_uid: UserUID | None = None,
    ) -> Result[builtins.list[PathStep]]:
        """List path steps with pagination and sorting support."""
        return await self.list_steps(
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_desc=order_desc,
            user_uid=user_uid,
        )

    async def get_steps_batch(self, uids: list[str]) -> Result[list[Any]]:
        """Get multiple path steps in one batched query."""
        return await self.core.backend.get_many(uids)

    async def list_user_knowledge(self, user_uid: UserUID) -> Result[list[Any]]:
        """Get all knowledge entities for semantic search."""
        result = await self.repo.list(QueryLimit.BULK)
        if result.is_error:
            return Result.fail(result)
        entities, _ = result.value
        return Result.ok(list(entities))

    # ============================================================================
    # SEARCH OPERATIONS - Delegated to PsSearchService (BaseService-backed)
    # ============================================================================
    # PsSearchService inherits BaseService.search() for text search.
    # Specialized methods (facets, chunks, vector) will be expanded as needed.

    async def search_by_title_template(
        self, search_term: str, limit: int = 25
    ) -> Result[list[Any]]:
        """Search by title/template text."""
        return await self.search.search(query=search_term, limit=limit)

    async def search_with_user_context(
        self, query: str, user_context: dict[str, Any] | None = None, limit: int = 25
    ) -> Result[list[Any]]:
        """Search with optional user context."""
        return await self.search.search(query=query, limit=limit)

    async def search_by_tags(
        self, tags: list[str], match_all: bool = False, limit: int = 25
    ) -> Result[list[Any]]:
        """Search by tags (delegates to BaseService search for now)."""
        return await self.search.search(query=" ".join(tags), limit=limit)

    async def search_steps(self, query: str, limit: int = 50) -> Result[list[Any]]:
        """Search path steps by text query."""
        return await self.search.search(query=query, limit=limit)

    # ============================================================================
    # GRAPH OPERATIONS - Delegated to PsGraphService
    # ============================================================================

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

    async def get_step_with_context(self, uid: str, depth: int = 2) -> Result[dict[str, Any]]:
        return await self.graph.get_step_with_context(uid, depth)

    async def link_prerequisite(
        self, unit_uid: str, prerequisite_uid: str, is_mandatory: bool = True
    ) -> Result[bool]:
        return await self.graph.link_prerequisite(unit_uid, prerequisite_uid, is_mandatory)

    async def link_parent_child(self, parent_uid: str, child_uid: str) -> Result[bool]:
        return await self.graph.link_parent_child(parent_uid, child_uid)

    async def get_prerequisite_chain(
        self, uid: str, user_uid: UserUID | None = None
    ) -> Result[dict[str, Any]]:
        return await self.graph.get_prerequisite_chain(uid, user_uid)

    async def analyze_knowledge_gaps(
        self, target_uid: str, user_uid: UserUID
    ) -> Result[dict[str, Any]]:
        return await self.graph.analyze_knowledge_gaps(target_uid, user_uid)

    async def get_learning_recommendations(
        self, user_uid: UserUID, domain: str | None = None, limit: int = 5
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

    async def get_prerequisites(self, uid: str) -> Result[list[CurriculumDTO]]:
        """Get prerequisite entities (alias for find_prerequisites with defaults)."""
        return await self.graph.find_prerequisites(uid=uid, depth=GraphDepth.DEFAULT)

    async def get_enables(self, uid: str) -> Result[list[CurriculumDTO]]:
        """Get entities enabled by this one."""
        return await self.graph.find_next_steps(uid=uid)

    async def get_step_dependencies(self, uid: str, limit: int = 10) -> Result[list[CurriculumDTO]]:
        """Get entities that depend on this one."""
        return await self.graph.find_next_steps(uid=uid, limit=limit)

    # ============================================================================
    # APPLICATION DISCOVERY - Delegated to PsApplicationDiscoveryService
    # ============================================================================

    async def find_events_applying_knowledge(
        self, ku_uid: str, user_uid: UserUID, upcoming_only: bool = True
    ) -> Result[list[str]]:
        return await self.application_discovery.find_events_applying_knowledge(
            ku_uid, user_uid, upcoming_only
        )

    async def find_habits_reinforcing_knowledge(
        self, ku_uid: str, user_uid: UserUID, only_active: bool = True
    ) -> Result[list[str]]:
        return await self.application_discovery.find_habits_reinforcing_knowledge(
            ku_uid, user_uid, only_active
        )

    async def find_path_steps_containing(self, ku_uid: str, limit: int = 10) -> Result[list[str]]:
        return await self.application_discovery.find_path_steps_containing(ku_uid, limit)

    async def find_learning_paths_teaching(self, ku_uid: str, limit: int = 10) -> Result[list[str]]:
        return await self.application_discovery.find_learning_paths_teaching(ku_uid, limit)

    async def find_tasks_applying_knowledge(
        self, ku_uid: str, user_uid: UserUID, status_filter: str | None = None
    ) -> Result[list[str]]:
        return await self.application_discovery.find_tasks_applying_knowledge(
            ku_uid, user_uid, status_filter
        )

    async def find_goals_requiring_knowledge(
        self, ku_uid: str, user_uid: UserUID, status_filter: str | None = None
    ) -> Result[list[str]]:
        return await self.application_discovery.find_goals_requiring_knowledge(
            ku_uid, user_uid, status_filter
        )

    async def find_choices_informed_by_knowledge(
        self, ku_uid: str, user_uid: UserUID, pending_only: bool = False
    ) -> Result[list[str]]:
        return await self.application_discovery.find_choices_informed_by_knowledge(
            ku_uid, user_uid, pending_only
        )

    async def find_principles_embodying_knowledge(
        self, ku_uid: str, user_uid: UserUID, only_active: bool = True
    ) -> Result[list[str]]:
        return await self.application_discovery.find_principles_embodying_knowledge(
            ku_uid, user_uid, only_active
        )

    # ============================================================================
    # CONTEXT-FIRST OPERATIONS - Delegated to PsContextService
    # ============================================================================

    async def get_ready_to_learn_for_user(
        self,
        context: UserContext,
        domain: str | None = None,
        limit: int = 10,
    ) -> Result[list[ContextualKnowledge]]:
        return await self.context_service.get_ready_to_learn_for_user(context, domain, limit)

    async def get_learning_gaps_for_user(
        self,
        context: UserContext,
        goal_uid: str | None = None,
        limit: int = 10,
    ) -> Result[list[ContextualKnowledge]]:
        return await self.context_service.get_learning_gaps_for_user(context, goal_uid, limit)

    async def get_steps_to_reinforce_for_user(
        self,
        context: UserContext,
        mastery_threshold: float = 0.7,
        limit: int = 10,
    ) -> Result[list[ContextualKnowledge]]:
        return await self.context_service.get_steps_to_reinforce_for_user(
            context, mastery_threshold, limit
        )

    # ============================================================================
    # SEMANTIC OPERATIONS - Delegated to PsSemanticService
    # ============================================================================

    async def create_with_semantic_relationships(
        self, data: dict[str, Any], relationships: list[SemanticTriple]
    ) -> Result[CurriculumDTO]:
        return await self.semantic.create_with_semantic_relationships(data, relationships)

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

    async def create_step_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: SemanticRelationshipType,
        confidence: float = 0.9,
        strength: float = 1.0,
        notes: str | None = None,
    ) -> Result[bool]:
        """Create a semantic relationship between two path steps."""
        return await self.semantic.add_semantic_relationship(
            subject_uid=source_uid,
            predicate=relationship_type,
            object_uid=target_uid,
            confidence=confidence,
            strength=strength,
            notes=notes,
        )

    async def get_step_relationships(
        self, uid: str, relationship_type: str | None = None
    ) -> Result[list[dict[str, Any]]]:
        """Get relationships for a path step."""
        if not relationship_type:
            return Result.fail(
                Errors.validation(
                    message="relationship_type is required",
                    field="relationship_type",
                )
            )
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

    async def find_related_steps(
        self, uid: str, similarity_threshold: float = 0.7, limit: int = 10
    ) -> Result[list[CurriculumDTO]]:
        """Find related path steps via semantic neighborhood."""
        neighborhood_result = await self.semantic.get_semantic_neighborhood(
            uid=uid, depth=2, min_confidence=similarity_threshold
        )
        if neighborhood_result.is_error:
            return Result.fail(neighborhood_result)
        neighborhood = neighborhood_result.value
        related_uids: list[str] = []
        if isinstance(neighborhood, dict):
            for nodes in neighborhood.values():
                if isinstance(nodes, list):
                    for node in nodes[:limit]:
                        if isinstance(node, dict) and "uid" in node:
                            related_uids.append(node["uid"])
                        elif isinstance(node, HasUID):
                            related_uids.append(node.uid)
        results = []
        for step_uid in related_uids[:limit]:
            r = await self.core.get(step_uid)
            if r.is_ok and r.value:
                results.append(r.value)
        return Result.ok(results)

    # ============================================================================
    # ADAPTIVE CURRICULUM - Delegated to PsAdaptiveService
    # ============================================================================

    async def get_personalized_curriculum(
        self, user_uid: UserUID, sel_category: SELCategory, limit: int = 10
    ) -> Result[list[PathStep]]:
        return await self.adaptive.get_personalized_curriculum(user_uid, sel_category, limit)

    async def get_sel_journey(self, user_uid: UserUID) -> Result[LearningJourney]:
        return await self.adaptive.get_sel_journey(user_uid)

    async def track_curriculum_completion(
        self, user_uid: UserUID, ku_uid: str, completion_time_minutes: int = 30
    ) -> Result[None]:
        return await self.adaptive.track_curriculum_completion(
            user_uid, ku_uid, completion_time_minutes
        )

    # ============================================================================
    # ORGANIZATION - Delegated to PsOrganizationService
    # ============================================================================

    async def organize(self, parent_uid: str, child_uid: str, order: int = 0) -> Result[bool]:
        return await self.organization.organize(parent_uid, child_uid, order)

    async def unorganize(self, parent_uid: str, child_uid: str) -> Result[bool]:
        return await self.organization.unorganize(parent_uid, child_uid)

    async def reorder(self, parent_uid: str, child_uid: str, new_order: int) -> Result[bool]:
        return await self.organization.reorder(parent_uid, child_uid, new_order)

    async def is_organizer(self, ku_uid: str) -> Result[bool]:
        return await self.organization.is_organizer(ku_uid)

    async def get_organization_view(
        self, ku_uid: str, max_depth: int = 3
    ) -> Result[StepOrganizationView]:
        return await self.organization.get_organization_view(ku_uid, max_depth)

    async def get_navigation(self, ku_uid: str) -> Result[StepNavigation]:
        return await self.organization.get_navigation(ku_uid)

    async def find_organizers(self, ku_uid: str) -> Result[list[OrganizerResult]]:
        return await self.organization.find_organizers(ku_uid)

    async def list_root_organizers(self, limit: int = 50) -> Result[list[RootOrganizerResult]]:
        return await self.organization.list_root_organizers(limit)

    async def get_organized_children(self, ku_uid: str) -> Result[list[OrganizerResult]]:
        return await self.organization.get_organized_children(ku_uid)

    # ============================================================================
    # MASTERY OPERATIONS - Delegated to PsMasteryService
    # ============================================================================

    async def record_view(
        self, user_uid: UserUID, ku_uid: str, time_spent_seconds: int = 0
    ) -> Result[bool]:
        return await self.mastery.record_view(user_uid, ku_uid, time_spent_seconds)

    async def mark_in_progress(self, user_uid: UserUID, ku_uid: str) -> Result[bool]:
        return await self.mastery.mark_in_progress(user_uid, ku_uid)

    async def mark_as_read(self, user_uid: UserUID, ku_uid: str) -> Result[None]:
        return await self.mastery.mark_as_read(user_uid, ku_uid)

    async def toggle_bookmark(self, user_uid: UserUID, ku_uid: str) -> Result[bool]:
        return await self.mastery.toggle_bookmark(user_uid, ku_uid)

    async def mark_mastered(
        self, user_uid: UserUID, ku_uid: str, mastery_score: float, method: str = "report_approval"
    ) -> Result[bool]:
        return await self.mastery.mark_mastered(user_uid, ku_uid, mastery_score, method)

    async def get_bookmarked_kus(self, user_uid: UserUID) -> Result[list[str]]:
        return await self.mastery.get_bookmarked_kus(user_uid)

    # ============================================================================
    # STEP-PATH RELATIONSHIP OPERATIONS (UnifiedRelationshipService)
    # ============================================================================

    async def attach_step_to_path(
        self, step_uid: str, path_uid: str, sequence: int | None = None
    ) -> Result[bool]:
        """Attach an existing path step to a learning path."""
        if sequence is None:
            seq_query = """
            MATCH (p:Entity {uid: $path_uid})-[r:HAS_STEP]->()
            RETURN coalesce(max(r.sequence), -1) + 1 as next_sequence
            """
            seq_result = await self.executor.execute_query(seq_query, {"path_uid": path_uid})
            if seq_result.is_error:
                sequence = 0
            else:
                records = seq_result.value
                sequence = records[0]["next_sequence"] if records else 0
        return await self.relationships.create_relationship_with_properties(
            relationship_key="in_paths",
            from_uid=step_uid,
            to_uid=path_uid,
            edge_properties={"sequence": sequence, "completed": False},
        )

    async def detach_step_from_path(self, step_uid: str, path_uid: str) -> Result[bool]:
        """Detach a path step from a learning path."""
        return await self.relationships.delete_relationship(
            relationship_key="in_paths",
            from_uid=step_uid,
            to_uid=path_uid,
        )

    async def get_path_steps_batch(
        self, uids: builtins.list[str]
    ) -> Result[builtins.list[PathStep | None]]:
        """Get multiple path steps in one batched query."""
        return await self.core.backend.get_many(uids)

    async def get_step_paths(self, step_uid: str, limit: int = 100) -> Result[builtins.list[str]]:
        """Get all learning paths that contain a specific step."""
        return await self.relationships.get_related_uids("in_paths", step_uid)

    # ============================================================================
    # KU COMPOSITION (PathStep → atomic Ku via USES_KU)
    # ============================================================================

    async def link_to_ku(self, ps_uid: str, ku_uid: str) -> Result[bool]:
        """Link this PathStep to an atomic Ku via USES_KU."""
        return await self.core.backend.link_to_ku(ps_uid, ku_uid)  # type: ignore[attr-defined]

    async def get_used_kus(self, ps_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all atomic Kus used by this PathStep."""
        return await self.core.backend.get_used_kus(ps_uid)  # type: ignore[attr-defined]

    # ============================================================================
    # CONTENT AND TAG MANAGEMENT
    # ============================================================================

    async def update_step_content(
        self, uid: str, content: str, title: str | None = None
    ) -> Result[CurriculumDTO]:
        """Update a path step's content."""
        updates: dict[str, Any] = {"content": content}
        if title:
            updates["title"] = title
        return await self.core.update(uid, updates)

    async def add_step_tags(self, uid: str, tags: list[str]) -> Result[CurriculumDTO]:
        """Add tags to a path step."""
        result = await self.core.get(uid)
        if result.is_error:
            return Result.fail(result)
        entity = result.value
        if not entity:
            return Result.fail(Errors.not_found(resource="PathStep", identifier=uid))
        current_tags = list(entity.tags or [])
        updated_tags = list(set(current_tags + tags))
        return await self.core.update(uid, {"tags": updated_tags})

    async def remove_step_tags(self, uid: str, tags: list[str]) -> Result[CurriculumDTO]:
        """Remove tags from a path step."""
        result = await self.core.get(uid)
        if result.is_error:
            return Result.fail(result)
        entity = result.value
        if not entity:
            return Result.fail(Errors.not_found(resource="PathStep", identifier=uid))
        current_tags = list(entity.tags or [])
        updated_tags = [t for t in current_tags if t not in tags]
        return await self.core.update(uid, {"tags": updated_tags})

    # ============================================================================
    # SUBSTANCE TRACKING EVENT LISTENERS
    # ============================================================================

    @safe_event_handler("knowledge.applied_in_task")
    async def handle_knowledge_applied_in_task(self, event: Any) -> None:
        await self.increment_substance_metric(
            ku_uid=event.knowledge_uid,
            metric="times_applied_in_tasks",
            timestamp_field="last_applied_date",
            timestamp=event.occurred_at,
        )

    @safe_event_handler("knowledge.practiced_in_event")
    async def handle_knowledge_practiced_in_event(self, event: Any) -> None:
        await self.increment_substance_metric(
            ku_uid=event.knowledge_uid,
            metric="times_practiced_in_events",
            timestamp_field="last_practiced_date",
            timestamp=event.occurred_at,
        )

    @safe_event_handler("knowledge.built_into_habit")
    async def handle_knowledge_built_into_habit(self, event: Any) -> None:
        await self.increment_substance_metric(
            ku_uid=event.knowledge_uid,
            metric="times_built_into_habits",
            timestamp_field="last_built_into_habit_date",
            timestamp=event.occurred_at,
        )

    @safe_event_handler("knowledge.informed_choice")
    async def handle_knowledge_informed_choice(self, event: Any) -> None:
        await self.increment_substance_metric(
            ku_uid=event.knowledge_uid,
            metric="choices_informed_count",
            timestamp_field="last_choice_informed_date",
            timestamp=event.occurred_at,
        )

    @safe_event_handler("knowledge.bulk_applied_in_task")
    async def handle_knowledge_bulk_applied_in_task(self, event: Any) -> None:
        await self.batch_increment_substance_metric(
            ku_uids=event.knowledge_uids,
            metric="times_applied_in_tasks",
            timestamp_field="last_applied_date",
            timestamp=event.occurred_at,
        )

    @safe_event_handler("knowledge.bulk_built_into_habit")
    async def handle_knowledge_bulk_built_into_habit(self, event: Any) -> None:
        await self.batch_increment_substance_metric(
            ku_uids=event.knowledge_uids,
            metric="times_built_into_habits",
            timestamp_field="last_built_into_habit_date",
            timestamp=event.occurred_at,
        )

    @safe_event_handler("knowledge.bulk_informed_choice")
    async def handle_knowledge_bulk_informed_choice(self, event: Any) -> None:
        await self.batch_increment_substance_metric(
            ku_uids=event.knowledge_uids,
            metric="choices_informed_count",
            timestamp_field="last_choice_informed_date",
            timestamp=event.occurred_at,
        )

    async def batch_increment_substance_metric(
        self, ku_uids: tuple[str, ...], metric: str, timestamp_field: str, timestamp: Any
    ) -> None:
        """Atomically increment a substance metric for multiple entities."""
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

    async def increment_substance_metric(
        self, ku_uid: str, metric: str, timestamp_field: str, timestamp: Any
    ) -> None:
        """Atomically increment a substance metric in Neo4j."""
        if metric not in _VALID_SUBSTANCE_METRICS:
            self.logger.error(f"Invalid substance metric rejected: {metric}")
            return
        if timestamp_field not in _VALID_SUBSTANCE_TIMESTAMP_FIELDS:
            self.logger.error(f"Invalid substance timestamp field rejected: {timestamp_field}")
            return
        if not self.ku_backend:
            self.logger.error("ku_backend not wired — cannot increment substance metric")
            return
        timestamp_str = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)
        result = await self.ku_backend.increment_substance(
            ku_uid=ku_uid,
            metric=metric,
            timestamp_field=timestamp_field,
            timestamp_str=timestamp_str,
        )
        if result.is_error:
            self.logger.error(f"Failed substance increment for {ku_uid}: {result.error}")

    # ============================================================================
    # TEMPLATE & UTILITY OPERATIONS
    # ============================================================================

    @with_error_handling("get_query_metrics", error_type="system")
    async def get_query_metrics(self) -> Result[dict[str, Any]]:
        """Get query performance metrics."""
        metrics = get_metrics_summary()
        return Result.ok(metrics)

    async def get_step_stats(self, uid: str) -> Result[dict[str, Any]]:
        """Get statistics for a path step."""
        result = await self.core.get(uid)
        if result.is_error:
            return Result.fail(result)
        entity = result.value
        if not entity:
            return Result.fail(Errors.not_found(resource="PathStep", identifier=uid))
        prereqs_result = await self.get_prerequisites(uid)
        prereq_count = len(prereqs_result.value) if prereqs_result.is_ok else 0
        deps_result = await self.get_step_dependencies(uid)
        deps_count = len(deps_result.value) if deps_result.is_ok else 0
        return Result.ok(
            {
                "uid": uid,
                "title": entity.title,
                "domain": entity.domain.value if entity.domain else None,
                "word_count": entity.word_count,
                "tag_count": len(entity.tags or []),
                "prerequisite_count": prereq_count,
                "dependent_count": deps_count,
                "created_at": entity.created_at.isoformat() if entity.created_at else None,
                "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
            }
        )

    async def get_step_recommendations(
        self,
        uid: str,
        user_uid: UserUID | None = None,
        recommendation_type: str = "learning",
    ) -> Result[list[CurriculumDTO]]:
        """Get personalized step recommendations."""
        if recommendation_type == "next":
            return await self.graph.find_next_steps(uid=uid, limit=5)
        elif recommendation_type == "related":
            return await self.find_related_steps(uid, limit=10)
        else:
            return await self.graph.find_next_steps(uid=uid, limit=10)

    async def list_step_domains(self) -> Result[list[str]]:
        """List all path step domains."""
        from core.models.enums import Domain

        return Result.ok([d.value for d in Domain])

    async def list_step_categories(self) -> Result[list[str]]:
        """List all path step categories."""
        result = await self.repo.list(QueryLimit.COMPREHENSIVE)
        if result.is_error:
            return Result.fail(result)
        entities, _ = result.value
        categories = set()
        for entity in entities:
            sel_category = getattr(entity, "sel_category", None)
            if sel_category:
                categories.add(sel_category)
        return Result.ok(sorted(list(categories)))

    async def list_step_tags(self, min_usage: int = 1) -> Result[list[dict[str, Any]]]:
        """List all path step tags with usage counts."""
        result = await self.repo.list(QueryLimit.COMPREHENSIVE)
        if result.is_error:
            return Result.fail(result)
        entities, _ = result.value
        tag_counts: dict[str, int] = {}
        for entity in entities:
            if entity.tags:
                for tag in entity.tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return Result.ok(
            [
                {"tag": tag, "count": count}
                for tag, count in sorted(tag_counts.items(), key=get_second_item, reverse=True)
                if count >= min_usage
            ]
        )

    # ============================================================================
    # USER CONTEXT OPERATIONS
    # ============================================================================

    async def get_user_step_context(
        self, ku_uid: str, user_context: UserContext
    ) -> Result[dict[str, Any]]:
        """Get personalized path step context for a user."""
        return await self.intelligence.calculate_user_substance(ku_uid, user_context)

    # =========================================================================
    # QUERY LAYER (FilteredContextProvider)
    # =========================================================================

    async def get_filtered_context(
        self,
        user_uid: UserUID,
        status_filter: str = "all",
        sort_by: str = "title",
    ) -> Result[ListContext]:
        """Get filtered and sorted path steps with pre-filter stats."""

        async def fetch_all() -> Result[list[Any]]:
            result = await self.core.list(limit=500)
            if result.is_error:
                return Result.fail(result)
            entities, _ = result.value
            return Result.ok(list(entities))

        def apply_filters(all_steps: list[Any]) -> list[Any]:
            return apply_entity_filter(all_steps, status_filter, _PS_FILTER_CONFIG)

        return await build_filtered_context(
            fetch_all=fetch_all,
            compute_stats=_compute_ps_stats,
            apply_filters=apply_filters,
            apply_sort=_apply_ps_sort,
            sort_by=sort_by,
        )
