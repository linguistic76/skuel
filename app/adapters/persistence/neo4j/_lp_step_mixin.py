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

from core.models.pathways.learning_path import LearningPath
from core.models.pathways.path_step import PathStep
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    import logging

from adapters.persistence.neo4j._backend_helpers import _ALLOWED_ORDER_BY
from adapters.persistence.neo4j.query.cypher import build_publication_clause


def _step_row_sequence(row: dict[str, Any]) -> int:
    """Sort key for {step, sequence} join rows (None sequence sorts first as 0)."""
    sequence = row.get("sequence")
    return sequence if sequence is not None else 0


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

    async def get_steps_raw(self, path_uid: str, depth: int = 1) -> Result[list[PathStep]]:
        """Get ordered steps in a learning path as typed models."""
        from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node

        query = f"""
        MATCH (lp:Entity {{uid: $path_uid}})-[r:HAS_STEP*1..{depth}]->(ps:Entity {{entity_type: 'path_step'}})
        RETURN ps, r[0].sequence as sequence
        ORDER BY sequence
        """
        result = await self.execute_query(query, {"path_uid": path_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [from_neo4j_node(dict(record["ps"]), PathStep) for record in (result.value or [])]
        )

    async def get_parent_path_raw(self, step_uid: str) -> Result[LearningPath | None]:
        """Get parent learning path for a step as a typed model, or None."""
        from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node

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
        return Result.ok(from_neo4j_node(dict(result.value[0]["lp"]), LearningPath))

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

    @staticmethod
    def _steps_from_steps_data(steps_data: list[dict[str, Any]]) -> list[PathStep]:
        """Convert ``[{step, sequence}, ...]`` join rows to ordered PathStep models."""
        from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node

        if not steps_data:
            return []
        ordered = sorted(steps_data, key=_step_row_sequence)
        steps: list[PathStep] = []
        for row in ordered:
            step_node = row.get("step") or row
            if step_node:
                step_dict = dict(step_node)
                if step_dict.get("uid"):
                    steps.append(from_neo4j_node(step_dict, PathStep))
        return steps

    @staticmethod
    def _record_to_path_with_steps(record: dict[str, Any], steps: list[PathStep]) -> LearningPath:
        """Build a LearningPath model from a ``p`` node record + pre-built steps.

        Steps (from HAS_STEP relationships) are stored in ``metadata["steps"]`` —
        the composed shape LpCoreService has always returned.
        """
        from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node

        path = from_neo4j_node(dict(record["p"]), LearningPath)
        metadata = path.metadata if path.metadata else {}
        metadata["steps"] = steps
        object.__setattr__(path, "metadata", metadata)
        return path

    async def get_path_with_steps(self, path_uid: str) -> Result[LearningPath | None]:
        """
        Get a single learning path (with its HAS_STEP steps in
        ``metadata["steps"]``) as a typed model, or None if not found.
        """
        query = """
        MATCH (p:Entity {uid: $uid})
        OPTIONAL MATCH (p)-[r:HAS_STEP]->(s:Entity {entity_type: 'path_step'})
        WITH p, collect({step: s, sequence: r.sequence}) as steps_data
        RETURN p, steps_data
        """
        result = await self.execute_query(query, {"uid": path_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(None)
        record = records[0]
        return Result.ok(
            self._record_to_path_with_steps(
                record, self._steps_from_steps_data(record["steps_data"])
            )
        )

    async def list_user_paths_with_steps(
        self, user_uid: UserUID, limit: int | None = None
    ) -> Result[list[LearningPath]]:
        """
        List a user's learning paths (authored via HAS_PATH or enrolled via
        ENROLLED_IN), with their steps.

        ENROLLED_IN is the edge the enroll route writes; reading HAS_PATH
        alone left every enrollment invisible on the pathways dashboard.

        Returns typed models with steps in ``metadata["steps"]``.
        """
        query = """
        MATCH (u:User {uid: $user_uid})-[:HAS_PATH|ENROLLED_IN]->(p:Entity {entity_type: 'learning_path'})
        WITH DISTINCT p
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
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                self._record_to_path_with_steps(
                    record, self._steps_from_steps_data(record["steps_data"])
                )
                for record in (result.value or [])
            ]
        )

    async def list_all_paths_with_steps(
        self,
        limit: int | None = None,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[list[LearningPath]]:
        """
        List all learning paths with pagination and safe sorting.

        Validates order_by against _ALLOWED_ORDER_BY to prevent Cypher injection.
        Returns typed models with steps in ``metadata["steps"]``.
        """
        validated_field = "uid"
        if order_by:
            if order_by not in _ALLOWED_ORDER_BY:
                return Result.fail(Errors.validation(f"Invalid order_by field: {order_by!r}"))
            validated_field = order_by

        order_direction = "DESC" if order_desc else "ASC"

        # Catalogue surface (/pathways/browse) — withholds draft-marked paths.
        # Composes the shared predicate rather than spelling it out; NULL-tolerant,
        # so the pre-``publication_state`` corpus keeps listing (Codex #1006).
        published, published_params = build_publication_clause("p")
        query = f"""
        MATCH (p:Entity {{entity_type: 'learning_path'}})
        WHERE {published}
        OPTIONAL MATCH (p)-[r:HAS_STEP]->(s:Entity {{entity_type: 'path_step'}})
        WITH p, collect({{step: s, sequence: r.sequence}}) as steps_data
        ORDER BY p.{validated_field} {order_direction}
        """
        if offset > 0:
            query += " SKIP $offset"
        if limit:
            query += " LIMIT $limit"
        query += " RETURN p, steps_data"

        params: dict[str, Any] = {"offset": offset, **published_params}
        if limit:
            params["limit"] = limit
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                self._record_to_path_with_steps(
                    record, self._steps_from_steps_data(record["steps_data"])
                )
                for record in (result.value or [])
            ]
        )

    async def update_path_properties(
        self, set_clauses: list[str], params: dict[str, Any]
    ) -> Result[LearningPath | None]:
        """
        Update a learning path's properties; return the updated path (with steps
        in ``metadata["steps"]``) as a typed model, or None if absent.

        Args:
            set_clauses: Pre-validated SET clause fragments (e.g. ['p.title = $title'])
            params: Query parameters including 'uid' and all SET values
        """
        from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node

        query = f"""
        MATCH (p:Entity {{uid: $uid}})
        SET {", ".join(set_clauses)}
        OPTIONAL MATCH (p)-[r:HAS_STEP]->(s:Entity {{entity_type: 'path_step'}})
        WITH p, collect(s) as steps
        RETURN p, steps
        """
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(None)
        record = records[0]
        steps = [
            from_neo4j_node(dict(step_node), PathStep)
            for step_node in record["steps"]
            if step_node and dict(step_node).get("uid")
        ]
        return Result.ok(self._record_to_path_with_steps(record, steps))

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
        Persist a learning path node with User relationship, then create step
        nodes and their PS→KU composition edges.

        Each step's ``knowledge_uids`` become ``(:PathStep)-[:USES_KU]->(:Ku)``
        edges (never a node property — knowledge_uids is reconstructed from these
        edges on read). Only existing Kus are linked: a missing KU yields no edge,
        mirroring ingestion (``link_to_ku``); placeholder Kus are never created.

        Args:
            user_uid: Owner user UID
            path_params: Properties for the path node
            steps_params: List of property dicts for each step node (each carrying
                a ``knowledge_uids`` list)
        """
        # Create path node and user relationship. The node carries the full
        # multi-label (:Entity:LearningPath) so domain-label reads — backend.get,
        # search — find it, matching how ingestion writes LP nodes (a bare
        # :Entity node is invisible to every domain-scoped query).
        path_query = """
        MERGE (u:User {uid: $user_uid})
        CREATE (p:Entity:LearningPath {
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

        # Create step nodes + HAS_STEP relationships, then wire PS→KU composition
        # edges (USES_KU) from the step's knowledge_uids. The step node is CREATEd
        # before the UNWIND, so it persists even when knowledge_uids is empty
        # (an empty UNWIND drops downstream rows without rolling back prior writes).
        # MATCH (not MERGE) the Ku so a missing KU yields no edge — never a
        # placeholder Ku — mirroring ingestion's link_to_ku.
        step_query = """
        MATCH (p:Entity {uid: $path_uid})
        CREATE (s:Entity:PathStep {
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
            created_at: datetime(),
            updated_at: datetime()
        })
        CREATE (p)-[:HAS_STEP {sequence: $sequence}]->(s)
        WITH s
        UNWIND $knowledge_uids AS ku_uid
        MATCH (ku:Entity {uid: ku_uid})
        MERGE (s)-[:USES_KU]->(ku)
        """
        for step_params in steps_params:
            step_result = await self.execute_query(step_query, step_params)
            if step_result.is_error:
                return Result.fail(step_result)

        self.logger.debug(f"Persisted path {path_params['uid']} with {len(steps_params)} steps")
        return Result.ok(True)

    async def get_next_step_sequence(self, path_uid: str) -> Result[int]:
        """Get the next available sequence number for a path's steps."""
        query = """
        MATCH (p:Entity {uid: $path_uid})-[r:HAS_STEP]->()
        RETURN coalesce(max(r.sequence), -1) + 1 as next_sequence
        """
        result = await self.execute_query(query, {"path_uid": path_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(0)
        return Result.ok(result.value[0].get("next_sequence", 0))

    async def entity_exists(self, uid: str) -> Result[bool]:
        """Check whether an Entity node with the given UID exists."""
        query = "MATCH (e:Entity {uid: $uid}) RETURN e.uid LIMIT 1"
        result = await self.execute_query(query, {"uid": uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok(bool(result.value))

    async def get_exercises_for_lp(self, lp_uid: str) -> Result[list[Neo4jProperties]]:
        """Get all Exercises reachable from an LP via HAS_STEP → HAS_EXERCISE traversal.

        Returns distinct exercises across all PathSteps in the LP, ordered by step
        sequence then exercise title. Includes path_step_uid/title so callers can
        group by step without a second query.

        Backend: (LP)-[:HAS_STEP]->(PS)-[:HAS_EXERCISE]->(Exercise)
        """
        query = f"""
        MATCH (lp:Entity {{uid: $lp_uid, entity_type: 'learning_path'}})
              -[step_rel:{RelationshipName.HAS_STEP}]->(ps:Entity {{entity_type: 'path_step'}})
              -[:{RelationshipName.HAS_EXERCISE}]->(ex:Entity {{entity_type: 'exercise'}})
        WITH ex, ps, step_rel.sequence AS step_sequence
        RETURN DISTINCT
               ex.uid AS uid,
               ex.title AS title,
               ex.scope AS scope,
               ex.estimated_time_minutes AS estimated_time_minutes,
               ps.uid AS path_step_uid,
               ps.title AS path_step_title,
               step_sequence
        ORDER BY step_sequence, ex.title
        """
        return await self.execute_query(query, {"lp_uid": lp_uid})
