"""
PathStep Core Service
=======================

Core CRUD operations for path steps.

This sub-service handles:
- Step creation and persistence
- Step retrieval (single, list)
- Step updates
- Step deletion
- Path-filtered listings

Part of PsService decomposition (October 24, 2025)
- Follows PsService and LpService decomposition patterns
- Clear separation of concerns
- Single responsibility: CRUD operations

**Architecture (January 2026 Unified):**
- Extends BaseService[BackendOperations[PathStep], PathStep] for unified infrastructure
- Uses specialized Cypher queries for knowledge relationships
- Class attributes match unified domain conventions
- Uses PsBackend methods for graph-native operations
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.curriculum_events import (
    PathStepCreated,
    PathStepDeleted,
    PathStepUpdated,
)
from core.models.pathways.path_step import PathStep
from core.models.pathways.path_step_dto import PathStepDTO
from core.models.type_hints import UserUID
from core.ports import get_enum_value
from core.ports.query_types import PsKnowledgeSummaryResult
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.metrics import track_query_metrics
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.curriculum_protocols import PsOperations

logger = get_logger(__name__)


class PsCoreService(BaseService["PsOperations", PathStep]):
    """
    Core CRUD operations for path steps.

    **Architecture (January 2026 Unified):**
    Extends BaseService[BackendOperations[PathStep], PathStep] for unified infrastructure.
    Uses specialized Cypher queries for knowledge relationships via
    PsBackend named methods (protocol-compliant).

    This service owns:
    - Step creation and persistence to Neo4j
    - Step retrieval (single and list)
    - Step updates (all mutable properties)
    - Step deletion (cascade safe)
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

    def __init__(self, backend: PsOperations, event_bus: Any = None) -> None:
        """
        Initialize core step service.

        FAIL-FAST ARCHITECTURE (per CLAUDE.md):
        The backend is REQUIRED. Services run at full capacity or fail immediately.

        Args:
            backend: BackendOperations[PathStep] for graph operations (REQUIRED)
            event_bus: Event bus for publishing domain events (optional)
        """
        super().__init__(backend, "ps_core")
        self.event_bus = event_bus

    @with_error_handling(operation="create_step", error_type="database", uid_param="step.uid")
    async def create_step(self, step: PathStep, path_uid: str | None = None) -> Result[PathStep]:
        """
        Create a standalone PathStep or add to existing path.

        GRAPH-NATIVE: Knowledge UIDs stored as relationships, not properties.

        Args:
            step: Ls to create
            path_uid: Optional path to add step to

        Returns:
            Result containing created Ls
        """
        # Build params with proper enum value extraction
        params: dict[str, Any] = {
            "uid": step.uid,
            "title": step.title,
            "intent": step.intent,
            "description": step.description,
            "learning_path_uid": step.learning_path_uid,
            "sequence": step.sequence,
            "mastery_threshold": step.mastery_threshold,
            "current_mastery": step.current_mastery,
            "estimated_hours": step.estimated_hours,
            "step_difficulty": get_enum_value(step.step_difficulty),
            "status": get_enum_value(step.status),
            "completed": step.is_completed,
            "domain": get_enum_value(step.domain),
            "knowledge_uids": list(step.knowledge_uids),
            "path_uid": path_uid,
        }

        result = await self.backend.create_step_node(
            params,
            has_knowledge=bool(step.knowledge_uids),
            path_uid=path_uid,
        )

        if result.is_error:
            return Result.fail(
                Errors.database(operation="create_step", message="Step creation failed")
            )

        if not result.value:
            return Result.fail(
                Errors.database(operation="create_step", message="Step creation failed")
            )

        logger.info(f"✅ Created path step {step.uid}")

        # Publish event
        event = PathStepCreated(
            ps_uid=step.uid,
            title=step.title,
            intent=step.intent,
            linked_lp_uid=path_uid,
            linked_ku_uids=step.knowledge_uids,
            sequence_order=step.sequence,
        )
        await publish_event(self.event_bus, event, self.logger)

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        from core.events.embedding_publisher import publish_embedding_requested
        from core.models.enums.entity_enums import EntityType

        await publish_embedding_requested(self.event_bus, EntityType.PATH_STEP, step, self.logger)

        return Result.ok(step)

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

    @with_error_handling(operation="update_step", error_type="database", uid_param="step_uid")
    async def update_step(self, step_uid: str, updates: dict[str, Any]) -> Result[PathStep]:
        """
        Update a path step.

        Args:
            step_uid: Ls UID to update
            updates: Dictionary of fields to update

        Returns:
            Result containing updated Ls
        """
        # First verify step exists
        get_result = await self.get_step(step_uid)
        if get_result.is_error:
            return Result.fail(get_result)

        if not get_result.value:
            return Result.fail(Errors.not_found(resource="path_step", identifier=step_uid))

        # Build SET clause dynamically
        set_clauses = []
        params = {"uid": step_uid}

        # GRAPH-NATIVE: knowledge_uid removed - use relationships instead
        allowed_fields = {
            "title",
            "intent",
            "description",
            "sequence",
            "mastery_threshold",
            "estimated_hours",
            "step_difficulty",
            "status",
            "completed",
            "domain",
        }
        for key, value in updates.items():
            if key in allowed_fields:
                # Handle enum values
                value = get_enum_value(value)
                set_clauses.append(f"s.{key} = ${key}")
                params[key] = value

        if not set_clauses:
            # No valid updates provided, return existing step
            if not get_result.value:
                return Result.fail(Errors.not_found(resource="path_step", identifier=step_uid))
            return Result.ok(get_result.value)

        result = await self.backend.update_step_fields(step_uid, set_clauses, params)

        if result.is_error:
            return Result.fail(
                Errors.database(
                    operation="update_step", message=f"Failed to update step {step_uid}"
                )
            )

        updated_step = result.value
        if updated_step is None:
            return Result.fail(
                Errors.database(
                    operation="update_step", message=f"Failed to update step {step_uid}"
                )
            )

        logger.info(f"Updated path step {step_uid}")

        # Publish event
        event = PathStepUpdated(
            ps_uid=step_uid,
            updated_fields=tuple(updates.keys()),
            linked_lp_uid=updated_step.learning_path_uid,
        )
        await publish_event(self.event_bus, event, self.logger)

        # Post-persist embedding refresh (ADR-074) — only when a text field changed.
        # updated_step is rebuilt from node properties, so the embedding text
        # covers frontmatter fields; PathStep body-content semantics live in
        # CHUNK embeddings (the RAG substrate), not the entity vector.
        from core.events.embedding_publisher import publish_embedding_requested
        from core.models.enums.entity_enums import EntityType

        await publish_embedding_requested(
            self.event_bus,
            EntityType.PATH_STEP,
            updated_step,
            self.logger,
            changed_fields=updates.keys(),
        )

        return Result.ok(updated_step)

    @with_error_handling(operation="delete_step", error_type="database", uid_param="step_uid")
    async def delete_step(self, step_uid: str) -> Result[bool]:
        """
        Delete a path step.

        Args:
            step_uid: Ls UID to delete

        Returns:
            Result[bool] - True if deleted successfully
        """
        # First verify step exists and capture data for event
        get_result = await self.get_step(step_uid)
        if get_result.is_error:
            return Result.fail(get_result)

        if not get_result.value:
            return Result.fail(Errors.not_found(resource="path_step", identifier=step_uid))

        step = get_result.value
        had_ku_links = bool(step.knowledge_uids)
        linked_lp_uid = step.learning_path_uid

        # Delete step and its relationships
        result = await self.backend.delete_step_node(step_uid)

        if result.is_error:
            return Result.fail(
                Errors.database(
                    operation="delete_step", message=f"Failed to delete step {step_uid}"
                )
            )

        records = result.value or []
        deleted_count = records[0]["deleted_count"] if records else 0

        if deleted_count == 0:
            return Result.fail(
                Errors.database(
                    operation="delete_step", message=f"Failed to delete step {step_uid}"
                )
            )

        logger.info(f"✅ Deleted path step {step_uid}")

        # Publish event
        event = PathStepDeleted(
            ps_uid=step_uid,
            linked_lp_uid=linked_lp_uid,
            had_ku_links=had_ku_links,
        )
        await publish_event(self.event_bus, event, self.logger)

        return Result.ok(True)

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
