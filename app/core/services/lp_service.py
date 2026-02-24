"""
Learning Path Service - Facade
================================

THE single owner for all learning path management in SKUEL.

Delegates to specialized sub-services following the unified domain pattern.

Sub-Services:
- LpCoreService: CRUD operations + persistence (extends BaseService)
- LpSearchService: Search operations (extends BaseService)
- LpProgressService: Progress tracking (event-driven)
- UnifiedRelationshipService: Path-step associations (shared with other domains)
- LpIntelligenceService: Validation, adaptive learning, context
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.services.lp.lp_ai_service import LpAIService
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.sort_functions import make_attribute_sort_key

if TYPE_CHECKING:
    from core.models.curriculum.learning_path import LearningPath
    from core.models.curriculum.learning_step import LearningStep
    from core.ports import EventBusOperations
    from core.services.ku_service import KuService
    from core.services.ls_service import LsService

logger = get_logger(__name__)


class LpService:
    """
    Facade for learning path management.

    **January 2026 - LP Consolidation (ADR-031):**
    Consolidated from 8 sub-services to 4:
    - Core: CRUD operations (non-standard: requires ls_service)
    - Search: Discovery operations
    - Relationships: Path-step associations (via UnifiedRelationshipService)
    - Intelligence: ALL validation/analysis/adaptive/context operations
    - Progress: Progress tracking (event-driven)

    Explicit Delegations:
    - Core: create_path_from_knowledge_units, create_path, get_learning_paths_batch,
            get_learning_path, list_user_paths, list_all_paths, get_path_steps,
            get_current_step, update_path, delete_path
    - Intelligence: validate_path_prerequisites, identify_path_blockers,
            get_optimal_path_recommendation, get_path_with_context,
            analyze_path_knowledge_scope,
            find_learning_sequence, get_next_adaptive_step, get_recommended_learning_steps

    Explicit Methods (custom logic):
    - Step operations: create_step, get_step, update_step, delete_step, list_steps (ls_service guard)
    - CRUD compatibility: create, get, update, delete, list (complex signatures)

    Source Tag: "lp_explicit"
    - Format: "lp_explicit" for user-created relationships
    - Format: "lp_inferred" for system-generated relationships

    SKUEL Architecture:
    - Uses explicit delegation methods for full MyPy visibility
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(
        self,
        backend: Any,
        executor: Any,
        ls_service: LsService,
        ku_service: KuService | None = None,
        progress_service: Any | None = None,
        graph_intelligence_service: Any | None = None,
        event_bus: EventBusOperations | None = None,
        progress_backend: Any | None = None,
        user_service: Any | None = None,
        ai_service: LpAIService | None = None,
    ) -> None:
        """
        Initialize facade with sub-services via factory.

        FAIL-FAST ARCHITECTURE (per CLAUDE.md):
        The backend, executor, ls_service, and graph_intelligence_service are REQUIRED.
        Services run at full capacity or fail immediately at startup.

        **January 2026 - Factory Pattern (Architecture Consistency Review):**
        Uses create_lp_sub_services() factory for consistent initialization.
        Factory handles cross-domain dependency: LpCoreService requires ls_service.

        Args:
            backend: BackendOperations for LP entities (REQUIRED — created by composition root)
            executor: QueryExecutor for raw Cypher (REQUIRED — created by composition root)
            ls_service: LsService for learning step operations - REQUIRED
            ku_service: Optional KuService for prerequisite queries
            progress_service: Optional UserProgressService for progress tracking
            graph_intelligence_service: GraphIntelligenceService - REQUIRED for cross-domain queries
            event_bus: Event bus for publishing domain events (optional)
            progress_backend: UserProgress backend for learning state analysis (optional)
            user_service: UserService for UserContext access (optional)
            ai_service: Optional LpAIService for AI features (ADR-030 separation)
        """
        # FAIL-FAST: Required dependencies
        if not backend:
            raise ValueError(
                "LpService backend is REQUIRED. "
                "SKUEL follows fail-fast architecture - all required dependencies "
                "must be provided at initialization."
            )
        if not executor:
            raise ValueError(
                "LpService executor is REQUIRED. "
                "SKUEL follows fail-fast architecture - all required dependencies "
                "must be provided at initialization."
            )
        if not ls_service:
            raise ValueError(
                "LpService ls_service is REQUIRED. "
                "SKUEL follows fail-fast architecture - all required dependencies "
                "must be provided at initialization."
            )
        if not graph_intelligence_service:
            raise ValueError(
                "LpService graph_intelligence_service is REQUIRED. "
                "SKUEL follows fail-fast architecture - graph intelligence enables "
                "cross-domain queries for curriculum domains."
            )

        # Create all sub-services via factory (January 2026 - Architecture Consistency)
        from core.utils.curriculum_domain_config import create_lp_sub_services

        subs = create_lp_sub_services(
            backend=backend,
            executor=executor,
            ls_service=ls_service,
            graph_intelligence_service=graph_intelligence_service,
            event_bus=event_bus,
            progress_backend=progress_backend,
            user_service=user_service,
        )

        # Assign sub-services from factory result
        self.core = subs.core
        self.search = subs.search
        self.relationships = subs.relationships
        self.intelligence = subs.intelligence
        self.progress = subs.progress

        # Store dependencies
        self.ls_service = ls_service
        self.ku_service = ku_service
        self.graph_intel = graph_intelligence_service
        self.event_bus = event_bus
        self.ai: LpAIService | None = ai_service
        self.logger = logger

        logger.info(
            "LpService initialized via factory (5 sub-services, cross-domain dependency handled)"
        )

    # ============================================================================
    # CORE CRUD OPERATIONS - Delegated to LpCoreService
    # ============================================================================

    async def create_path_from_knowledge_units(self, *args: Any, **kwargs: Any) -> Any:
        """Create a learning path from knowledge units."""
        return await self.core.create_path_from_knowledge_units(*args, **kwargs)

    async def create_path(self, *args: Any, **kwargs: Any) -> Any:
        """Create a learning path."""
        return await self.core.create_path(*args, **kwargs)

    async def get_learning_paths_batch(self, uids: list[str]) -> Any:
        """Get multiple learning paths in one query."""
        return await self.core.get_learning_paths_batch(uids)

    async def get_learning_path(self, uid: str) -> Any:
        """Get a learning path by UID."""
        return await self.core.get_learning_path(uid)

    async def list_user_paths(self, user_uid: str, limit: int = 100) -> Any:
        """List learning paths for a user."""
        return await self.core.list_user_paths(user_uid, limit)

    async def list_all_paths(self, limit: int = 100) -> Any:
        """List all learning paths."""
        return await self.core.list_all_paths(limit=limit)

    async def get_path_steps(self, path_uid: str) -> Any:
        """Get steps in a learning path."""
        return await self.core.get_path_steps(path_uid)

    async def get_current_step(self, path_uid: str) -> Any:
        """Get current step for a user in a learning path."""
        return await self.core.get_current_step(path_uid)

    async def update_path(self, uid: str, updates: dict[str, Any]) -> Any:
        """Update a learning path."""
        return await self.core.update_path(uid, updates)

    async def delete_path(self, uid: str) -> Any:
        """Delete a learning path."""
        return await self.core.delete_path(uid)

    # ============================================================================
    # INTELLIGENCE OPERATIONS - Delegated to LpIntelligenceService
    # ============================================================================

    async def validate_path_prerequisites(self, *args: Any, **kwargs: Any) -> Any:
        """Validate prerequisites for a learning path."""
        return await self.intelligence.validate_path_prerequisites(*args, **kwargs)

    async def identify_path_blockers(self, *args: Any, **kwargs: Any) -> Any:
        """Identify blockers in a learning path."""
        return await self.intelligence.identify_path_blockers(*args, **kwargs)

    async def get_optimal_path_recommendation(self, *args: Any, **kwargs: Any) -> Any:
        """Get optimal path recommendation."""
        return await self.intelligence.get_optimal_path_recommendation(*args, **kwargs)

    async def get_path_with_context(self, *args: Any, **kwargs: Any) -> Any:
        """Get learning path with context."""
        return await self.intelligence.get_path_with_context(*args, **kwargs)

    async def analyze_path_knowledge_scope(self, *args: Any, **kwargs: Any) -> Any:
        """Analyze knowledge scope of a learning path."""
        return await self.intelligence.analyze_path_knowledge_scope(*args, **kwargs)

    async def find_learning_sequence(self, *args: Any, **kwargs: Any) -> Any:
        """Find learning sequence."""
        return await self.intelligence.find_learning_sequence(*args, **kwargs)

    async def get_next_adaptive_step(self, *args: Any, **kwargs: Any) -> Any:
        """Get next adaptive learning step."""
        return await self.intelligence.get_next_adaptive_step(*args, **kwargs)

    async def get_recommended_learning_steps(self, *args: Any, **kwargs: Any) -> Any:
        """Get recommended learning steps."""
        return await self.intelligence.get_recommended_learning_steps(*args, **kwargs)

    # ============================================================================
    # LEARNING STEP OPERATIONS - Delegated to LsService
    # ============================================================================
    # Note: These require ls_service guard, kept explicit.

    async def create_step(
        self, step: LearningStep, path_uid: str | None = None
    ) -> Result[LearningStep]:
        """Create a learning step. Delegates to LsService."""
        if not self.ls_service:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(message="LsService not available", operation="create_step")
            )
        return await self.ls_service.create_step(step, path_uid)

    async def get_step(self, step_uid: str) -> Result[LearningStep | None]:
        """Get a learning step by UID. Delegates to LsService."""
        if not self.ls_service:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(message="LsService not available", operation="get_step")
            )
        return await self.ls_service.get_step(step_uid)

    async def update_step(self, step_uid: str, updates: dict[str, Any]) -> Result[LearningStep]:
        """Update a learning step. Delegates to LsService."""
        if not self.ls_service:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(message="LsService not available", operation="update_step")
            )
        return await self.ls_service.update_step(step_uid, updates)

    async def delete_step(self, step_uid: str) -> Result[bool]:
        """Delete a learning step. Delegates to LsService."""
        if not self.ls_service:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(message="LsService not available", operation="delete_step")
            )
        return await self.ls_service.delete_step(step_uid)

    async def list_steps(
        self, path_uid: str | None = None, limit: int = 100
    ) -> Result[list[LearningStep]]:
        """List learning steps. Delegates to LsService."""
        if not self.ls_service:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(message="LsService not available", operation="list_steps")
            )
        return await self.ls_service.list_steps(path_uid, limit)

    # ============================================================================
    # CRUD OPERATIONS PROTOCOL COMPATIBILITY
    # ============================================================================

    async def create(self, entity: LearningPath) -> Result[LearningPath]:
        """Create method for CRUDRouteFactory compatibility."""
        user_uid = getattr(entity, "user_uid", "demo_user")
        steps = entity.metadata.get("steps", []) if entity.metadata else []
        return await self.create_path(
            user_uid=user_uid,
            title=entity.title,
            description=entity.description,
            steps=steps,
            domain=entity.domain,
        )

    async def get(self, uid: str) -> Result[LearningPath | None]:
        """Get method for CRUDRouteFactory compatibility."""
        return await self.get_learning_path(uid)

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[LearningPath]:
        """Update method for CRUDRouteFactory compatibility."""
        return await self.update_path(uid, updates)

    async def delete(self, uid: str) -> Result[bool]:
        """Delete method for CRUDRouteFactory compatibility."""
        return await self.delete_path(uid)

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
        user_uid: str | None = None,
    ) -> Result[list[LearningPath]]:
        """
        List learning paths with pagination and sorting support.

        CRUDRouteFactory compatible method with full filtering/sorting.

        Args:
            limit: Maximum number of paths to return
            offset: Number of paths to skip (for pagination)
            order_by: Field to sort by (e.g., 'title', 'created_at')
            order_desc: Sort in descending order if True
            user_uid: Filter by user (if provided)
        """
        if user_uid:
            return await self.list_user_paths(user_uid, limit)

        # Service-layer filtering pattern: get more results to allow pagination
        backend_limit = limit + offset if offset > 0 else limit
        result = await self.list_all_paths(limit=backend_limit)

        if result.is_error:
            return result

        paths = result.value

        # Service-layer filtering: sorting
        if order_by:
            reverse = order_desc
            try:
                sort_key = make_attribute_sort_key(order_by)
                paths = sorted(paths, key=sort_key, reverse=reverse)
            except (AttributeError, TypeError):
                # If order_by field doesn't exist or can't be compared, skip sorting
                pass

        # Service-layer filtering: pagination (offset)
        if offset > 0:
            paths = paths[offset:]

        # Apply final limit
        paths = paths[:limit]

        return Result.ok(paths)
