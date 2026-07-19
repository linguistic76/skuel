"""
LP Search Service - BaseService Pattern
========================================

Search operations for Learning Paths extending BaseService for
unified search architecture.

This service provides:
- Text search on name/goal/outcomes (inherited from BaseService)
- Graph-aware faceted search with relationship traversal
- LP-specific reverse-lookup lenses: get_aligned_with_goal(), get_by_knowledge()

Architecture (January 2026 Unified):
- Extends BaseService[BackendOperations[Lp], Lp]
- Inherits: search(), get_by_status(), get_with_content(), etc.
- Adds: LP-specific reverse-lookup lenses (goal alignment, knowledge)
- No wrapper backend - uses UniversalNeo4jBackend directly
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.pathways.learning_path import LearningPath
from core.models.pathways.learning_path_dto import LearningPathDTO
from core.models.type_hints import UserUID
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.curriculum_protocols import LpOperations
    from core.services.user import UserContext

logger = get_logger(__name__)


class LpSearchService(BaseService["LpOperations", LearningPath]):
    """
    Search service for Learning Paths - BaseService pattern.

    Implements DomainSearchOperations[Lp] protocol for integration with
    SearchRouter and unified search infrastructure.

    Inherited Methods (from BaseService):
    - search(query, limit) - Text search on _search_fields
    - get_by_relationship(related_uid, relationship_type, direction)
    - get_by_status(status, limit) - Filter by status
    - graph_aware_faceted_search(request) - Rich graph context search
    - get_with_content(uid) - Entity with full content
    - get_with_context(uid, depth) - Entity with graph neighborhood
    - get_prerequisites(uid, depth) - Prerequisite chain
    - get_enables(uid, depth) - What this enables
    - get_hierarchy(uid) - Position in KU → PS → LP hierarchy
    - get_user_progress(user_uid, entity_uid) - User mastery data

    LP-Specific Methods:
    - get_aligned_with_goal(goal_uid) - Paths aligned with goal (staged, PLANNED)
    - get_by_knowledge(ku_uid) - Paths teaching a Ku (staged, PLANNED)
    - get_prioritized(user_uid, context) - Context-aware prioritization

    SKUEL Architecture:
    - No custom filter classes - uses SearchRequest
    """

    # =========================================================================
    # DomainConfig consolidation (January 2026)
    # =========================================================================
    # All configuration in one place, using centralized relationship registry
    # See: /docs/decisions/ADR-025-service-consolidation-patterns.md
    # Note: LP uses name instead of title, and stores main content in goal field
    _config = create_curriculum_domain_config(
        dto_class=LearningPathDTO,
        model_class=LearningPath,
        entity_label="Entity",
        domain_name="lp",
        search_fields=("title", "description"),  # LP: name→title, goal→description
        search_order_by="updated_at",
        content_field="description",  # LP goal mapped to Entity description
    )

    def __init__(self, backend: LpOperations) -> None:
        """Initialize service with required backend."""
        super().__init__(backend=backend, service_name="lp.search")

    # =========================================================================
    # LP-SPECIFIC METHODS
    # =========================================================================

    async def get_aligned_with_goal(
        self, goal_uid: str, limit: int = 50
    ) -> Result[list[LearningPath]]:
        """
        Get Learning Paths aligned with a specific goal.

        Uses graph relationship traversal to find paths connected
        via ALIGNED_WITH_GOAL relationship.

        Args:
            goal_uid: Goal UID to find aligned paths for
            limit: Maximum results (default 50)

        Returns:
            Result containing Learning Paths aligned with the goal
        """
        if not goal_uid:
            return Result.fail(Errors.validation(message="goal_uid is required", field="goal_uid"))

        result = await self.backend.get_paths_aligned_with_goal(goal_uid, limit)
        if result.is_error:
            return Result.fail(result)

        paths = result.value

        self.logger.debug(f"Found {len(paths)} paths aligned with goal {goal_uid}")
        return Result.ok(paths)

    async def get_by_knowledge(self, ku_uid: str, limit: int = 20) -> Result[list[LearningPath]]:
        """
        Find learning paths that teach this knowledge (via path steps).

        Graph Pattern: (LP)-[:HAS_STEP]->(PS)-[:CONTAINS_KNOWLEDGE]->(Ku)

        This is a 2-hop indirect relationship query. Uses DISTINCT since
        multiple steps within a path may contain the same knowledge.

        Args:
            ku_uid: Knowledge unit UID
            limit: Maximum results to return (default 20)

        Returns:
            Result containing list of Learning Path entities
        """
        if not ku_uid:
            return Result.fail(Errors.validation(message="ku_uid is required", field="ku_uid"))

        result = await self.backend.get_paths_by_knowledge(ku_uid, limit)
        if result.is_error:
            return Result.fail(result)

        paths = result.value

        self.logger.debug(f"Found {len(paths)} learning paths for knowledge {ku_uid}")
        return Result.ok(paths)

    async def get_prioritized(
        self, user_uid: UserUID, context: UserContext, limit: int = 20
    ) -> Result[list[LearningPath]]:
        """
        Get Learning Paths prioritized by user context.

        Prioritization considers:
        1. Adaptive paths (highest - personalized learning)
        2. Paths aligned with user's goals
        3. Structured paths
        4. Recently updated

        Args:
            user_uid: User UID for personalization
            context: User's context for goal alignment
            limit: Maximum results (default 20)

        Returns:
            Result containing prioritized Learning Paths
        """
        result = await self.backend.get_user_paths_prioritized(user_uid, limit)
        if result.is_error:
            return Result.fail(result)

        paths = result.value

        self.logger.debug(f"Prioritized LP search returned {len(paths)} results")
        return Result.ok(paths)
