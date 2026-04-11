"""
LP Step Mixin
=============

Step management and path CRUD operations for LpBackend.

Provides HAS_STEP relationship management, path node CRUD,
batch operations, and graph context queries.

Requires on concrete class:
    execute_query, logger  (provided by UniversalNeo4jBackend)

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    import logging

from adapters.persistence.neo4j._backend_helpers import _ALLOWED_ORDER_BY


class _LpStepMixin:
    """Step management and path CRUD operations.

    Domain backends that need LP step management should add ``_LpStepMixin``
    to their class bases.

    Requires on concrete class:
        execute_query: async (query, params) -> Result[list[dict]]
        logger: logging.Logger
    """

    if TYPE_CHECKING:
        logger: logging.Logger

        async def execute_query(
            self, query: str, params: dict[str, Any] | None = None
        ) -> Result[builtins.list[dict[str, Any]]]: ...

    # ========================================================================
    # STEP MANAGEMENT (HAS_STEP edges)
    # ========================================================================

    async def get_steps_raw(self, path_uid: str, depth: int = 1) -> Result[list[dict[str, Any]]]:
        """Get ordered steps in a learning path as raw dicts."""
        query = f"""
        MATCH (lp:Entity {{uid: $path_uid}})-[r:HAS_STEP*1..{depth}]->(ps:Entity {{entity_type: 'path_step'}})
        RETURN ps, r[0].sequence as sequence
        ORDER BY sequence
        """
        result = await self.execute_query(query, {"path_uid": path_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["ps"] for record in (result.value or [])])

    async def get_parent_path_raw(self, step_uid: str) -> Result[dict[str, Any] | None]:
        """Get parent learning path for a step as raw dict, or None."""
        query = """
        MATCH (lp:Entity {entity_type: 'learning_path'})-[:HAS_STEP]->(ps:Entity {uid: $step_uid})
        RETURN lp
        LIMIT 1
        """
        result = await self.execute_query(query, {"step_uid": step_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(None)
        return Result.ok(result.value[0]["lp"])

    async def add_step_to_path(
        self, path_uid: str, step_uid: str, sequence: int, order: int = 0
    ) -> Result[bool]:
        """Create HAS_STEP relationship between path and step (idempotent)."""
        query = """
        MATCH (lp:Entity {uid: $path_uid})
        MATCH (ps:Entity {uid: $step_uid})
        MERGE (lp)-[r:HAS_STEP]->(ps)
        ON CREATE SET
            r.sequence = $sequence,
            r.order = $order,
            r.created_at = datetime()
        RETURN true as success
        """
        result = await self.execute_query(
            query,
            {"path_uid": path_uid, "step_uid": step_uid, "sequence": sequence, "order": order},
        )
        if result.is_error:
            return Result.fail(result)
        if result.value:
            self.logger.info(f"Added step {step_uid} to path {path_uid} at sequence {sequence}")
            return Result.ok(True)
        return Result.fail(
            Errors.database(operation="add_step_to_path", message="Failed to add step to path")
        )

    async def remove_step_from_path(self, path_uid: str, step_uid: str) -> Result[bool]:
        """Remove HAS_STEP relationship and reorder remaining steps."""
        # Delete the relationship
        delete_query = """
        MATCH (lp:Entity {uid: $path_uid})-[r:HAS_STEP]->(ps:Entity {uid: $step_uid})
        DELETE r
        RETURN count(r) as deleted_count
        """
        result = await self.execute_query(
            delete_query, {"path_uid": path_uid, "step_uid": step_uid}
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value or result.value[0]["deleted_count"] == 0:
            return Result.ok(False)

        # Reorder remaining steps to close gaps
        reorder_query = """
        MATCH (lp:Entity {uid: $path_uid})-[r:HAS_STEP]->(ps:Entity {entity_type: 'path_step'})
        WITH ps, r
        ORDER BY r.sequence
        WITH collect(ps) as steps
        UNWIND range(0, size(steps)-1) as idx
        MATCH (lp:Entity {uid: $path_uid})-[r:HAS_STEP]->(steps[idx])
        SET r.sequence = idx
        RETURN count(r) as updated
        """
        await self.execute_query(reorder_query, {"path_uid": path_uid})
        self.logger.info(f"Removed step {step_uid} from path {path_uid} and reordered")
        return Result.ok(True)

    async def reorder_steps(self, path_uid: str, step_uids: list[str]) -> Result[bool]:
        """Batch reorder all steps in a path."""
        query = """
        MATCH (lp:Entity {uid: $path_uid})
        WITH lp
        UNWIND range(0, size($step_uids)-1) as idx
        MATCH (lp)-[r:HAS_STEP]->(ps:Entity {uid: $step_uids[idx]})
        SET r.sequence = idx
        RETURN count(r) as updated
        """
        result = await self.execute_query(query, {"path_uid": path_uid, "step_uids": step_uids})
        if result.is_error:
            return Result.fail(result)
        updated = result.value[0]["updated"] if result.value else 0
        success = updated == len(step_uids)
        if success:
            self.logger.info(f"Reordered {updated} steps in path {path_uid}")
        return Result.ok(success)

    # ========================================================================
    # PATH CRUD (moved from LpCoreService — separation of concerns)
    # ========================================================================

    async def get_path_with_steps(self, path_uid: str) -> Result[list[dict[str, Any]]]:
        """
        Get a single learning path node with its HAS_STEP steps.

        Returns raw records: each record has 'p' (path node) and 'steps_data'
        (list of {step, sequence} dicts).
        """
        query = """
        MATCH (p:Entity {uid: $uid})
        OPTIONAL MATCH (p)-[r:HAS_STEP]->(s:Entity {entity_type: 'path_step'})
        WITH p, collect({step: s, sequence: r.sequence}) as steps_data
        RETURN p, steps_data
        """
        return await self.execute_query(query, {"uid": path_uid})

    async def get_paths_batch_with_steps(self, uids: list[str]) -> Result[list[dict[str, Any]]]:
        """
        Batch-fetch multiple learning paths with their steps.

        Returns raw records ordered by uid: each record has 'p' (path node)
        and 'steps_data' (list of {step, sequence} dicts).
        """
        query = """
        MATCH (p:Entity)
        WHERE p.uid IN $uids
        OPTIONAL MATCH (p)-[r:HAS_STEP]->(s:Entity {entity_type: 'path_step'})
        WITH p, collect({step: s, sequence: r.sequence}) as steps_data
        ORDER BY p.uid
        RETURN p, steps_data
        """
        return await self.execute_query(query, {"uids": uids})

    async def get_path_with_graph_context(self, path_uid: str) -> Result[list[dict[str, Any]]]:
        """
        Get learning path with comprehensive graph context in a single query.

        Returns raw records with: lp, steps_data, prerequisite_knowledge,
        aligned_goals, embodied_principles, milestone_events, enrolled_users,
        completed_steps, total_steps.
        """
        query = """
        MATCH (lp:Entity {uid: $uid})

        // 1. Steps (with sequence and progress)
        OPTIONAL MATCH (lp)-[r_step:HAS_STEP|CONTAINS_STEP]->(step:Entity {entity_type: 'path_step'})
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
        WHERE prereq_ku.entity_type IS NULL OR prereq_ku.entity_type = 'ku'
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
        """
        return await self.execute_query(query, {"uid": path_uid})

    async def list_user_paths_with_steps(
        self, user_uid: UserUID, limit: int | None = None
    ) -> Result[list[dict[str, Any]]]:
        """
        List all learning paths for a user, with their steps.

        Returns raw records: each record has 'p' (path node) and 'steps_data'.
        """
        query = """
        MATCH (u:User {uid: $user_uid})-[:HAS_PATH]->(p:Entity {entity_type: 'learning_path'})
        OPTIONAL MATCH (p)-[r:HAS_STEP]->(s:Entity {entity_type: 'path_step'})
        WITH p, collect({step: s, sequence: r.sequence}) as steps_data
        ORDER BY p.uid DESC
        """
        if limit:
            query += " LIMIT $limit"
        query += " RETURN p, steps_data"

        params: dict[str, Any] = {"user_uid": user_uid}
        if limit:
            params["limit"] = limit
        return await self.execute_query(query, params)

    async def list_all_paths_with_steps(
        self,
        limit: int | None = None,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[list[dict[str, Any]]]:
        """
        List all learning paths with pagination and safe sorting.

        Validates order_by against _ALLOWED_ORDER_BY to prevent Cypher injection.
        """
        validated_field = "uid"
        if order_by:
            if order_by not in _ALLOWED_ORDER_BY:
                return Result.fail(Errors.validation(f"Invalid order_by field: {order_by!r}"))
            validated_field = order_by

        order_direction = "DESC" if order_desc else "ASC"

        query = f"""
        MATCH (p:Entity {{entity_type: 'learning_path'}})
        OPTIONAL MATCH (p)-[r:HAS_STEP]->(s:Entity {{entity_type: 'path_step'}})
        WITH p, collect({{step: s, sequence: r.sequence}}) as steps_data
        ORDER BY p.{validated_field} {order_direction}
        """
        if offset > 0:
            query += " SKIP $offset"
        if limit:
            query += " LIMIT $limit"
        query += " RETURN p, steps_data"

        params: dict[str, Any] = {"offset": offset}
        if limit:
            params["limit"] = limit
        return await self.execute_query(query, params)

    async def update_path_properties(
        self, set_clauses: list[str], params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]:
        """
        Update a learning path's properties and return the updated path with steps.

        Args:
            set_clauses: Pre-validated SET clause fragments (e.g. ['p.title = $title'])
            params: Query parameters including 'uid' and all SET values
        """
        query = f"""
        MATCH (p:Entity {{uid: $uid}})
        SET {", ".join(set_clauses)}
        OPTIONAL MATCH (p)-[r:HAS_STEP]->(s:Entity {{entity_type: 'path_step'}})
        WITH p, collect(s) as steps
        RETURN p, steps
        """
        return await self.execute_query(query, params)

    async def delete_path_cascade(self, path_uid: str) -> Result[list[dict[str, Any]]]:
        """
        Delete a learning path and cascade-delete its step nodes.

        Returns records with deleted_count.
        """
        query = """
        MATCH (p:Entity {uid: $uid})
        OPTIONAL MATCH (p)-[:HAS_STEP]->(s:Entity {entity_type: 'path_step'})
        DETACH DELETE p, s
        RETURN count(p) as deleted_count
        """
        return await self.execute_query(query, {"uid": path_uid})

    async def persist_path_with_steps(
        self,
        user_uid: UserUID,
        path_params: dict[str, Any],
        steps_params: list[dict[str, Any]],
    ) -> Result[bool]:
        """
        Persist a learning path node with User relationship, then create step nodes.

        Args:
            user_uid: Owner user UID
            path_params: Properties for the path node
            steps_params: List of property dicts for each step node
        """
        # Create path node and user relationship
        path_query = """
        MERGE (u:User {uid: $user_uid})
        CREATE (p:Entity {
            uid: $uid,
            entity_type: 'learning_path',
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
        """
        path_result = await self.execute_query(path_query, {"user_uid": user_uid, **path_params})
        if path_result.is_error:
            return Result.fail(path_result)

        # Create step nodes and HAS_STEP relationships
        step_query = """
        MATCH (p:Entity {uid: $path_uid})
        CREATE (s:Entity {
            uid: $uid,
            entity_type: 'path_step',
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
        """
        for step_params in steps_params:
            step_result = await self.execute_query(step_query, step_params)
            if step_result.is_error:
                return Result.fail(step_result)

        self.logger.debug(f"Persisted path {path_params['uid']} with {len(steps_params)} steps")
        return Result.ok(True)

    async def entity_exists(self, uid: str) -> Result[bool]:
        """Check whether an Entity node with the given UID exists."""
        query = "MATCH (e:Entity {uid: $uid}) RETURN e.uid LIMIT 1"
        result = await self.execute_query(query, {"uid": uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok(bool(result.value))
