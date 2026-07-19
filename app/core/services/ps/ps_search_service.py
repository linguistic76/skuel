"""
PathStep Search Service - BaseService Pattern
===============================================

Search operations for PathSteps extending BaseService for
unified search architecture.

This service provides:
- Text search on title/intent/description (inherited from BaseService)
- Graph-aware faceted search with relationship traversal
- PS-specific methods: get_standalone_steps(), get_prioritized()

Architecture (January 2026 Unified):
- Extends BaseService[BackendOperations[PathStep], PathStep]
- Inherits: search(), get_by_status(), get_with_content(), etc.
- Adds: PS-specific methods for learning path integration
- No wrapper backend - uses UniversalNeo4jBackend directly
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.pathways.path_step import PathStep
from core.models.pathways.path_step_dto import PathStepDTO
from core.models.type_hints import UserUID
from core.ports.query_types import NousSubtopicPair, to_nous_subtopic_pairs
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.curriculum_protocols import PsOperations
    from core.services.user import UserContext

logger = get_logger(__name__)


class PsSearchService(BaseService["PsOperations", PathStep]):
    """
    Search service for PathSteps - BaseService pattern.

    Implements DomainSearchOperations[PathStep] protocol for integration with
    SearchRouter and unified search infrastructure.

    Inherited Methods (from BaseService):
    - search(query, limit) - Text search on _search_fields
    - get_by_relationship(related_uid, relationship_type, direction)
    - get_by_status(status, limit) - Filter by StepStatus
    - graph_aware_faceted_search(request) - Rich graph context search
    - get_with_content(uid) - Entity with full content
    - get_with_context(uid, depth) - Entity with graph neighborhood
    - get_prerequisites(uid, depth) - Prerequisite chain
    - get_enables(uid, depth) - What this enables
    - get_hierarchy(uid) - Position in KU → PS → LP hierarchy
    - get_user_progress(user_uid, entity_uid) - User mastery data

    PS-Specific Methods:
    - get_standalone_steps() - Steps not in any learning path
    - get_prioritized(user_uid, context) - Context-aware prioritization

    SKUEL Architecture:
    - No custom filter classes - uses SearchRequest
    """

    # =========================================================================
    # DomainConfig consolidation (January 2026)
    # =========================================================================
    # All configuration in one place, using centralized relationship registry
    # See: /docs/decisions/ADR-025-service-consolidation-patterns.md
    _config = create_curriculum_domain_config(
        dto_class=PathStepDTO,
        model_class=PathStep,
        entity_label="Entity",
        domain_name="ps",
        search_fields=("title", "intent", "description"),  # PS-specific fields
        search_order_by="updated_at",
        category_field="nous",  # NOUS topic membership (array — `has` semantics)
        content_field="description",  # PS stores content in description
    )

    def __init__(self, backend: PsOperations) -> None:
        """Initialize service with required backend."""
        super().__init__(backend=backend, service_name="ps.search")

    # =========================================================================
    # PS-SPECIFIC METHODS
    # =========================================================================

    async def nous_subtopic_pairs(self) -> Result[list[NousSubtopicPair]]:
        """This PathStep label's contribution of (nous, nous_subtopic) pairs.

        Scoped to `:PathStep` — mirror of `KuSearchService.nous_subtopic_pairs`.
        `SearchRouter.nous_subtopic_map` merges both domains' pairs into the
        dependent /search dropdown's map, keeping cross-domain aggregation in the
        service layer. Raw Neo4j property unions are narrowed to typed string
        pairs at the domain boundary.

        Backend: ``PsBackend.nous_subtopic_pairs``.
        """
        result = await self.backend.nous_subtopic_pairs()
        if result.is_error:
            return Result.fail(result)
        return Result.ok(to_nous_subtopic_pairs(result.value or []))

    async def get_standalone_steps(self, limit: int = 50) -> Result[list[PathStep]]:
        """
        Get standalone PathSteps (not part of any learning path).

        Args:
            limit: Maximum results (default 50)

        Returns:
            Result containing standalone PathSteps
        """
        result = await self.backend.get_standalone_steps(limit)
        if result.is_error:
            return Result.fail(result)

        steps = result.value

        self.logger.debug(f"Found {len(steps)} standalone steps")
        return Result.ok(steps)

    async def get_prioritized(
        self, user_uid: UserUID, context: UserContext, limit: int = 20
    ) -> Result[list[PathStep]]:
        """
        Get PathSteps prioritized by user context.

        Prioritization considers:
        1. In-progress steps (highest)
        2. Steps aligned with user's current goals
        3. Priority level
        4. Recently updated

        Args:
            user_uid: User UID for personalization
            context: User's context for goal alignment
            limit: Maximum results (default 20)

        Returns:
            Result containing prioritized PathSteps
        """
        result = await self.backend.get_prioritized_steps(user_uid, limit)
        if result.is_error:
            return Result.fail(result)

        steps = result.value

        self.logger.debug(f"Prioritized PS search returned {len(steps)} results")
        return Result.ok(steps)
