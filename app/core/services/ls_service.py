"""
Learning Step Service - Facade
================================

THE single owner for all learning step management in SKUEL.

Delegates to specialized sub-services following unified Curriculum Domain patterns.

Sub-Services:
- LsCoreService: CRUD operations + persistence (extends BaseService)
- LsSearchService: Search operations (extends BaseService)
- LsIntelligenceService: Intelligence operations (extends BaseIntelligenceService)
- UnifiedRelationshipService: All relationship operations

Ls (Learning Step) is one of three core curriculum entities: Ku, Ls, Lp.
Can exist standalone or as part of an Lp. Clusters KUs with practice opportunities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from core.services.ls.ls_ai_service import LsAIService
from core.services.mixins import FacadeDelegationMixin, merge_delegations
from core.utils.logging import get_logger

if TYPE_CHECKING:
    import builtins

    from core.models.ku import Ku
    from core.services.ls.ls_intelligence_service import LsIntelligenceService
    from core.services.protocols.facade_protocols import LsFacadeProtocol
    from core.utils.result_simplified import Result

logger = get_logger(__name__)


class LsService(FacadeDelegationMixin):
    """
    Facade for learning step management.

    Coordinates 4 common sub-services (via factory):
    - Core: CRUD operations + persistence
    - Search: Discovery operations
    - Relationships: Step-path associations
    - Intelligence: Readiness assessment, practice analysis

    **January 2026 - Unified Curriculum Architecture (ADR-030):**
    Uses `create_curriculum_sub_services()` factory for consistent initialization,
    matching Activity Domain patterns exactly.

    Auto-Generated Delegations (via FacadeDelegationMixin):
    - Core: create_step, get_step, update_step, delete_step, list_steps

    Explicit Methods:
    - CRUD compatibility: create, get, update, delete, list (different signatures)
    - Step-path: attach_step_to_path, detach_step_from_path, get_step_paths
      (using UnifiedRelationshipService)

    Source Tag: "ls_explicit"
    - Format: "ls_explicit" for user-created relationships
    - Format: "ls_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from learning_steps metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses FacadeDelegationMixin for auto-generated delegation methods
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    # ========================================================================
    # DELEGATION SPECIFICATION (FacadeDelegationMixin)
    # ========================================================================
    _delegations = merge_delegations(
        # Core CRUD delegations
        {
            "create_step": ("core", "create_step"),
            "get_step": ("core", "get_step"),
            "update_step": ("core", "update_step"),
            "delete_step": ("core", "delete_step"),
            "list_steps": ("core", "list_steps"),
        },
        # Note: Step-path relationship methods (attach_step_to_path, etc.)
        # are now explicit methods using UnifiedRelationshipService
    )

    def __init__(
        self,
        backend: Any = None,
        executor: Any = None,
        graph_intel: Any = None,
        event_bus: Any = None,
        ai_service: LsAIService | None = None,
    ) -> None:
        """
        Initialize facade with sub-services via factory.

        FAIL-FAST ARCHITECTURE (per CLAUDE.md):
        Backend and graph_intel are REQUIRED. Services run at full capacity or fail immediately.

        **January 2026 - Unified Curriculum Architecture (ADR-030):**
        Uses `create_curriculum_sub_services()` factory for consistent initialization,
        matching Activity Domain patterns exactly.

        Args:
            backend: BackendOperations for LS entities (REQUIRED — created by composition root)
            executor: Query executor (REQUIRED for persistence)
            graph_intel: GraphIntelligenceService for cross-domain queries (REQUIRED)
            event_bus: Event bus for publishing domain events (optional)
        """
        if not backend:
            raise ValueError(
                "LsService backend is REQUIRED. "
                "SKUEL follows fail-fast architecture - all required dependencies "
                "must be provided at initialization."
            )
        if not executor:
            raise ValueError(
                "LsService executor is REQUIRED. "
                "SKUEL follows fail-fast architecture - all required dependencies "
                "must be provided at initialization."
            )
        if not graph_intel:
            raise ValueError(
                "LsService graph_intel is REQUIRED. "
                "SKUEL follows fail-fast architecture - graph intelligence enables "
                "cross-domain queries for curriculum domains."
            )

        from core.utils.curriculum_domain_config import (
            CurriculumCommonSubServices,
            create_curriculum_sub_services,
        )

        # Create 4 common sub-services via factory (January 2026 - ADR-030)
        # This matches Activity Domain patterns exactly
        common: CurriculumCommonSubServices[LsIntelligenceService] = create_curriculum_sub_services(
            domain="ls",
            backend=backend,
            graph_intel=graph_intel,
            event_bus=event_bus,
        )

        # Assign sub-services from factory
        self.core = common.core
        self.search = common.search
        self.relationships = common.relationships
        self.intelligence: LsIntelligenceService = common.intelligence

        # Store dependencies
        self.executor = executor
        self.event_bus = event_bus
        self.ai: LsAIService | None = ai_service
        self.logger = logger

        logger.debug("LsService facade initialized with 4 sub-services via factory (ADR-030)")

    # ============================================================================
    # CORE CRUD OPERATIONS - Delegated to LsCoreService
    # ============================================================================
    # Note: Simple delegations (create_step, get_step, update_step, delete_step,
    # list_steps) auto-generated by FacadeDelegationMixin.

    # ============================================================================
    # RELATIONSHIP OPERATIONS - Delegated to LsRelationshipService
    # ============================================================================
    # Note: Simple delegations (attach_step_to_path, detach_step_from_path,
    # get_step_paths, reorder_path_steps, get_path_step_count)
    # auto-generated by FacadeDelegationMixin.

    # ============================================================================
    # CRUD OPERATIONS PROTOCOL COMPATIBILITY
    # ============================================================================
    # These methods make LsService compatible with CRUDRouteFactory

    async def create(self, entity: Ku) -> Result[Ku]:
        """Create method for CRUDRouteFactory compatibility."""
        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_self = cast("LsFacadeProtocol", self)
        return await typed_self.create_step(entity)

    async def get(self, uid: str) -> Result[Ku | None]:
        """Get method for CRUDRouteFactory compatibility."""
        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_self = cast("LsFacadeProtocol", self)
        return await typed_self.get_step(uid)

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[Ku]:
        """Update method for CRUDRouteFactory compatibility."""
        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_self = cast("LsFacadeProtocol", self)
        return await typed_self.update_step(uid, updates)

    async def delete(self, uid: str) -> Result[bool]:
        """Delete method for CRUDRouteFactory compatibility."""
        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_self = cast("LsFacadeProtocol", self)
        return await typed_self.delete_step(uid)

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
        user_uid: str | None = None,
    ) -> Result[builtins.list[Ku]]:
        """
        List learning steps with pagination and sorting support.

        CRUDRouteFactory compatible method with full filtering/sorting.

        Args:
            limit: Maximum number of steps to return
            offset: Number of steps to skip (for pagination)
            order_by: Field to sort by (e.g., 'sequence', 'title', 'created_at')
            order_desc: Sort in descending order if True
            user_uid: User filter (reserved for future use)
        """
        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_self = cast("LsFacadeProtocol", self)
        return await typed_self.list_steps(
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_desc=order_desc,
            user_uid=user_uid,  # Pass through for future user filtering
        )

    # ============================================================================
    # STEP-PATH RELATIONSHIP OPERATIONS (UnifiedRelationshipService)
    # ============================================================================

    async def attach_step_to_path(
        self, step_uid: str, path_uid: str, sequence: int | None = None
    ) -> Result[bool]:
        """
        Attach an existing learning step to a learning path.

        Creates HAS_STEP relationship from path to step.
        If sequence not provided, appends to end of path.

        Args:
            step_uid: Learning step UID
            path_uid: Learning path UID
            sequence: Optional sequence number (auto-calculated if None)

        Returns:
            Result[bool] - True if relationship created successfully
        """
        # If sequence not provided, get max sequence + 1 via direct query
        if sequence is None:
            seq_query = """
            MATCH (p:Ku {uid: $path_uid})-[r:HAS_STEP]->()
            RETURN coalesce(max(r.sequence), -1) + 1 as next_sequence
            """
            seq_result = await self.executor.execute_query(seq_query, {"path_uid": path_uid})
            if seq_result.is_error:
                sequence = 0
            else:
                records = seq_result.value
                sequence = records[0]["next_sequence"] if records else 0

        # Create relationship via UnifiedRelationshipService
        # LS config has "in_paths" as incoming HAS_STEP from LP
        return await self.relationships.create_relationship_with_properties(
            relationship_key="in_paths",
            from_uid=step_uid,
            to_uid=path_uid,
            edge_properties={"sequence": sequence, "completed": False},
        )

    async def detach_step_from_path(self, step_uid: str, path_uid: str) -> Result[bool]:
        """
        Detach a learning step from a learning path.

        Removes HAS_STEP relationship but keeps step node intact.

        Args:
            step_uid: Learning step UID
            path_uid: Learning path UID

        Returns:
            Result[bool] - True if relationship deleted successfully
        """
        return await self.relationships.delete_relationship(
            relationship_key="in_paths",
            from_uid=step_uid,
            to_uid=path_uid,
        )

    async def get_step_paths(self, step_uid: str, limit: int = 100) -> Result[builtins.list[str]]:
        """
        Get all learning paths that contain a specific step.

        Args:
            step_uid: Learning step UID
            limit: Maximum number of paths to return (Note: limit not used in URS call)

        Returns:
            Result containing list of path UIDs
        """
        return await self.relationships.get_related_uids("in_paths", step_uid)
