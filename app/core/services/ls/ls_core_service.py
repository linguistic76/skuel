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
- Accesses driver via self.backend.driver for graph-native operations
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
from core.models.ls import Ls
from core.models.ls.ls_dto import LearningStepDTO
from core.models.relationship_names import RelationshipName
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.services.protocols import get_enum_value
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from collections.abc import Sequence

    from core.services.protocols import BackendOperations

logger = get_logger(__name__)


class LsCoreService(BaseService["BackendOperations[Ls]", Ls]):
    """
    Core CRUD operations for learning steps.

    **Architecture (January 2026 Unified):**
    Extends BaseService[BackendOperations[Ls], Ls] for unified infrastructure.
    Uses specialized Cypher queries for knowledge relationships via
    self.backend.driver (no wrapper backend needed).

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
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    # =========================================================================
    # DomainConfig consolidation (January 2026 Phase 3)
    # =========================================================================
    # All configuration in one place, using centralized relationship registry
    # See: /docs/migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md
    _config = create_curriculum_domain_config(
        dto_class=LearningStepDTO,
        model_class=Ls,
        domain_name="ls",
        search_fields=("title", "intent", "description"),  # LS-specific fields
        search_order_by="updated_at",
        content_field="description",  # LS stores content in description field
    )

    @property
    def entity_label(self) -> str:
        """Entity label for Neo4j queries."""
        return "Ls"

    def __init__(self, backend: BackendOperations[Ls], event_bus: Any = None) -> None:
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
    async def create_step(self, step: Ls, path_uid: str | None = None) -> Result[Ls]:
        """
        Create a standalone Ls or add to existing path.

        GRAPH-NATIVE: Knowledge UIDs stored as relationships, not properties.

        Args:
            step: Ls to create
            path_uid: Optional path to add step to

        Returns:
            Result containing created Ls
        """
        async with self.backend.driver.session() as session:
            # GRAPH-NATIVE: Create step node with scalar properties only
            # Relationships (knowledge, prerequisites, etc.) stored as edges
            query = """
            CREATE (s:Ls {
                uid: $uid,
                title: $title,
                intent: $intent,
                description: $description,
                learning_path_uid: $learning_path_uid,
                sequence: $sequence,
                mastery_threshold: $mastery_threshold,
                current_mastery: $current_mastery,
                estimated_hours: $estimated_hours,
                difficulty: $difficulty,
                status: $status,
                completed: $completed,
                completed_at: $completed_at,
                domain: $domain,
                priority: $priority
            })
            """

            # Create relationships for primary knowledge units
            if step.primary_knowledge_uids:
                query += """
                WITH s
                UNWIND $primary_knowledge_uids AS ku_uid
                MATCH (ku:Ku {uid: ku_uid})
                CREATE (s)-[:REQUIRES_KNOWLEDGE {type: 'primary'}]->(ku)
                """

            # Create relationships for supporting knowledge units
            if step.supporting_knowledge_uids:
                query += """
                WITH s
                UNWIND $supporting_knowledge_uids AS ku_uid
                MATCH (ku:Ku {uid: ku_uid})
                CREATE (s)-[:REQUIRES_KNOWLEDGE {type: 'supporting'}]->(ku)
                """

            # Optionally link to path
            if path_uid:
                query += """
                WITH s
                MATCH (p:Lp {uid: $path_uid})
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
                "difficulty": get_enum_value(step.difficulty),
                "status": get_enum_value(step.status),
                "completed": step.completed,
                "completed_at": step.completed_at.isoformat() if step.completed_at else None,
                "domain": get_enum_value(step.domain),
                "priority": get_enum_value(step.priority),
                "primary_knowledge_uids": list(step.primary_knowledge_uids),
                "supporting_knowledge_uids": list(step.supporting_knowledge_uids),
                "path_uid": path_uid,
            }

            result = await session.run(query, params)

            record = await result.single()
            if not record:
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
    async def get_step(self, step_uid: str) -> Result[Ls | None]:
        """
        Get a learning step by UID.

        GRAPH-NATIVE: Fetches knowledge relationships from graph.

        Args:
            step_uid: Ls UID

        Returns:
            Result containing Ls or None if not found
        """
        async with self.backend.driver.session() as session:
            # GRAPH-NATIVE: Query node + knowledge relationships
            result = await session.run(
                """
                MATCH (s:Ls {uid: $uid})
                OPTIONAL MATCH (s)-[r:REQUIRES_KNOWLEDGE]->(ku:Ku)
                RETURN s, collect({uid: ku.uid, type: r.type}) as knowledge_rels
                """,
                uid=step_uid,
            )

            record = await result.single()
            if not record:
                return Result.ok(None)

            step_data = dict(record["s"])
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

            step = Ls(
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
                difficulty=step_data.get("difficulty", "MODERATE"),
                status=step_data.get("status", "NOT_STARTED"),
                completed=step_data.get("completed", False),
                completed_at=step_data.get("completed_at"),
                domain=step_data.get("domain", "PERSONAL"),
                priority=step_data.get("priority", "MEDIUM"),
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
    ) -> Result[Ls]:
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
        async with self.backend.driver.session() as session:
            result = await session.run(
                """
                MATCH (ls:Ls {uid: $uid})

                // 1. Primary and supporting knowledge
                OPTIONAL MATCH (ls)-[r_ku:REQUIRES_KNOWLEDGE]->(ku:Ku)
                WITH ls, collect({
                    uid: ku.uid,
                    title: ku.title,
                    type: r_ku.type,
                    confidence: coalesce(r_ku.confidence, 1.0)
                }) as knowledge_rels

                // 2. Prerequisite steps
                OPTIONAL MATCH (ls)-[:REQUIRES_STEP]->(prereq_step:Ls)
                WITH ls, knowledge_rels, collect({
                    uid: prereq_step.uid,
                    title: prereq_step.title,
                    completed: prereq_step.completed
                }) as prereq_steps

                // 3. Prerequisite knowledge (separate from content knowledge)
                OPTIONAL MATCH (ls)-[:REQUIRES_KNOWLEDGE {type: 'prerequisite'}]->(prereq_ku:Ku)
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
                WITH ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, collect({
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
                OPTIONAL MATCH (lp:Lp)-[r_path:HAS_STEP|CONTAINS_STEP]->(ls)
                WITH ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, events, {
                    uid: lp.uid,
                    name: lp.name,
                    goal: lp.goal,
                    sequence: coalesce(r_path.sequence, 0)
                } as path_context

                // 10. Dependent steps (steps that require this one)
                OPTIONAL MATCH (dependent:Ls)-[:REQUIRES_STEP]->(ls)
                WITH ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, events, path_context, collect({
                    uid: dependent.uid,
                    title: dependent.title,
                    completed: dependent.completed
                }) as dependent_steps

                RETURN ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices,
                       habits, tasks, events, path_context, dependent_steps
                """,
                uid=step_uid,
            )

            record = await result.single()
            if not record:
                return Result.fail(Errors.not_found(resource="Ls", identifier=step_uid))

            step_data = dict(record["ls"])

            # Separate primary and supporting knowledge from relationships
            primary_uids = []
            supporting_uids = []
            for rel in record["knowledge_rels"]:
                if rel.get("uid"):  # Skip empty relationships
                    if rel.get("type") == "supporting":
                        supporting_uids.append(rel["uid"])
                    else:
                        primary_uids.append(rel["uid"])

            # Build Ls with knowledge UIDs
            step = Ls(
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
                difficulty=step_data.get("difficulty", "MODERATE"),
                status=step_data.get("status", "NOT_STARTED"),
                completed=step_data.get("completed", False),
                completed_at=step_data.get("completed_at"),
                domain=step_data.get("domain", "PERSONAL"),
                priority=step_data.get("priority", "MEDIUM"),
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
                        "total_prerequisites": len(
                            [s for s in record["prereq_steps"] if s.get("uid")]
                        ),
                        "total_practice_opportunities": len(
                            [h for h in record["habits"] if h.get("uid")]
                        )
                        + len([t for t in record["tasks"] if t.get("uid")])
                        + len([e for e in record["events"] if e.get("uid")]),
                        "is_sequenced": bool(record["path_context"].get("uid")),
                        "has_dependents": len(
                            [d for d in record["dependent_steps"] if d.get("uid")]
                        )
                        > 0,
                    }
                },
            )

            logger.info(
                f"✅ Retrieved step with context: {step_uid} "
                f"(prereqs: {len([s for s in record['prereq_steps'] if s.get('uid')])}, "
                f"practice: {len([h for h in record['habits'] if h.get('uid')]) + len([t for t in record['tasks'] if t.get('uid')])}, "
                f"dependents: {len([d for d in record['dependent_steps'] if d.get('uid')])})"
            )

            return Result.ok(step)

    @with_error_handling(operation="update_step", error_type="database", uid_param="step_uid")
    async def update_step(self, step_uid: str, updates: dict[str, Any]) -> Result[Ls]:
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
            return Result.fail(Errors.not_found(resource="Ls", identifier=step_uid))

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
            "difficulty",
            "status",
            "completed",
            "domain",
            "priority",
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
                return Result.fail(Errors.not_found(resource="Ls", identifier=step_uid))
            return Result.ok(get_result.value)

        async with self.backend.driver.session() as session:
            # GRAPH-NATIVE: Query includes knowledge relationships
            query = f"""
            MATCH (s:Ls {{uid: $uid}})
            SET {", ".join(set_clauses)}
            WITH s
            OPTIONAL MATCH (s)-[r:REQUIRES_KNOWLEDGE]->(ku:Ku)
            RETURN s, collect({{uid: ku.uid, type: r.type}}) as knowledge_rels
            """

            result = await session.run(query, params)
            record = await result.single()

            if not record:
                return Result.fail(
                    Errors.database(
                        operation="update_step", message=f"Failed to update step {step_uid}"
                    )
                )

            step_data = dict(record["s"])
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

            updated_step = Ls(
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
                difficulty=step_data.get("difficulty", "MODERATE"),
                status=step_data.get("status", "NOT_STARTED"),
                completed=step_data.get("completed", False),
                completed_at=step_data.get("completed_at"),
                domain=step_data.get("domain", "PERSONAL"),
                priority=step_data.get("priority", "MEDIUM"),
            )

            logger.info(f"✅ Updated learning step {step_uid}")

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
            return Result.fail(Errors.not_found(resource="Ls", identifier=step_uid))

        step = get_result.value
        had_ku_links = bool(step.primary_knowledge_uids or step.supporting_knowledge_uids)
        linked_lp_uid = step.learning_path_uid

        async with self.backend.driver.session() as session:
            # Delete step and its relationships
            result = await session.run(
                """
                MATCH (s:Ls {uid: $uid})
                DETACH DELETE s
                RETURN count(s) as deleted_count
                """,
                uid=step_uid,
            )

            record = await result.single()
            deleted_count = record["deleted_count"] if record else 0

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
    ) -> Result[list[Ls]]:
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

        async with self.backend.driver.session() as session:
            # Build WHERE clause for optional user_uid filtering
            where_clause = ""
            if user_uid:
                where_clause = "WHERE s.user_uid = $user_uid "

            # GRAPH-NATIVE: Include knowledge relationships in query
            if path_uid:
                # Get steps for specific path
                query = f"""
                MATCH (p:Lp {{uid: $path_uid}})-[:HAS_STEP]->(s:Ls)
                {where_clause}
                OPTIONAL MATCH (s)-[r:REQUIRES_KNOWLEDGE]->(ku:Ku)
                WITH s, collect({{uid: ku.uid, type: r.type}}) as knowledge_rels
                RETURN s, knowledge_rels
                ORDER BY {order_field} {order_direction}
                SKIP $offset
                LIMIT $limit
                """
                params = {"path_uid": path_uid, "limit": limit, "offset": offset}
            else:
                # Get all steps
                query = f"""
                MATCH (s:Ls)
                {where_clause}
                OPTIONAL MATCH (s)-[r:REQUIRES_KNOWLEDGE]->(ku:Ku)
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

            result = await session.run(query, params)

            steps = []
            async for record in result:
                step_data = dict(record["s"])
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
                    Ls(
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
                        difficulty=step_data.get("difficulty", "MODERATE"),
                        status=step_data.get("status", "NOT_STARTED"),
                        completed=step_data.get("completed", False),
                        completed_at=step_data.get("completed_at"),
                        domain=step_data.get("domain", "PERSONAL"),
                        priority=step_data.get("priority", "MEDIUM"),
                    )
                )

            logger.info(f"✅ Listed {len(steps)} learning steps")
            return Result.ok(steps)
