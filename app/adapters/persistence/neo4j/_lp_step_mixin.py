"""
LP Step Mixin
=============

Step and path reads for LpBackend.

Provides the HAS_STEP step reads, the path reads with their steps composed in,
and graph context queries. A path and its steps are written by the content-vault
sync (ADR-091); this mixin writes nothing.

Requires on concrete class:
    execute_query, logger  (provided by UniversalNeo4jBackend)

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.path_step import PathStep
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins
    import logging

from adapters.persistence.neo4j.query.cypher import build_publication_clause


def _step_row_sequence(row: dict[str, Any]) -> int:
    """Sort key for {step, sequence} join rows (None sequence sorts first as 0)."""
    sequence = row.get("sequence")
    return sequence if sequence is not None else 0


class _LpStepMixin:
    """Step and path reads.

    Domain backends that need LP step reads should add ``_LpStepMixin``
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
    # STEP READS (HAS_STEP edges)
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

    # ========================================================================
    # PATH READS (steps composed into metadata["steps"])
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

        Only a learning path: a uid naming any other entity is not found, so no
        other node — another user's task — is ever read back as a path.
        """
        query = f"""
        MATCH (p:{NeoLabel.LEARNING_PATH.value} {{uid: $uid}})
        OPTIONAL MATCH (p)-[r:HAS_STEP]->(s:Entity {{entity_type: 'path_step'}})
        WITH p, collect({{step: s, sequence: r.sequence}}) as steps_data
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
    ) -> Result[list[LearningPath]]:
        """
        List all learning paths, ordered by uid, with steps in ``metadata["steps"]``.

        The catalogue publishes no sort key: ``limit``/``offset`` are a pagination
        window, and a fixed order is what makes successive pages disjoint.
        """
        # Catalogue surface (/pathways/browse) — withholds draft-marked paths.
        # Composes the shared predicate rather than spelling it out; NULL-tolerant,
        # so the pre-``publication_state`` corpus keeps listing (Codex #1006).
        published, published_params = build_publication_clause("p")
        query = f"""
        MATCH (p:Entity {{entity_type: 'learning_path'}})
        WHERE {published}
        OPTIONAL MATCH (p)-[r:HAS_STEP]->(s:Entity {{entity_type: 'path_step'}})
        WITH p, collect({{step: s, sequence: r.sequence}}) as steps_data
        ORDER BY p.uid ASC
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
