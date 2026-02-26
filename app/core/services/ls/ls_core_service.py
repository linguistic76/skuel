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
- Follows KuService and LpService decomposition patterns
- Clear separation of concerns
- Single responsibility: CRUD operations

**Architecture (January 2026 Unified):**
- Extends BaseService[BackendOperations[Ls], Ls] for unified infrastructure
- Uses specialized Cypher queries for knowledge relationships
- Class attributes match unified domain conventions
- Uses self.backend.execute_query() for graph-native operations
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.curriculum_events import (
    LearningStepCreated,
    LearningStepDeleted,
    LearningStepUpdated,
)
from core.models.curriculum.learning_step import LearningStep
from core.models.curriculum.learning_step_dto import LearningStepDTO
from core.ports import get_enum_value
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.metrics import track_query_metrics
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from collections.abc import Sequence

    from core.ports import BackendOperations

logger = get_logger(__name__)


class LsCoreService(BaseService["BackendOperations[LearningStep]", LearningStep]):
    """
    Core CRUD operations for learning steps.

    **Architecture (January 2026 Unified):**
    Extends BaseService[BackendOperations[Ls], Ls] for unified infrastructure.
    Uses specialized Cypher queries for knowledge relationships via
    self.backend.execute_query() (protocol-compliant).

    This service owns:
    - Step creation and persistence to Neo4j
    - Step retrieval (single and list)
    - Step updates (all mutable properties)
    - Step deletion (cascade safe)
    - Path-filtered step listings


    Source Tag: "ls_core_explicit"
    - Format: "ls_core_explicit" for user-created relationships
    - Format: "ls_core_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from learning_steps metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Extends BaseService for unified infrastructure
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (uses pure Cypher)
    - Returns Result[T] for error handling
    - Logs operations with structured logging
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

    def __init__(self, backend: BackendOperations[LearningStep], event_bus: Any = None) -> None:
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
        # GRAPH-NATIVE: Create step node with scalar properties only
        # Relationships (knowledge, prerequisites, etc.) stored as edges
        query = """
        CREATE (s:Entity {
            uid: $uid,
            ku_type: 'learning_step',
            title: $title,
            intent: $intent,
            description: $description,
            learning_path_uid: $learning_path_uid,
            sequence: $sequence,
            mastery_threshold: $mastery_threshold,
            current_mastery: $current_mastery,
            estimated_hours: $estimated_hours,
            step_difficulty: $step_difficulty,
            status: $status,
            completed: $completed,
            domain: $domain
        })
        """

        # Create relationships for primary knowledge units
        if step.primary_knowledge_uids:
            query += """
            WITH s
            UNWIND $primary_knowledge_uids AS ku_uid
            MATCH (ku:Entity {uid: ku_uid})
            CREATE (s)-[:REQUIRES_KNOWLEDGE {type: 'primary'}]->(ku)
            """

        # Create relationships for supporting knowledge units
        if step.supporting_knowledge_uids:
            query += """
            WITH s
            UNWIND $supporting_knowledge_uids AS ku_uid
            MATCH (ku:Entity {uid: ku_uid})
            CREATE (s)-[:REQUIRES_KNOWLEDGE {type: 'supporting'}]->(ku)
            """

        # Optionally link to path
        if path_uid:
            query += """
            WITH s
            MATCH (p:Entity {uid: $path_uid})
            CREATE (p)-[:HAS_STEP {sequence: $sequence}]->(s)
            """

        query += """
        WITH s
        RETURN s
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

        result = await self.backend.execute_query(query, params)

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
            occurred_at=datetime.now(UTC),
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
        result = await self.backend.execute_query(
            """
            MATCH (s:Entity {uid: $uid})
            OPTIONAL MATCH (s)-[r:REQUIRES_KNOWLEDGE]->(ku:Entity)
            RETURN s, collect({uid: ku.uid, type: r.type}) as knowledge_rels
            """,
            {"uid": step_uid},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

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
        step_uid = uid  # Alias for backward compatibility in query
        query_result = await self.backend.execute_query(
            """
            MATCH (ls:Entity {uid: $uid})

            // 1. Primary and supporting knowledge
            OPTIONAL MATCH (ls)-[r_ku:REQUIRES_KNOWLEDGE]->(ku:Entity)
            WITH ls, collect({
                uid: ku.uid,
                title: ku.title,
                type: r_ku.type,
                confidence: coalesce(r_ku.confidence, 1.0)
            }) as knowledge_rels

            // 2. Prerequisite steps
            OPTIONAL MATCH (ls)-[:REQUIRES_STEP]->(prereq_step:Entity {ku_type: 'learning_step'})
            WITH ls, knowledge_rels, collect({
                uid: prereq_step.uid,
                title: prereq_step.title,
                completed: prereq_step.completed
            }) as prereq_steps

            // 3. Prerequisite knowledge (separate from content knowledge)
            OPTIONAL MATCH (ls)-[:REQUIRES_KNOWLEDGE {type: 'prerequisite'}]->(prereq_ku:Entity)
            WITH ls, knowledge_rels, prereq_steps, collect({
                uid: prereq_ku.uid,
                title: prereq_ku.title
            }) as prereq_knowledge

            // 4. Guiding principles
            OPTIONAL MATCH (ls)-[:GUIDED_BY_PRINCIPLE]->(principle:Principle)
            WITH ls, knowledge_rels, prereq_steps, prereq_knowledge, collect({
                uid: principle.uid,
                title: principle.title
            }) as principles

            // 5. Offered choices
            OPTIONAL MATCH (ls)-[:OFFERS_CHOICE]->(choice:Choice)
            WITH ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, collect({
                uid: choice.uid,
                title: choice.title
            }) as choices

            // 6. Practice opportunities: Habits
            OPTIONAL MATCH (ls)-[:BUILDS_HABIT]->(habit:Habit)
            WITH ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, collect({
                uid: habit.uid,
                title: habit.title,
                current_streak: habit.current_streak
            }) as habits

            // 7. Practice opportunities: Tasks
            OPTIONAL MATCH (ls)-[:ASSIGNS_TASK]->(task:Task)
            With ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, collect({
                uid: task.uid,
                title: task.title,
                status: task.status
            }) as tasks

            // 8. Practice opportunities: Events
            OPTIONAL MATCH (ls)-[:SCHEDULES_EVENT]->(event:Event)
            WITH ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, collect({
                uid: event.uid,
                title: event.title,
                event_date: event.event_date
            }) as events

            // 9. Learning path context (if part of sequence)
            OPTIONAL MATCH (lp:Entity {ku_type: 'learning_path'})-[r_path:HAS_STEP|CONTAINS_STEP]->(ls)
            WITH ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, events, {
                uid: lp.uid,
                name: lp.title,
                goal: lp.goal,
                sequence: coalesce(r_path.sequence, 0)
            } as path_context

            // 10. Dependent steps (steps that require this one)
            OPTIONAL MATCH (dependent:Entity {ku_type: 'learning_step'})-[:REQUIRES_STEP]->(ls)
            WITH ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, events, path_context, collect({
                uid: dependent.uid,
                title: dependent.title,
                completed: dependent.completed
            }) as dependent_steps

            RETURN ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices,
                   habits, tasks, events, path_context, dependent_steps
            """,
            {"uid": step_uid},
        )

        if query_result.is_error:
            return Result.fail(query_result.expect_error())

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
                    "offered_choices": [c for c in record["choices"] if c.get("uid")],
                    # Practice opportunities
                    "practice_habits": [h for h in record["habits"] if h.get("uid")],
                    "practice_tasks": [t for t in record["tasks"] if t.get("uid")],
                    "practice_events": [e for e in record["events"] if e.get("uid")],
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
                    + len([e for e in record["events"] if e.get("uid")]),
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

        # GRAPH-NATIVE: Query includes knowledge relationships
        query = f"""
        MATCH (s:Entity {{uid: $uid}})
        SET {", ".join(set_clauses)}
        WITH s
        OPTIONAL MATCH (s)-[r:REQUIRES_KNOWLEDGE]->(ku:Entity)
        RETURN s, collect({{uid: ku.uid, type: r.type}}) as knowledge_rels
        """

        result = await self.backend.execute_query(query, params)

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
            occurred_at=datetime.now(UTC),
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
        result = await self.backend.execute_query(
            """
            MATCH (s:Entity {uid: $uid})
            DETACH DELETE s
            RETURN count(s) as deleted_count
            """,
            {"uid": step_uid},
        )

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
            occurred_at=datetime.now(UTC),
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
        # Build dynamic ORDER BY clause
        order_field = f"s.{order_by}" if order_by else "s.sequence"
        order_direction = "DESC" if order_desc else "ASC"

        # Build WHERE clause for optional user_uid filtering
        where_clause = ""
        if user_uid:
            where_clause = "WHERE s.user_uid = $user_uid "

        # GRAPH-NATIVE: Include knowledge relationships in query
        if path_uid:
            # Get steps for specific path
            query = f"""
            MATCH (p:Entity {{uid: $path_uid}})-[:HAS_STEP]->(s:Entity {{ku_type: 'learning_step'}})
            {where_clause}
            OPTIONAL MATCH (s)-[r:REQUIRES_KNOWLEDGE]->(ku:Entity)
            WITH s, collect({{uid: ku.uid, type: r.type}}) as knowledge_rels
            RETURN s, knowledge_rels
            ORDER BY {order_field} {order_direction}
            SKIP $offset
            LIMIT $limit
            """
            params: dict[str, Any] = {"path_uid": path_uid, "limit": limit, "offset": offset}
        else:
            # Get all steps
            query = f"""
            MATCH (s:Entity {{ku_type: 'learning_step'}})
            {where_clause}
            OPTIONAL MATCH (s)-[r:REQUIRES_KNOWLEDGE]->(ku:Entity)
            WITH s, collect({{uid: ku.uid, type: r.type}}) as knowledge_rels
            RETURN s, knowledge_rels
            ORDER BY {order_field} {order_direction}
            SKIP $offset
            LIMIT $limit
            """
            params = {"limit": limit, "offset": offset}

        # Add user_uid to params if filtering by user
        if user_uid:
            params["user_uid"] = user_uid

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

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
    # ========================================================================

    @track_query_metrics("ls_add_knowledge")
    @with_error_handling("add_knowledge_relationship", error_type="database")
    async def add_knowledge_relationship(
        self, ls_uid: str, ku_uid: str, knowledge_type: str = "primary"
    ) -> Result[bool]:
        """
        Create CONTAINS_KNOWLEDGE relationship between LS and KU.

        Universal Hierarchical Pattern: Stores knowledge references as graph
        relationships instead of properties. Supports rich metadata.

        Args:
            ls_uid: Learning Step UID
            ku_uid: Knowledge Unit UID
            knowledge_type: "primary" (core learning) or "supporting" (optional)

        Returns:
            Result[bool] - True if created successfully

        Example:
            # Add primary knowledge
            await ls_service.add_knowledge_relationship(
                ls_uid="ls:abc123",
                ku_uid="ku_python-basics_xyz789",
                knowledge_type="primary"
            )

            # Add supporting knowledge
            await ls_service.add_knowledge_relationship(
                ls_uid="ls:abc123",
                ku_uid="ku_advanced-topics_def456",
                knowledge_type="supporting"
            )

        See: /docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md
        """
        # Validate knowledge_type
        if knowledge_type not in ("primary", "supporting"):
            return Result.fail(
                Errors.validation(
                    f"Invalid knowledge_type: {knowledge_type}. Must be 'primary' or 'supporting'",
                    field="knowledge_type",
                )
            )

        query = """
        MATCH (ls:Entity {uid: $ls_uid})
        MATCH (ku:Entity {uid: $ku_uid})
        MERGE (ls)-[r:CONTAINS_KNOWLEDGE]->(ku)
        SET r.type = $knowledge_type,
            r.created_at = COALESCE(r.created_at, datetime()),
            r.updated_at = datetime()
        RETURN r
        """

        result = await self.backend.execute_query(
            query, {"ls_uid": ls_uid, "ku_uid": ku_uid, "knowledge_type": knowledge_type}
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        success = len(result.value or []) > 0
        if success:
            self.logger.info(
                f"Created CONTAINS_KNOWLEDGE: {ls_uid} -> {ku_uid} (type={knowledge_type})"
            )
        else:
            self.logger.warning(f"Failed to create CONTAINS_KNOWLEDGE: {ls_uid} -> {ku_uid}")

        return Result.ok(success)

    @track_query_metrics("ls_get_knowledge")
    @with_error_handling("get_contained_knowledge", error_type="database")
    async def get_contained_knowledge(
        self, ls_uid: str, knowledge_type: str | None = None
    ) -> Result[list[dict]]:
        """
        Get KUs contained in this Learning Step via CONTAINS_KNOWLEDGE relationships.

        Universal Hierarchical Pattern: Queries graph relationships instead of
        reading properties. Returns KU data with type metadata.

        Args:
            ls_uid: Learning Step UID
            knowledge_type: Filter by "primary" or "supporting" (None = all)

        Returns:
            Result containing list of KU dicts with metadata:
            - uid: KU UID
            - title: KU title
            - type: "primary" or "supporting"
            - domain: KU domain
            - created_at: When relationship was created

        Example:
            # Get all knowledge
            result = await ls_service.get_contained_knowledge("ls:abc123")
            # Returns: [
            # {"uid": "ku_python_xyz", "title": "Python Basics", "type": "primary"},
            # {"uid": "ku_advanced_def", "title": "Advanced", "type": "supporting"}
            # ]

            # Get only primary knowledge
            result = await ls_service.get_contained_knowledge(
                "ls:abc123",
                knowledge_type="primary"
            )

        See: /docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md
        """
        if knowledge_type and knowledge_type not in ("primary", "supporting"):
            return Result.fail(
                Errors.validation(
                    f"Invalid knowledge_type: {knowledge_type}. Must be 'primary', 'supporting', or None",
                    field="knowledge_type",
                )
            )

        # Build query based on filter
        if knowledge_type:
            query = """
            MATCH (ls:Entity {uid: $ls_uid})-[r:CONTAINS_KNOWLEDGE {type: $knowledge_type}]->(ku:Entity)
            RETURN ku.uid as uid,
                   ku.title as title,
                   ku.domain as domain,
                   r.type as type,
                   r.created_at as created_at
            ORDER BY r.created_at, ku.title
            """
            params = {"ls_uid": ls_uid, "knowledge_type": knowledge_type}
        else:
            query = """
            MATCH (ls:Entity {uid: $ls_uid})-[r:CONTAINS_KNOWLEDGE]->(ku:Entity)
            RETURN ku.uid as uid,
                   ku.title as title,
                   ku.domain as domain,
                   r.type as type,
                   r.created_at as created_at
            ORDER BY r.type, r.created_at, ku.title
            """
            params = {"ls_uid": ls_uid}

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        knowledge = [
            {
                "uid": record["uid"],
                "title": record["title"],
                "domain": record["domain"],
                "type": record["type"],
                "created_at": record["created_at"],
            }
            for record in result.value or []
        ]

        self.logger.info(
            f"Found {len(knowledge)} KUs for LS {ls_uid} (type={knowledge_type or 'all'})"
        )

        return Result.ok(knowledge)

    @track_query_metrics("ls_remove_knowledge")
    @with_error_handling("remove_knowledge_relationship", error_type="database")
    async def remove_knowledge_relationship(self, ls_uid: str, ku_uid: str) -> Result[bool]:
        """
        Remove CONTAINS_KNOWLEDGE relationship between LS and KU.

        Universal Hierarchical Pattern: Removes the graph edge while preserving
        both the LS and KU nodes.

        Args:
            ls_uid: Learning Step UID
            ku_uid: Knowledge Unit UID

        Returns:
            Result[bool] - True if removed successfully

        Example:
            await ls_service.remove_knowledge_relationship(
                ls_uid="ls:abc123",
                ku_uid="ku_python_xyz789"
            )

        See: /docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md
        """
        query = """
        MATCH (ls:Entity {uid: $ls_uid})-[r:CONTAINS_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        DELETE r
        RETURN count(r) as deleted
        """

        result = await self.backend.execute_query(query, {"ls_uid": ls_uid, "ku_uid": ku_uid})

        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        deleted = records[0]["deleted"] if records else 0
        success = deleted > 0

        if success:
            self.logger.info(f"Removed CONTAINS_KNOWLEDGE: {ls_uid} -> {ku_uid}")
        else:
            self.logger.warning(f"No CONTAINS_KNOWLEDGE relationship found: {ls_uid} -> {ku_uid}")

        return Result.ok(success)

    @track_query_metrics("ls_get_knowledge_summary")
    @with_error_handling("get_knowledge_summary", error_type="database")
    async def get_knowledge_summary(self, ls_uid: str) -> Result[dict]:
        """
        Get summary of knowledge relationships for a Learning Step.

        Returns counts and lists of both primary and supporting knowledge.

        Args:
            ls_uid: Learning Step UID

        Returns:
            Result containing dict with:
            - primary_count: Number of primary KUs
            - supporting_count: Number of supporting KUs
            - total_count: Total KUs
            - primary_uids: List of primary KU UIDs
            - supporting_uids: List of supporting KU UIDs

        Example:
            result = await ls_service.get_knowledge_summary("ls:abc123")
            # Returns: {
            # "primary_count": 2,
            # "supporting_count": 1,
            # "total_count": 3,
            # "primary_uids": ["ku_python_xyz", "ku_basics_abc"],
            # "supporting_uids": ["ku_advanced_def"]
            # }
        """
        query = """
        MATCH (ls:Entity {uid: $ls_uid})
        OPTIONAL MATCH (ls)-[r:CONTAINS_KNOWLEDGE]->(ku:Entity)
        WITH ls, r, ku
        RETURN
            count(CASE WHEN r.type = 'primary' THEN 1 END) as primary_count,
            count(CASE WHEN r.type = 'supporting' THEN 1 END) as supporting_count,
            count(r) as total_count,
            collect(CASE WHEN r.type = 'primary' THEN ku.uid END) as primary_uids,
            collect(CASE WHEN r.type = 'supporting' THEN ku.uid END) as supporting_uids
        """

        result = await self.backend.execute_query(query, {"ls_uid": ls_uid})

        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        if not records:
            return Result.ok(
                {
                    "primary_count": 0,
                    "supporting_count": 0,
                    "total_count": 0,
                    "primary_uids": [],
                    "supporting_uids": [],
                }
            )

        record = records[0]
        summary = {
            "primary_count": record["primary_count"],
            "supporting_count": record["supporting_count"],
            "total_count": record["total_count"],
            "primary_uids": [uid for uid in record["primary_uids"] if uid],
            "supporting_uids": [uid for uid in record["supporting_uids"] if uid],
        }

        self.logger.info(
            f"Knowledge summary for {ls_uid}: "
            f"{summary['primary_count']} primary, "
            f"{summary['supporting_count']} supporting"
        )

        return Result.ok(summary)
