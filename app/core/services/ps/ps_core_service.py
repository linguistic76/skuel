"""
PathStep Core Service
=======================

Core reads for path steps.

This sub-service handles:
- Step retrieval (single, list)
- Path-filtered listings
- Knowledge summaries

A path step is authored only in the content vault (ADR-091); nothing here
creates, updates or deletes one.

Part of PsService decomposition (October 24, 2025)
- Follows PsService and LpService decomposition patterns
- Clear separation of concerns
- Single responsibility: path step reads

**Architecture (January 2026 Unified):**
- Extends BaseService[BackendOperations[PathStep], PathStep] for unified infrastructure
- Uses specialized Cypher queries for knowledge relationships
- Class attributes match unified domain conventions
- Uses PsBackend methods for graph-native operations
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.pathways.path_step import PathStep
from core.models.pathways.path_step_dto import PathStepDTO
from core.models.type_hints import UserUID
from core.ports.query_types import PsKnowledgeSummaryResult
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.metrics import track_query_metrics
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.curriculum_protocols import PsOperations

logger = get_logger(__name__)


class PsCoreService(BaseService["PsOperations", PathStep]):
    """
    Core reads for path steps.

    **Architecture (January 2026 Unified):**
    Extends BaseService[BackendOperations[PathStep], PathStep] for unified infrastructure.
    Uses specialized Cypher queries for knowledge relationships via
    PsBackend named methods (protocol-compliant).

    This service owns:
    - Step retrieval (single and list)
    - Path-filtered step listings
    """

    # =========================================================================
    # DomainConfig consolidation (January 2026)
    # =========================================================================
    # All configuration in one place, using centralized relationship registry
    # See: /docs/migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md
    _config = create_curriculum_domain_config(
        dto_class=PathStepDTO,
        model_class=PathStep,
        entity_label="Entity",
        domain_name="ps",
        search_fields=("title", "intent", "description"),  # PS-specific fields
        search_order_by="updated_at",
        category_field="nous",  # NOUS topic membership (array — `has` semantics)
        content_field="description",  # PS stores content in description field
    )

    def __init__(self, backend: PsOperations) -> None:
        """
        Initialize core step service.

        FAIL-FAST ARCHITECTURE (per CLAUDE.md):
        The backend is REQUIRED. Services run at full capacity or fail immediately.

        Args:
            backend: BackendOperations[PathStep] for graph operations (REQUIRED)
        """
        super().__init__(backend, "ps_core")

    @with_error_handling(operation="get_step", error_type="database", uid_param="step_uid")
    async def get_step(self, step_uid: str) -> Result[PathStep | None]:
        """
        Get a path step by UID.

        GRAPH-NATIVE: Fetches knowledge relationships from graph.

        Args:
            step_uid: Ls UID

        Returns:
            Result containing Ls or None if not found
        """
        # GRAPH-NATIVE: backend returns the typed model (node + knowledge UIDs)
        result = await self.backend.get_step_with_knowledge(step_uid)

        if result.is_error:
            return Result.fail(result)

        return Result.ok(result.value)

    @with_error_handling(operation="list_steps", error_type="database")
    async def list_steps(
        self,
        path_uid: str | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
        user_uid: UserUID | None = None,
    ) -> Result[list[PathStep]]:
        """
        List path steps with pagination and sorting support.

        Args:
            path_uid: Optional path UID to filter by
            limit: Maximum number of steps to return
            offset: Number of steps to skip (for pagination)
            order_by: Field to sort by (e.g., 'sequence', 'title', 'created_at')
            order_desc: Sort in descending order if True
            user_uid: Optional user UID to filter by (future use)

        Returns:
            Result containing list of Ls
        """
        order_field = f"s.{order_by}" if order_by else "s.sequence"
        order_direction = "DESC" if order_desc else "ASC"

        result = await self.backend.list_steps_raw(
            path_uid=path_uid,
            limit=limit,
            offset=offset,
            order_field=order_field,
            order_direction=order_direction,
            user_uid=user_uid,
        )

        if result.is_error:
            return Result.fail(result)

        steps = result.value or []
        logger.info(f"✅ Listed {len(steps)} path steps")
        return Result.ok(steps)

    # ========================================================================
    # KNOWLEDGE RELATIONSHIP METHODS (Universal Hierarchical Pattern - 2026-01-30)
    # Delegated to PsBackend (2026-03-24)
    # Edge writes happen at ingestion time (registry yaml_field_path
    # "knowledge_uids" → CONTAINS_KNOWLEDGE via ingest_edge).
    # ========================================================================

    @track_query_metrics("ps_get_knowledge_summary")
    @with_error_handling("get_knowledge_summary", error_type="database")
    async def get_knowledge_summary(self, ps_uid: str) -> Result[PsKnowledgeSummaryResult]:
        """Get summary of knowledge relationships (count and UIDs)."""
        result = await self.backend.get_knowledge_summary(ps_uid)
        if result.is_error:
            return Result.fail(result)
        summary = result.value
        self.logger.info(f"Knowledge summary for {ps_uid}: {summary['count']} KUs")
        return result
