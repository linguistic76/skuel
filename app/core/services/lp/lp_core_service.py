"""
Learning Path Core Service
===========================

Core CRUD operations for learning paths.

This sub-service handles:
- Path creation and persistence
- Path retrieval (single and batch)
- Path listing (by user, all paths)
- Path updates and deletion
- Path-to-steps relationship management

Part of LpService decomposition (October 24, 2025)
- Follows KuService decomposition pattern
- Clear separation of concerns
- Single responsibility: CRUD operations

**Architecture (January 2026 Unified):**
- Extends BaseService[BackendOperations[Lp], Lp] for unified infrastructure
- Uses specialized Cypher queries for path-step relationships
- Class attributes match unified domain conventions
- Accesses database via self.backend.execute_query for graph-native operations
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.constants import MasteryLevel
from core.events import publish_event
from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.models.enums import Domain
from core.models.curriculum.learning_path import LearningPath
from core.models.curriculum.learning_step import LearningStep
from core.models.curriculum.learning_path_dto import LearningPathDTO
from core.ports import HasUID, get_enum_value
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.neo4j_mapper import from_neo4j_node
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence

    from core.ports import BackendOperations

logger = get_logger(__name__)


class LpCoreService(BaseService["BackendOperations[LearningPath]", LearningPath]):
    """
    Core CRUD operations for learning paths.

    **Architecture (January 2026 Unified):**
    Extends BaseService[BackendOperations[Lp], Lp] for unified infrastructure.
    Uses specialized Cypher queries for path-step relationships via
    self.backend.execute_query (no wrapper backend needed).

    This service owns:
    - Path creation and persistence to Neo4j
    - Path retrieval (single, batch, by user)
    - Path updates (name, goal, domain, hours)
    - Path deletion (cascade deletes steps)


    Source Tag: "lp_core_explicit"
    - Format: "lp_core_explicit" for user-created relationships
    - Format: "lp_core_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from learning_paths metadata
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
        dto_class=LearningPathDTO,
        model_class=LearningPath,
        entity_label="Entity",
        domain_name="lp",
        search_fields=("title", "description"),  # LP: name→title, goal→description
        search_order_by="updated_at",
        content_field="description",  # LP goal mapped to Ku description
    )

    @property
    def entity_label(self) -> str:
        """Entity label for Neo4j queries."""
        return "Entity"

    def __init__(
        self,
        backend: BackendOperations[LearningPath],
        ls_service: Any = None,
        event_bus: Any = None,
    ) -> None:
        """
        Initialize core path service.

        FAIL-FAST ARCHITECTURE (per CLAUDE.md):
        The backend is REQUIRED. Services run at full capacity or fail immediately.

        Args:
            backend: BackendOperations[Lp] for graph operations (REQUIRED)
            ls_service: LsService for step operations (optional for get_path_steps)
            event_bus: Event bus for domain events (optional)
        """
        super().__init__(backend, "lp_core")
        self.ls_service = ls_service
        self.event_bus = event_bus

    @staticmethod
    def _build_lp_from_record(path_data: dict, steps: list[LearningStep]) -> LearningPath:
        """Build LearningPath from Neo4j node dict + pre-built step list.

        Uses from_neo4j_node for full field deserialization.
        Steps (from HAS_STEP relationships) are stored in metadata["steps"].
        """
        ku = from_neo4j_node(path_data, LearningPath)
        existing_metadata = ku.metadata if ku.metadata else {}
        existing_metadata["steps"] = steps
        object.__setattr__(ku, "metadata", existing_metadata)
        return ku

    @staticmethod
    def _build_steps_from_data(steps_data: list[dict]) -> list[LearningStep]:
        """Build LearningStep list from step node dicts fetched via HAS_STEP join.

        Uses from_neo4j_node for full field deserialization of each step.
        """
        if not steps_data:
            return []

        sorted_steps = sorted(steps_data, key=get_sequence)
        steps: list[LearningStep] = []
        for step_info in sorted_steps:
            step_node = step_info.get("step") or step_info
            if step_node:
                step_dict = dict(step_node) if not isinstance(step_node, dict) else step_node
                if step_dict.get("uid"):
                    steps.append(from_neo4j_node(step_dict, LearningStep))
        return steps

    def _build_prerequisite_query(self, knowledge_var: str = "k", depth: int = 3) -> str:
        """
        Build pure Cypher prerequisite subquery using semantic relationships.

        PHASE 5 MIGRATION: Uses pure Cypher for prerequisite traversal.

        Args:
            knowledge_var: Variable name for knowledge node in query
            depth: Maximum prerequisite depth

        Returns:
            Cypher subquery fragment for prerequisite discovery
        """
        prerequisite_types = [
            SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
            SemanticRelationshipType.REQUIRES_PRACTICAL_APPLICATION,
            SemanticRelationshipType.REQUIRES_CONCEPTUAL_FOUNDATION,
            SemanticRelationshipType.BUILDS_ON_FOUNDATION,
        ]

        rel_pattern = "|".join([st.to_neo4j_name() for st in prerequisite_types])

        return f"""
        OPTIONAL MATCH ({knowledge_var})<-[:{rel_pattern}*1..{depth}]-(prereq:Entity)
        WITH {knowledge_var}, collect(DISTINCT prereq) as prereqs
        """

    @with_error_handling(
        "create_path_from_knowledge_units", error_type="database", uid_param="user_uid"
    )
    async def create_path_from_knowledge_units(
        self,
        user_uid: str,
        knowledge_units: list[Any],
        title: str | None = None,
        description: str | None = None,
    ) -> Result[LearningPath]:
        """Create a learning path from a list of knowledge units."""
        path_uid = f"path_{user_uid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        steps = []
        total_estimated_hours = 0

        for i, unit in enumerate(knowledge_units):
            step_uid = f"{path_uid}_step_{i + 1}"
            estimated_hours = 2

            step = LearningStep(
                uid=step_uid,
                title=f"Step {i + 1}",
                intent="Complete this learning step",
                primary_knowledge_uids=tuple([unit.uid if isinstance(unit, HasUID) else str(unit)]),
                sequence=i,
                estimated_hours=estimated_hours,
                mastery_threshold=MasteryLevel.PROFICIENT,
            )
            steps.append(step)
            total_estimated_hours += estimated_hours

        path = LearningPath(
            uid=path_uid,
            title=title or f"Learning Path for {user_uid}",
            description=description or "Complete knowledge units in sequence",
            domain=Domain.LEARNING,
            estimated_hours=total_estimated_hours,
        )

        if self.backend:
            persist_result = await self._persist_path(path, steps, user_uid)
            if persist_result.is_error:
                logger.warning(f"Failed to persist path: {persist_result.error}")

        # Store steps in metadata for return value
        path_with_steps = self._build_lp_from_record(
            {
                "uid": path.uid,
                "title": path.title,
                "description": path.description,
                "domain": get_enum_value(path.domain),
                "ku_type": "learning_path",
            },
            steps,
        )

        logger.info(f"✅ Created learning path {path_uid} with {len(steps)} steps")
        return Result.ok(path_with_steps)

    @with_error_handling("create_path", error_type="database", uid_param="user_uid")
    async def create_path(
        self,
        user_uid: str,
        title: str,
        description: str,
        steps: list[LearningStep],
        domain: Domain = Domain.LEARNING,
    ) -> Result[LearningPath]:
        """
        Create and persist a learning path.

        This is THE method for creating paths programmatically.
        """
        path_uid = f"path_{user_uid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        path = LearningPath(
            uid=path_uid,
            title=title,
            description=description,
            domain=domain,
            estimated_hours=sum(s.estimated_hours for s in steps if s.estimated_hours),
        )

        if self.backend:
            persist_result = await self._persist_path(path, steps, user_uid)
            if persist_result.is_error:
                return Result.fail(persist_result.expect_error())

        # Publish LearningPathStarted event
        from core.events import LearningPathStarted

        event = LearningPathStarted(
            path_uid=path_uid,
            user_uid=user_uid,
            occurred_at=datetime.now(),
            path_title=title,
            estimated_duration_hours=int(path.estimated_hours) if path.estimated_hours else None,
            total_kus=len(steps),
        )
        await publish_event(self.event_bus, event, self.logger)

        logger.info(f"✅ Created path {path_uid}: {title}")
        return Result.ok(path)

    @with_error_handling("get_learning_paths_batch", error_type="database")
    async def get_learning_paths_batch(self, uids: list[str]) -> Result[list[LearningPath | None]]:
        """
        Get multiple learning paths in one batched query.

        Critical for GraphQL DataLoader batching to prevent N+1 queries.
        """
        if not uids:
            return Result.ok([])

        query_result = await self.backend.execute_query(
            """
            MATCH (p:Entity)
            WHERE p.uid IN $uids
            OPTIONAL MATCH (p)-[r:HAS_STEP]->(s:Entity {ku_type: 'learning_step'})
            WITH p, collect({step: s, sequence: r.sequence}) as steps_data
            ORDER BY p.uid
            RETURN p, steps_data
            """,
            {"uids": uids},
        )

        if query_result.is_error:
            return Result.fail(query_result)

        paths_map: dict[str, LearningPath] = {}
        for record in query_result.value:
            path_data = dict(record["p"])
            steps = self._build_steps_from_data(record["steps_data"])
            path = self._build_lp_from_record(path_data, steps)
            paths_map[path.uid] = path

        # Return in same order as input UIDs
        result_list = [paths_map.get(uid) for uid in uids]
        return Result.ok(result_list)

    @with_error_handling("get_learning_path", error_type="database", uid_param="path_uid")
    async def get_learning_path(self, path_uid: str) -> Result[LearningPath | None]:
        """Get a single learning path by UID (returns None if not found)."""
        query_result = await self.backend.execute_query(
            """
            MATCH (p:Entity {uid: $uid})
            OPTIONAL MATCH (p)-[r:HAS_STEP]->(s:Entity {ku_type: 'learning_step'})
            WITH p, collect({step: s, sequence: r.sequence}) as steps_data
            RETURN p, steps_data
            """,
            {"uid": path_uid},
        )

        if query_result.is_error:
            return Result.fail(query_result)

        records = query_result.value
        if not records:
            return Result.ok(None)  # Not found - return None instead of error

        record = records[0]
        path_data = dict(record["p"])
        steps = self._build_steps_from_data(record["steps_data"])
        path = self._build_lp_from_record(path_data, steps)

        return Result.ok(path)

    @with_error_handling("get_with_context", error_type="database", uid_param="uid")
    async def get_with_context(
        self,
        uid: str,
        depth: int = 2,
        min_confidence: float = 0.7,
        include_relationships: Sequence[str] | None = None,
        exclude_relationships: Sequence[str] | None = None,
    ) -> Result[LearningPath]:
        """
        Get learning path with comprehensive graph context (SINGLE QUERY).

        Overrides BaseService.get_with_context() with LP-specific graph patterns.

        Rich Context Pattern: Fetches path + all graph neighborhoods in one query:
        - Steps with sequence and progress
        - Prerequisite knowledge units
        - Aligned goals (motivational integration)
        - Embodied principles (value alignment)
        - Milestone events (curriculum calendar)
        - Enrolled users (community tracking)
        - Step completion statistics

        All context stored in path.metadata["graph_context"].

        Args:
            uid: Ku UID (learning_path)
            depth: Graph traversal depth (not used - fixed depth query)
            min_confidence: Minimum relationship confidence (not used - specialized query)
            include_relationships: Relationships to include (not used - specialized query)
            exclude_relationships: Relationships to exclude (not used - specialized query)

        Returns:
            Result containing Ku (learning_path) with enriched metadata
        """
        # Note: depth and min_confidence are accepted for API compatibility
        # but this implementation uses a fixed specialized query
        path_uid = uid  # Alias for backward compatibility in query
        query_result = await self.backend.execute_query(
            """
            MATCH (lp:Entity {uid: $uid})

            // 1. Steps (with sequence and progress)
            OPTIONAL MATCH (lp)-[r_step:HAS_STEP|CONTAINS_STEP]->(step:Entity {ku_type: 'learning_step'})
            WITH lp, collect({
                uid: step.uid,
                title: step.title,
                intent: step.intent,
                sequence: coalesce(r_step.sequence, step.sequence),
                status: step.status,
                current_mastery: step.current_mastery,
                estimated_hours: step.estimated_hours
            }) as steps_data

            // 2. Prerequisite knowledge
            OPTIONAL MATCH (lp)-[:REQUIRES_KNOWLEDGE]->(prereq_ku:Entity)
            WHERE prereq_ku.ku_type IS NULL OR prereq_ku.ku_type = 'curriculum'
            WITH lp, steps_data, collect({
                uid: prereq_ku.uid,
                title: prereq_ku.title,
                domain: prereq_ku.domain
            }) as prerequisite_knowledge

            // 3. Aligned goals (motivational integration)
            OPTIONAL MATCH (lp)-[:ALIGNED_WITH_GOAL]->(goal:Goal)
            WITH lp, steps_data, prerequisite_knowledge, collect({
                uid: goal.uid,
                title: goal.title,
                status: goal.status,
                progress_percentage: goal.progress_percentage
            }) as aligned_goals

            // 4. Embodied principles (value alignment)
            OPTIONAL MATCH (lp)-[:EMBODIES_PRINCIPLE]->(principle:Principle)
            WITH lp, steps_data, prerequisite_knowledge, aligned_goals, collect({
                uid: principle.uid,
                title: principle.title,
                principle_type: principle.principle_type
            }) as embodied_principles

            // 5. Milestone events (curriculum calendar)
            OPTIONAL MATCH (lp)-[:HAS_MILESTONE_EVENT]->(event:Event)
            WITH lp, steps_data, prerequisite_knowledge, aligned_goals, embodied_principles, collect({
                uid: event.uid,
                title: event.title,
                event_date: event.event_date,
                status: event.status
            }) as milestone_events

            // 6. Enrolled users (community tracking)
            OPTIONAL MATCH (user:User)-[:ENROLLED_IN|HAS_PATH]->(lp)
            WITH lp, steps_data, prerequisite_knowledge, aligned_goals, embodied_principles,
                 milestone_events, collect({
                uid: user.uid,
                username: user.username
            }) as enrolled_users

            // 7. Step statistics (using status instead of completed boolean)
            WITH lp, steps_data, prerequisite_knowledge, aligned_goals, embodied_principles,
                 milestone_events, enrolled_users,
                 size([s IN steps_data WHERE s.status = 'completed']) as completed_steps,
                 size(steps_data) as total_steps

            RETURN lp, steps_data, prerequisite_knowledge, aligned_goals, embodied_principles,
                   milestone_events, enrolled_users, completed_steps, total_steps
            """,
            {"uid": path_uid},
        )

        if query_result.is_error:
            return Result.fail(query_result)

        records = query_result.value
        if not records:
            return Result.fail(Errors.not_found(resource="learning_path", identifier=path_uid))

        record = records[0]
        path_data = dict(record["lp"])
        steps_data = record["steps_data"]

        # Build steps
        steps = []
        if steps_data:
            sorted_steps = sorted(steps_data, key=get_sequence)
            for step_info in sorted_steps:
                if step_info.get("uid"):
                    steps.append(
                        LearningStep(
                            uid=step_info["uid"],
                            title=step_info.get("title", "Learning Step"),
                            intent=step_info.get("intent", "Complete this learning step"),
                            sequence=step_info.get("sequence"),
                            current_mastery=step_info.get("current_mastery", 0.0),
                            estimated_hours=step_info.get("estimated_hours", 1.0),
                        )
                    )

        # Build LearningPath — from_neo4j_node handles all fields from full node
        path = self._build_lp_from_record(path_data, steps)

        # Calculate progress percentage
        total_steps = record["total_steps"]
        completed_steps = record["completed_steps"]
        progress_percentage = (completed_steps / total_steps * 100.0) if total_steps > 0 else 0.0

        # Enrich with graph context in metadata
        object.__setattr__(
            path,
            "metadata",
            {
                "graph_context": {
                    # Steps (detailed)
                    "steps": [s for s in steps_data if s.get("uid")],
                    # Prerequisites
                    "prerequisite_knowledge": [
                        k for k in record["prerequisite_knowledge"] if k.get("uid")
                    ],
                    # Motivational integration
                    "aligned_goals": [g for g in record["aligned_goals"] if g.get("uid")],
                    # Value alignment
                    "embodied_principles": [
                        p for p in record["embodied_principles"] if p.get("uid")
                    ],
                    # Curriculum calendar
                    "milestone_events": [e for e in record["milestone_events"] if e.get("uid")],
                    # Community
                    "enrolled_users": [u for u in record["enrolled_users"] if u.get("uid")],
                    # Progress statistics
                    "total_steps": total_steps,
                    "completed_steps": completed_steps,
                    "progress_percentage": progress_percentage,
                    "remaining_steps": total_steps - completed_steps,
                    # Aggregates
                    "has_prerequisites": len(
                        [k for k in record["prerequisite_knowledge"] if k.get("uid")]
                    )
                    > 0,
                    "has_goals": len([g for g in record["aligned_goals"] if g.get("uid")]) > 0,
                    "has_milestones": len([e for e in record["milestone_events"] if e.get("uid")])
                    > 0,
                    "is_active": len([u for u in record["enrolled_users"] if u.get("uid")]) > 0,
                }
            },
        )

        logger.info(
            f"✅ Retrieved path with context: {path_uid} "
            f"(steps: {total_steps}, completed: {completed_steps}, "
            f"progress: {progress_percentage:.1f}%, "
            f"goals: {len([g for g in record['aligned_goals'] if g.get('uid')])}, "
            f"users: {len([u for u in record['enrolled_users'] if u.get('uid')])})"
        )

        return Result.ok(path)

    @with_error_handling("list_user_paths", error_type="database", uid_param="user_uid")
    async def list_user_paths(
        self, user_uid: str, limit: int | None = None
    ) -> Result[list[LearningPath]]:
        """List all learning paths for a specific user."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:HAS_PATH]->(p:Entity {ku_type: 'learning_path'})
        OPTIONAL MATCH (p)-[r:HAS_STEP]->(s:Entity {ku_type: 'learning_step'})
        WITH p, collect({step: s, sequence: r.sequence}) as steps_data
        ORDER BY p.uid DESC
        """
        if limit:
            query += " LIMIT $limit"
        query += " RETURN p, steps_data"

        params = {"user_uid": user_uid}
        if limit:
            params["limit"] = limit

        query_result = await self.backend.execute_query(query, params)

        if query_result.is_error:
            return Result.fail(query_result)

        paths = []
        for record in query_result.value:
            path_data = dict(record["p"])
            steps = self._build_steps_from_data(record["steps_data"])
            paths.append(self._build_lp_from_record(path_data, steps))

        return Result.ok(paths)

    @with_error_handling("list_all_paths", error_type="database")
    async def list_all_paths(
        self,
        limit: int | None = None,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[list[LearningPath]]:
        """
        List all learning paths in the system with pagination and sorting.

        Args:
            limit: Maximum number of paths to return
            offset: Number of paths to skip (for pagination)
            order_by: Field to sort by (e.g., 'uid', 'created_at', 'title')
            order_desc: Sort in descending order if True
        """
        # Build dynamic ORDER BY clause
        order_field = f"p.{order_by}" if order_by else "p.uid"
        order_direction = "DESC" if order_desc else "ASC"

        query = f"""
        MATCH (p:Entity {{ku_type: 'learning_path'}})
        OPTIONAL MATCH (p)-[r:HAS_STEP]->(s:Entity {{ku_type: 'learning_step'}})
        WITH p, collect({{step: s, sequence: r.sequence}}) as steps_data
        ORDER BY {order_field} {order_direction}
        """
        if offset > 0:
            query += " SKIP $offset"
        if limit:
            query += " LIMIT $limit"
        query += " RETURN p, steps_data"

        params: dict[str, Any] = {"offset": offset}
        if limit:
            params["limit"] = limit

        query_result = await self.backend.execute_query(query, params)

        if query_result.is_error:
            return Result.fail(query_result)

        paths = []
        for record in query_result.value or []:
            path_data = dict(record["p"])
            steps = self._build_steps_from_data(record["steps_data"])
            paths.append(self._build_lp_from_record(path_data, steps))

        return Result.ok(paths)

    async def get_path_steps(self, path_uid: str) -> Result[list[LearningStep]]:
        """
        Get steps for a learning path.

        Used by GraphQL types to resolve nested steps field.
        """
        path_result = await self.get_learning_path(path_uid)
        if path_result.is_error:
            return Result.fail(path_result.expect_error())

        if not path_result.value:
            return Result.fail(Errors.not_found(resource="learning_path", identifier=path_uid))

        path = path_result.value
        steps = path.metadata.get("steps", []) if path.metadata else []
        return Result.ok(list(steps))

    async def get_current_step(self, path_uid: str) -> Result[LearningStep | None]:
        """
        Get the current (first incomplete) step in a learning path.

        Returns the first step that is not yet completed, or None if all steps
        are completed or path has no steps.

        Args:
            path_uid: Learning path UID

        Returns:
            Result containing the current step, or None if all steps completed
        """
        steps_result = await self.get_path_steps(path_uid)
        if steps_result.is_error:
            return Result.fail(steps_result.expect_error())

        steps = steps_result.value
        if not steps:
            return Result.ok(None)

        # Find first incomplete step (Ku uses is_completed property)
        for step in steps:
            if not step.is_completed:
                return Result.ok(step)

        # All steps completed - return None
        return Result.ok(None)

    @with_error_handling("update_path", error_type="database", uid_param="path_uid")
    async def update_path(self, path_uid: str, updates: dict[str, Any]) -> Result[LearningPath]:
        """
        Update an existing learning path.

        Supports updating: title, description, domain, estimated_hours, etc.
        """
        # First verify path exists
        get_result = await self.get_learning_path(path_uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        if not get_result.value:
            return Result.fail(Errors.not_found(resource="learning_path", identifier=path_uid))

        # Build SET clause dynamically
        set_clauses = []
        params = {"uid": path_uid}

        allowed_fields = {
            "title",
            "description",
            "domain",
            "estimated_hours",
            "path_type",
            "step_difficulty",
            "outcomes",
            "checkpoint_week_intervals",
        }
        for key, value in updates.items():
            if key in allowed_fields:
                set_clauses.append(f"p.{key} = ${key}")
                if key in ("domain", "path_type", "step_difficulty"):
                    params[key] = get_enum_value(value)
                elif key in ("outcomes", "checkpoint_week_intervals"):
                    params[key] = list(value) if value else []
                else:
                    params[key] = value

        if not set_clauses:
            return Result.fail(
                Errors.validation(message="No valid fields to update", field="updates")
            )

        set_clauses.append("p.updated_at = $updated_at")
        params["updated_at"] = datetime.now().isoformat()

        query = f"""
        MATCH (p:Entity {{uid: $uid}})
        SET {", ".join(set_clauses)}
        OPTIONAL MATCH (p)-[r:HAS_STEP]->(s:Entity {{ku_type: 'learning_step'}})
        WITH p, collect(s) as steps
        RETURN p, steps
        """

        query_result = await self.backend.execute_query(query, params)

        if query_result.is_error:
            return Result.fail(query_result)

        if not query_result.value:
            return Result.fail(
                Errors.database(
                    operation="update_path", message=f"Failed to update path {path_uid}"
                )
            )

        record = query_result.value[0]
        path_data = dict(record["p"])
        steps_data = record["steps"]

        steps = []
        for step_node in steps_data:
            step_dict = dict(step_node) if not isinstance(step_node, dict) else step_node
            if step_dict.get("uid"):
                steps.append(from_neo4j_node(step_dict, LearningStep))

        updated_path = self._build_lp_from_record(path_data, steps)

        logger.info(f"✅ Updated learning path {path_uid}")
        return Result.ok(updated_path)

    @with_error_handling("delete_path", error_type="database", uid_param="path_uid")
    async def delete_path(self, path_uid: str) -> Result[bool]:
        """
        Delete a learning path and its associated steps.

        Cascade deletes step Ku nodes to prevent orphaned data.
        """
        # First verify path exists
        get_result = await self.get_learning_path(path_uid)
        if get_result.is_error:
            return Result.fail(get_result)

        if not get_result.value:
            return Result.fail(Errors.not_found(resource="learning_path", identifier=path_uid))

        query_result = await self.backend.execute_query(
            """
            MATCH (p:Entity {uid: $uid})
            OPTIONAL MATCH (p)-[:HAS_STEP]->(s:Entity {ku_type: 'learning_step'})
            DETACH DELETE p, s
            RETURN count(p) as deleted_count
            """,
            {"uid": path_uid},
        )

        if query_result.is_error:
            return Result.fail(query_result)

        deleted_count = query_result.value[0]["deleted_count"] if query_result.value else 0

        if deleted_count == 0:
            return Result.fail(
                Errors.database(
                    operation="delete_path", message=f"Failed to delete path {path_uid}"
                )
            )

        logger.info(f"✅ Deleted learning path {path_uid}")
        return Result.ok(True)

    # ============================================================================
    # STEP MANAGEMENT (2026-01-30 - Universal Hierarchical Pattern)
    # ============================================================================

    @with_error_handling("get_steps", error_type="database", uid_param="path_uid")
    async def get_steps(self, path_uid: str, depth: int = 1) -> Result[list[LearningStep]]:
        """
        Get all steps in a learning path ordered by sequence.

        Args:
            path_uid: Learning path UID
            depth: Traversal depth (default: 1, immediate steps only)

        Returns:
            Result containing list of Ku (learning steps) ordered by sequence

        Example:
            steps = await service.get_steps("lp:abc123")
            # Returns [step1, step2, step3] in sequence order
        """
        query = f"""
        MATCH (lp:Entity {{uid: $path_uid}})-[r:HAS_STEP*1..{depth}]->(ls:Entity {{ku_type: 'learning_step'}})
        RETURN ls, r[0].sequence as sequence
        ORDER BY sequence
        """

        result = await self.backend.execute_query(query, {"path_uid": path_uid})

        if result.is_error:
            return Result.fail(result)

        if not result.value:
            return Result.ok([])

        steps = []
        for record in result.value:
            ls_data = record["ls"]
            steps.append(from_neo4j_node(ls_data, LearningStep))

        return Result.ok(steps)

    @with_error_handling("get_parent_path", error_type="database", uid_param="step_uid")
    async def get_parent_path(self, step_uid: str) -> Result[LearningPath | None]:
        """
        Get the learning path containing this step.

        Args:
            step_uid: Learning step UID

        Returns:
            Result containing parent Ku (learning_path) or None if step not in any path

        Note:
            A learning step can belong to multiple paths. This returns the first match.
        """
        query = """
        MATCH (lp:Entity {ku_type: 'learning_path'})-[:HAS_STEP]->(ls:Entity {uid: $step_uid})
        RETURN lp
        LIMIT 1
        """

        result = await self.backend.execute_query(query, {"step_uid": step_uid})

        if result.is_error:
            return Result.fail(result)

        if not result.value:
            return Result.ok(None)

        lp_data = result.value[0]["lp"]
        lp = self._to_domain_model(lp_data, LearningPathDTO, LearningPath)
        return Result.ok(lp)

    @with_error_handling("get_path_hierarchy", error_type="database", uid_param="path_uid")
    async def get_path_hierarchy(self, path_uid: str) -> Result[dict[str, Any]]:
        """
        Get learning path with all its steps.

        Args:
            path_uid: Learning path UID

        Returns:
            Result containing hierarchy dict with keys:
            - current: Ku (the path itself)
            - steps: list[Ku] (ordered learning steps)
            - step_count: int (total number of steps)
        """
        # Get current path
        current_result = await self.backend.get(path_uid)
        if current_result.is_error:
            return Result.fail(current_result)

        current_lp = self._to_domain_model(current_result.value, LearningPathDTO, LearningPath)

        # Get steps
        steps_result = await self.get_steps(path_uid)
        if steps_result.is_error:
            return Result.fail(steps_result)

        steps = steps_result.value

        return Result.ok(
            {
                "current": current_lp,
                "steps": steps,
                "step_count": len(steps),
            }
        )

    @with_error_handling("add_step_to_path", error_type="database")
    async def add_step_to_path(
        self, path_uid: str, step_uid: str, sequence: int, order: int = 0
    ) -> Result[bool]:
        """
        Add a learning step to a path with sequence ordering.

        Args:
            path_uid: Learning path UID
            step_uid: Learning step UID
            sequence: Position in path (0-indexed)
            order: Additional ordering hint (default: 0)

        Returns:
            Result indicating success

        Note:
            Creates HAS_STEP relationship with sequence property for ordering.
        """
        # Validate path exists
        path_result = await self.backend.get(path_uid)
        if path_result.is_error:
            return Result.fail(Errors.not_found(f"Learning path not found: {path_uid}"))

        # Validate step exists
        step_query = """
        MATCH (ls:Entity {uid: $step_uid})
        RETURN ls
        """
        step_check = await self.backend.execute_query(step_query, {"step_uid": step_uid})
        if step_check.is_error:
            return Result.fail(step_check)
        if not step_check.value:
            return Result.fail(Errors.not_found(f"Learning step not found: {step_uid}"))

        # Create relationship
        query = """
        MATCH (lp:Entity {uid: $path_uid})
        MATCH (ls:Entity {uid: $step_uid})
        CREATE (lp)-[:HAS_STEP {
            sequence: $sequence,
            order: $order,
            created_at: datetime()
        }]->(ls)
        RETURN true as success
        """

        result = await self.backend.execute_query(
            query,
            {"path_uid": path_uid, "step_uid": step_uid, "sequence": sequence, "order": order},
        )

        if result.is_error:
            return Result.fail(result)

        if result.value:
            self.logger.info(f"Added step {step_uid} to path {path_uid} at sequence {sequence}")
            return Result.ok(True)

        return Result.fail(
            Errors.database(operation="database_operation", message="Failed to add step to path")
        )

    @with_error_handling("remove_step_from_path", error_type="database")
    async def remove_step_from_path(self, path_uid: str, step_uid: str) -> Result[bool]:
        """
        Remove a learning step from a path and reorder remaining steps.

        Args:
            path_uid: Learning path UID
            step_uid: Learning step UID

        Returns:
            Result containing True if step was removed

        Note:
            Automatically closes sequence gaps by reordering remaining steps.
        """
        # Delete the relationship
        delete_query = """
        MATCH (lp:Entity {uid: $path_uid})-[r:HAS_STEP]->(ls:Entity {uid: $step_uid})
        DELETE r
        RETURN count(r) as deleted_count
        """

        result = await self.backend.execute_query(
            delete_query, {"path_uid": path_uid, "step_uid": step_uid}
        )

        if result.is_error:
            return Result.fail(result)

        if not result.value or result.value[0]["deleted_count"] == 0:
            return Result.ok(False)

        # Reorder remaining steps to close gaps
        reorder_query = """
        MATCH (lp:Entity {uid: $path_uid})-[r:HAS_STEP]->(ls:Entity {ku_type: 'learning_step'})
        WITH ls, r
        ORDER BY r.sequence
        WITH collect(ls) as steps
        UNWIND range(0, size(steps)-1) as idx
        MATCH (lp:Entity {uid: $path_uid})-[r:HAS_STEP]->(steps[idx])
        SET r.sequence = idx
        RETURN count(r) as updated
        """

        await self.backend.execute_query(reorder_query, {"path_uid": path_uid})

        self.logger.info(
            f"Removed step {step_uid} from path {path_uid} and reordered remaining steps"
        )
        return Result.ok(True)

    @with_error_handling("reorder_steps", error_type="database")
    async def reorder_steps(self, path_uid: str, step_uids: list[str]) -> Result[bool]:
        """
        Batch reorder all steps in a learning path.

        Args:
            path_uid: Learning path UID
            step_uids: Ordered list of step UIDs (defines new sequence)

        Returns:
            Result indicating success

        Example:
            # Swap first two steps
            await service.reorder_steps("lp:abc123", ["ls:step2", "ls:step1", "ls:step3"])
        """
        query = """
        MATCH (lp:Entity {uid: $path_uid})
        WITH lp
        UNWIND range(0, size($step_uids)-1) as idx
        MATCH (lp)-[r:HAS_STEP]->(ls:Entity {uid: $step_uids[idx]})
        SET r.sequence = idx
        RETURN count(r) as updated
        """

        result = await self.backend.execute_query(
            query, {"path_uid": path_uid, "step_uids": step_uids}
        )

        if result.is_error:
            return Result.fail(result)

        updated = result.value[0]["updated"] if result.value else 0
        success = updated == len(step_uids)

        if success:
            self.logger.info(f"Reordered {updated} steps in path {path_uid}")

        return Result.ok(success)

    # ============================================================================
    # PRIVATE HELPERS
    # ============================================================================

    @with_error_handling("_persist_path", error_type="database", uid_param="user_uid")
    async def _persist_path(
        self, path: LearningPath, steps: list[LearningStep], user_uid: str
    ) -> Result[bool]:
        """Persist a learning path to Neo4j graph."""
        # Create path node with all fields
        path_result = await self.backend.execute_query(
            """
            MERGE (u:User {uid: $user_uid})
            CREATE (p:Entity {
                uid: $uid,
                ku_type: 'learning_path',
                title: $title,
                description: $description,
                domain: $domain,
                path_type: $path_type,
                step_difficulty: $step_difficulty,
                created_by: $created_by,
                estimated_hours: $estimated_hours,
                outcomes: $outcomes,
                checkpoint_week_intervals: $checkpoint_week_intervals,
                created_at: datetime(),
                updated_at: datetime()
            })
            CREATE (u)-[:HAS_PATH]->(p)
            """,
            {
                "user_uid": user_uid,
                "uid": path.uid,
                "title": path.title,
                "description": path.description,
                "domain": get_enum_value(path.domain),
                "path_type": get_enum_value(path.path_type),
                "step_difficulty": get_enum_value(getattr(path, "step_difficulty", None)),
                "created_by": path.created_by,
                "estimated_hours": path.estimated_hours,
                "outcomes": list(path.outcomes),
                "checkpoint_week_intervals": list(path.checkpoint_week_intervals),
            },
        )

        if path_result.is_error:
            return Result.fail(path_result)

        # Create step nodes and relationships
        for _i, step in enumerate(steps):
            step_result = await self.backend.execute_query(
                """
                MATCH (p:Entity {uid: $path_uid})
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
                    domain: $domain,
                    priority: $priority,
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (p)-[:HAS_STEP {sequence: $sequence}]->(s)
                """,
                {
                    "path_uid": path.uid,
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
                    "domain": get_enum_value(step.domain),
                    "priority": get_enum_value(step.priority),
                },
            )

            if step_result.is_error:
                return Result.fail(step_result)

        logger.debug(f"✅ Persisted path {path.uid} with {len(steps)} steps")
        return Result.ok(True)
