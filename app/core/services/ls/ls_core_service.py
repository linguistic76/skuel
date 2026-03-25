"""
Learning Step Core Service
============================

Core CRUD operations for learning steps.

This sub-service handles:
- Step creation and persistence
- Step retrieval (single, list)
- Step updates
- Step deletion
- Path-filtered listings

Part of LsService decomposition (October 24, 2025)
- Follows LessonService and LpService decomposition patterns
- Clear separation of concerns
- Single responsibility: CRUD operations

**Architecture (January 2026 Unified):**
- Extends BaseService[BackendOperations[Ls], Ls] for unified infrastructure
- Uses specialized Cypher queries for knowledge relationships
- Class attributes match unified domain conventions
- Uses LsBackend methods for graph-native operations
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.curriculum_events import (
    LearningStepCreated,
    LearningStepDeleted,
    LearningStepUpdated,
)
from core.models.pathways.learning_step import LearningStep
from core.models.pathways.learning_step_dto import LearningStepDTO
from core.ports import get_enum_value
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.metrics import track_query_metrics
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from collections.abc import Sequence

    from core.ports.curriculum_protocols import LsOperations

logger = get_logger(__name__)


class LsCoreService(BaseService["LsOperations", LearningStep]):
    """
    Core CRUD operations for learning steps.

    **Architecture (January 2026 Unified):**
    Extends BaseService[BackendOperations[Ls], Ls] for unified infrastructure.
    Uses specialized Cypher queries for knowledge relationships via
    LsBackend named methods (protocol-compliant).

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
        dto_class=LearningStepDTO,
        model_class=LearningStep,
        entity_label="Entity",
        domain_name="ls",
        search_fields=("title", "intent", "description"),  # LS-specific fields
        search_order_by="updated_at",
        content_field="description",  # LS stores content in description field
    )

    @property
    def entity_label(self) -> str:
        """Entity label for Neo4j queries."""
        return "Entity"

    def __init__(self, backend: LsOperations, event_bus: Any = None) -> None:
        """
        Initialize core step service.

        FAIL-FAST ARCHITECTURE (per CLAUDE.md):
        The backend is REQUIRED. Services run at full capacity or fail immediately.

        Args:
            backend: BackendOperations[Ls] for graph operations (REQUIRED)
            event_bus: Event bus for publishing domain events (optional)
        """
        super().__init__(backend, "ls_core")
        self.event_bus = event_bus

    @with_error_handling(operation="create_step", error_type="database", uid_param="step.uid")
    async def create_step(
        self, step: LearningStep, path_uid: str | None = None
    ) -> Result[LearningStep]:
        """
        Create a standalone Ls or add to existing path.

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
            "primary_knowledge_uids": list(step.primary_knowledge_uids),
            "supporting_knowledge_uids": list(step.supporting_knowledge_uids),
            "path_uid": path_uid,
        }

        result = await self.backend.create_step_node(
            params,
            has_primary_knowledge=bool(step.primary_knowledge_uids),
            has_supporting_knowledge=bool(step.supporting_knowledge_uids),
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

        logger.info(f"✅ Created learning step {step.uid}")

        # Publish event
        event = LearningStepCreated(
            ls_uid=step.uid,
            title=step.title,
            intent=step.intent,
            linked_lp_uid=path_uid,
            linked_ku_uids=step.primary_knowledge_uids + step.supporting_knowledge_uids,
            sequence_order=step.sequence,
        )
        await publish_event(self.event_bus, event, self.logger)

        return Result.ok(step)

    @with_error_handling(operation="get_step", error_type="database", uid_param="step_uid")
    async def get_step(self, step_uid: str) -> Result[LearningStep | None]:
        """
        Get a learning step by UID.

        GRAPH-NATIVE: Fetches knowledge relationships from graph.

        Args:
            step_uid: Ls UID

        Returns:
            Result containing Ls or None if not found
        """
        # GRAPH-NATIVE: Query node + knowledge relationships
        result = await self.backend.get_step_with_knowledge(step_uid)

        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        if not records:
            return Result.ok(None)

        record = records[0]
        step_data = record["s"]
        knowledge_rels = record["knowledge_rels"]

        # Separate primary and supporting knowledge from relationships
        primary_uids = []
        supporting_uids = []
        for rel in knowledge_rels:
            if rel["uid"]:  # Skip empty relationships
                if rel.get("type") == "supporting":
                    supporting_uids.append(rel["uid"])
                else:
                    # Default to primary if type not specified
                    primary_uids.append(rel["uid"])

        step = LearningStep(
            uid=step_data["uid"],
            title=step_data.get("title", "Learning Step"),
            intent=step_data.get("intent", "Complete this learning step"),
            description=step_data.get("description"),
            primary_knowledge_uids=tuple(primary_uids),
            supporting_knowledge_uids=tuple(supporting_uids),
            learning_path_uid=step_data.get("learning_path_uid"),
            sequence=step_data.get("sequence"),
            mastery_threshold=step_data.get("mastery_threshold", 0.7),
            current_mastery=step_data.get("current_mastery", 0.0),
            estimated_hours=step_data.get("estimated_hours", 1.0),
            step_difficulty=step_data.get("step_difficulty"),
            status=step_data.get("status"),
            domain=step_data.get("domain", "PERSONAL"),
        )

        return Result.ok(step)

    @with_error_handling(operation="get_with_context", error_type="database", uid_param="uid")
    async def get_with_context(
        self,
        uid: str,
        depth: int = 2,
        min_confidence: float = 0.7,
        include_relationships: Sequence[str] | None = None,
        exclude_relationships: Sequence[str] | None = None,
    ) -> Result[LearningStep]:
        """
        Get learning step with comprehensive graph context (SINGLE QUERY).

        Overrides BaseService.get_with_context() with LS-specific graph patterns.

        Rich Context Pattern: Fetches step + all graph neighborhoods in one query:
        - Primary and supporting knowledge
        - Prerequisite steps and knowledge
        - Guiding principles and offered choices
        - Practice opportunities (habits, tasks, events)
        - Learning path context (if sequenced)
        - Dependent steps (steps that require this one)

        All context stored in step.metadata["graph_context"].

        Args:
            uid: Ls UID
            depth: Graph traversal depth (not used - fixed depth query)
            min_confidence: Minimum relationship confidence (not used - specialized query)
            include_relationships: Relationships to include (not used - specialized query)
            exclude_relationships: Relationships to exclude (not used - specialized query)

        Returns:
            Result containing Ls with enriched metadata
        """
        # Note: depth and min_confidence are accepted for API compatibility
        # but this implementation uses a fixed specialized query
        step_uid = uid
        query_result = await self.backend.get_step_with_context(step_uid)

        if query_result.is_error:
            return Result.fail(query_result)

        records = query_result.value or []
        if not records:
            return Result.fail(Errors.not_found(resource="learning_step", identifier=step_uid))

        record = records[0]
        step_data = record["ls"]

        # Separate primary and supporting knowledge from relationships
        primary_uids = []
        supporting_uids = []
        for rel in record["knowledge_rels"]:
            if rel.get("uid"):  # Skip empty relationships
                if rel.get("type") == "supporting":
                    supporting_uids.append(rel["uid"])
                else:
                    primary_uids.append(rel["uid"])

        # Build LearningStep with knowledge UIDs
        step = LearningStep(
            uid=step_data["uid"],
            title=step_data.get("title", "Learning Step"),
            intent=step_data.get("intent", "Complete this learning step"),
            description=step_data.get("description"),
            primary_knowledge_uids=tuple(primary_uids),
            supporting_knowledge_uids=tuple(supporting_uids),
            learning_path_uid=step_data.get("learning_path_uid"),
            sequence=step_data.get("sequence"),
            mastery_threshold=step_data.get("mastery_threshold", 0.7),
            current_mastery=step_data.get("current_mastery", 0.0),
            estimated_hours=step_data.get("estimated_hours", 1.0),
            step_difficulty=step_data.get("step_difficulty"),
            status=step_data.get("status"),
            domain=step_data.get("domain", "PERSONAL"),
        )

        # Enrich with graph context in metadata
        object.__setattr__(
            step,
            "metadata",
            {
                "graph_context": {
                    # Knowledge content (detailed)
                    "knowledge_relationships": [
                        rel for rel in record["knowledge_rels"] if rel.get("uid")
                    ],
                    # Prerequisites
                    "prerequisite_steps": [s for s in record["prereq_steps"] if s.get("uid")],
                    "prerequisite_knowledge": [
                        k for k in record["prereq_knowledge"] if k.get("uid")
                    ],
                    # Learning guidance
                    "guiding_principles": [p for p in record["principles"] if p.get("uid")],
                    "informed_choices": [c for c in record["choices"] if c.get("uid")],
                    # Practice opportunities (all 6 activity domains)
                    "practice_habits": [h for h in record["habits"] if h.get("uid")],
                    "practice_tasks": [t for t in record["tasks"] if t.get("uid")],
                    "practice_events": [e for e in record["events"] if e.get("uid")],
                    "practice_goals": [g for g in record["goals"] if g.get("uid")],
                    # Path integration
                    "learning_path": record["path_context"]
                    if record["path_context"].get("uid")
                    else None,
                    # Dependencies
                    "dependent_steps": [d for d in record["dependent_steps"] if d.get("uid")],
                    # Aggregates
                    "total_prerequisites": len([s for s in record["prereq_steps"] if s.get("uid")]),
                    "total_practice_opportunities": len(
                        [h for h in record["habits"] if h.get("uid")]
                    )
                    + len([t for t in record["tasks"] if t.get("uid")])
                    + len([e for e in record["events"] if e.get("uid")])
                    + len([g for g in record["goals"] if g.get("uid")]),
                    "is_sequenced": bool(record["path_context"].get("uid")),
                    "has_dependents": len([d for d in record["dependent_steps"] if d.get("uid")])
                    > 0,
                }
            },
        )

        logger.info(
            f"Retrieved step with context: {step_uid} "
            f"(prereqs: {len([s for s in record['prereq_steps'] if s.get('uid')])}, "
            f"practice: {len([h for h in record['habits'] if h.get('uid')]) + len([t for t in record['tasks'] if t.get('uid')])}, "
            f"dependents: {len([d for d in record['dependent_steps'] if d.get('uid')])})"
        )

        return Result.ok(step)

    @with_error_handling(operation="update_step", error_type="database", uid_param="step_uid")
    async def update_step(self, step_uid: str, updates: dict[str, Any]) -> Result[LearningStep]:
        """
        Update a learning step.

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
            return Result.fail(Errors.not_found(resource="learning_step", identifier=step_uid))

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
                return Result.fail(Errors.not_found(resource="learning_step", identifier=step_uid))
            return Result.ok(get_result.value)

        result = await self.backend.update_step_fields(step_uid, set_clauses, params)

        if result.is_error:
            return Result.fail(
                Errors.database(
                    operation="update_step", message=f"Failed to update step {step_uid}"
                )
            )

        records = result.value or []
        if not records:
            return Result.fail(
                Errors.database(
                    operation="update_step", message=f"Failed to update step {step_uid}"
                )
            )

        record = records[0]
        step_data = record["s"]
        knowledge_rels = record["knowledge_rels"]

        # Separate primary and supporting knowledge
        primary_uids = []
        supporting_uids = []
        for rel in knowledge_rels:
            if rel["uid"]:
                if rel.get("type") == "supporting":
                    supporting_uids.append(rel["uid"])
                else:
                    primary_uids.append(rel["uid"])

        updated_step = LearningStep(
            uid=step_data["uid"],
            title=step_data.get("title", "Learning Step"),
            intent=step_data.get("intent", "Complete this learning step"),
            description=step_data.get("description"),
            primary_knowledge_uids=tuple(primary_uids),
            supporting_knowledge_uids=tuple(supporting_uids),
            learning_path_uid=step_data.get("learning_path_uid"),
            sequence=step_data.get("sequence"),
            mastery_threshold=step_data.get("mastery_threshold", 0.7),
            current_mastery=step_data.get("current_mastery", 0.0),
            estimated_hours=step_data.get("estimated_hours", 1.0),
            step_difficulty=step_data.get("step_difficulty"),
            status=step_data.get("status"),
            domain=step_data.get("domain", "PERSONAL"),
        )

        logger.info(f"Updated learning step {step_uid}")

        # Publish event
        event = LearningStepUpdated(
            ls_uid=step_uid,
            updated_fields=tuple(updates.keys()),
            linked_lp_uid=updated_step.learning_path_uid,
        )
        await publish_event(self.event_bus, event, self.logger)

        return Result.ok(updated_step)

    @with_error_handling(operation="delete_step", error_type="database", uid_param="step_uid")
    async def delete_step(self, step_uid: str) -> Result[bool]:
        """
        DETACH DELETE a learning step.

        Args:
            step_uid: Ls UID to DETACH DELETE

        Returns:
            Result[bool] - True if deleted successfully
        """
        # First verify step exists and capture data for event
        get_result = await self.get_step(step_uid)
        if get_result.is_error:
            return Result.fail(get_result)

        if not get_result.value:
            return Result.fail(Errors.not_found(resource="learning_step", identifier=step_uid))

        step = get_result.value
        had_ku_links = bool(step.primary_knowledge_uids or step.supporting_knowledge_uids)
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

        logger.info(f"✅ Deleted learning step {step_uid}")

        # Publish event
        event = LearningStepDeleted(
            ls_uid=step_uid,
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
        user_uid: str | None = None,
    ) -> Result[list[LearningStep]]:
        """
        List learning steps with pagination and sorting support.

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

        steps = []
        for record in result.value or []:
            step_data = record["s"]
            knowledge_rels = record["knowledge_rels"]

            # Separate primary and supporting knowledge
            primary_uids = []
            supporting_uids = []
            for rel in knowledge_rels:
                if rel["uid"]:
                    if rel.get("type") == "supporting":
                        supporting_uids.append(rel["uid"])
                    else:
                        primary_uids.append(rel["uid"])

            steps.append(
                LearningStep(
                    uid=step_data["uid"],
                    title=step_data.get("title", "Learning Step"),
                    intent=step_data.get("intent", "Complete this learning step"),
                    description=step_data.get("description"),
                    primary_knowledge_uids=tuple(primary_uids),
                    supporting_knowledge_uids=tuple(supporting_uids),
                    learning_path_uid=step_data.get("learning_path_uid"),
                    sequence=step_data.get("sequence"),
                    mastery_threshold=step_data.get("mastery_threshold", 0.7),
                    current_mastery=step_data.get("current_mastery", 0.0),
                    estimated_hours=step_data.get("estimated_hours", 1.0),
                    step_difficulty=step_data.get("step_difficulty"),
                    status=step_data.get("status"),
                    domain=step_data.get("domain", "PERSONAL"),
                )
            )

        logger.info(f"✅ Listed {len(steps)} learning steps")
        return Result.ok(steps)

    # ========================================================================
    # KNOWLEDGE RELATIONSHIP METHODS (Universal Hierarchical Pattern - 2026-01-30)
    # Delegated to LsBackend (2026-03-24)
    # ========================================================================

    @track_query_metrics("ls_add_knowledge")
    @with_error_handling("add_knowledge_relationship", error_type="database")
    async def add_knowledge_relationship(
        self, ls_uid: str, ku_uid: str, knowledge_type: str = "primary"
    ) -> Result[bool]:
        """Create CONTAINS_KNOWLEDGE relationship between LS and KU."""
        if knowledge_type not in ("primary", "supporting"):
            return Result.fail(
                Errors.validation(
                    f"Invalid knowledge_type: {knowledge_type}. Must be 'primary' or 'supporting'",
                    field="knowledge_type",
                )
            )
        return await self.backend.add_knowledge(ls_uid, ku_uid, knowledge_type)

    @track_query_metrics("ls_get_knowledge")
    @with_error_handling("get_contained_knowledge", error_type="database")
    async def get_contained_knowledge(
        self, ls_uid: str, knowledge_type: str | None = None
    ) -> Result[list[dict]]:
        """Get KUs contained in this LS via CONTAINS_KNOWLEDGE relationships."""
        if knowledge_type and knowledge_type not in ("primary", "supporting"):
            return Result.fail(
                Errors.validation(
                    f"Invalid knowledge_type: {knowledge_type}. Must be 'primary', 'supporting', or None",
                    field="knowledge_type",
                )
            )
        result = await self.backend.list_knowledge(ls_uid, knowledge_type)
        if result.is_error:
            return Result.fail(result)
        self.logger.info(
            f"Found {len(result.value)} KUs for LS {ls_uid} (type={knowledge_type or 'all'})"
        )
        return result

    @track_query_metrics("ls_remove_knowledge")
    @with_error_handling("remove_knowledge_relationship", error_type="database")
    async def remove_knowledge_relationship(self, ls_uid: str, ku_uid: str) -> Result[bool]:
        """Remove CONTAINS_KNOWLEDGE relationship between LS and KU."""
        result = await self.backend.remove_knowledge(ls_uid, ku_uid)
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            self.logger.warning(f"No CONTAINS_KNOWLEDGE relationship found: {ls_uid} -> {ku_uid}")
        return result

    @track_query_metrics("ls_get_knowledge_summary")
    @with_error_handling("get_knowledge_summary", error_type="database")
    async def get_knowledge_summary(self, ls_uid: str) -> Result[dict]:
        """Get summary of knowledge relationships (primary/supporting counts and UIDs)."""
        result = await self.backend.get_knowledge_summary(ls_uid)
        if result.is_error:
            return Result.fail(result)
        summary = result.value
        self.logger.info(
            f"Knowledge summary for {ls_uid}: "
            f"{summary['primary_count']} primary, "
            f"{summary['supporting_count']} supporting"
        )
        return result
