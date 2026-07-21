"""
LP Progress Mixin
=================

KU mastery progress tracking and search operations for LpBackend.

Provides KU-path relationship queries, mastery progress calculation,
goal alignment search, knowledge-based search, prioritized listing,
and step-path lookup.

Requires on concrete class:
    execute_query, logger  (provided by UniversalNeo4jBackend)

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.pathways.learning_path import LearningPath
from core.models.type_hints import Neo4jProperties, UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins
    import logging


class _LpProgressMixin:
    """KU mastery progress tracking and search operations.

    Domain backends that need LP progress tracking and search should add
    ``_LpProgressMixin`` to their class bases.

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
    # KU MASTERY PROGRESS TRACKING
    # ========================================================================

    async def get_paths_containing_ku(self, ku_uid: str) -> Result[list[str]]:
        """
        Return the UIDs of all learning paths that include the given KU.

        Used by LpProgressService to find which LPs to update when a KU is mastered.

        Args:
            ku_uid: Knowledge Unit UID

        Returns:
            Result containing list of LP UIDs
        """
        # A learning path reaches a Ku two ways: directly, via the ingestible
        # `connections.required_knowledge` prerequisite edge (LP_CONFIG), or —
        # the normal case — through its PathSteps, which are what actually
        # compose Kus. There is no LP→Ku containment edge: INCLUDES_KU was never
        # a RelationshipName member and the live graph has no LearningPath→Ku
        # relationship of any type (findings §8).
        query = """
        MATCH (lp:Entity {entity_type: 'learning_path'})-[:REQUIRES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        RETURN DISTINCT lp.uid as lp_uid
        UNION
        MATCH (lp:Entity {entity_type: 'learning_path'})-[:HAS_STEP]->(:Entity)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku:Entity {uid: $ku_uid})
        RETURN DISTINCT lp.uid as lp_uid
        """
        result = await self.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        return Result.ok([record["lp_uid"] for record in records])

    async def get_ku_mastery_progress(
        self, lp_uid: str, user_uid: UserUID
    ) -> Result[Neo4jProperties]:
        """
        Return total and mastered KU counts for a user's progress in a learning path.

        Used by LpProgressService to calculate new progress percentage after a KU
        is mastered.

        Args:
            lp_uid: Learning Path UID
            user_uid: User UID

        Returns:
            Result containing dict with 'total_kus' and 'mastered_kus' keys,
            or empty dict if the learning path contains no KUs.
        """
        # Same two routes to the path's Kus as get_paths_containing_ku. Both
        # legs are OPTIONAL and the mastery test is an EXISTS predicate rather
        # than a MATCH: a user who has mastered nothing must read as 0-of-N, not
        # collapse the query to zero rows, which the service would report as
        # "this path has no Kus".
        query = """
        MATCH (lp:Entity {uid: $lp_uid})
        OPTIONAL MATCH (lp)-[:REQUIRES_KNOWLEDGE]->(direct_ku:Entity)
        WITH lp, collect(DISTINCT direct_ku) as direct_kus
        OPTIONAL MATCH (lp)-[:HAS_STEP]->(:Entity)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(step_ku:Entity)
        WITH direct_kus, collect(DISTINCT step_ku) as step_kus
        WITH direct_kus + step_kus as candidate_kus
        UNWIND (CASE WHEN size(candidate_kus) = 0 THEN [null] ELSE candidate_kus END) as ku
        WITH [k IN collect(DISTINCT ku) WHERE k IS NOT NULL] as lp_kus
        RETURN
            size(lp_kus) as total_kus,
            size([k IN lp_kus
                  WHERE EXISTS { (:User {uid: $user_uid})-[:MASTERED]->(k) }]) as mastered_kus
        """
        result = await self.execute_query(query, {"lp_uid": lp_uid, "user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok({})
        return Result.ok(dict(records[0]))

    # ========================================================================
    # SEARCH QUERIES (migrated from LpSearchService / LpProgressService)
    # ========================================================================

    def _records_to_paths(
        self, result: Result[builtins.list[dict[str, Any]]], node_key: str = "lp"
    ) -> Result[builtins.list[LearningPath]]:
        """Convert raw LP node records to LearningPath models (Tier 6: conversion
        lives below the hexagonal boundary — services receive typed models)."""
        from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node

        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [from_neo4j_node(record[node_key], LearningPath) for record in (result.value or [])]
        )

    async def get_paths_aligned_with_goal(
        self, goal_uid: str, limit: int = 50
    ) -> Result[list[LearningPath]]:
        """Get learning paths aligned with a specific goal via ALIGNED_WITH_GOAL.

        Args:
            goal_uid: Goal UID
            limit: Maximum results

        Returns:
            Result containing LearningPath models
        """
        query = """
        MATCH (lp:Entity {entity_type: 'learning_path'})-[:ALIGNED_WITH_GOAL]->(g:Goal {uid: $goal_uid})
        RETURN lp
        ORDER BY lp.updated_at DESC
        LIMIT $limit
        """
        return self._records_to_paths(
            await self.execute_query(query, {"goal_uid": goal_uid, "limit": limit})
        )

    async def get_paths_by_knowledge(
        self, ku_uid: str, limit: int = 20
    ) -> Result[list[LearningPath]]:
        """Get learning paths that teach a knowledge unit (2-hop via HAS_STEP + the PS→KU edge union).

        Traverses the canonical ``USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU`` union
        (matching the sibling ``get_paths_containing_ku``) so API-created paths —
        which compose Kus via ``USES_KU`` only — are not invisible to search.
        Uses DISTINCT since multiple steps within a path may contain the same knowledge.

        Args:
            ku_uid: Knowledge unit UID
            limit: Maximum results

        Returns:
            Result containing LearningPath models
        """
        query = """
        MATCH (ku:Entity {uid: $ku_uid})<-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]-(ps:Entity {entity_type: 'path_step'})<-[:HAS_STEP]-(lp:Entity {entity_type: 'learning_path'})
        RETURN DISTINCT lp
        ORDER BY lp.created_at DESC
        LIMIT $limit
        """
        return self._records_to_paths(
            await self.execute_query(query, {"ku_uid": ku_uid, "limit": limit})
        )

    async def get_user_paths_prioritized(
        self, user_uid: UserUID, limit: int = 20
    ) -> Result[list[LearningPath]]:
        """Get learning paths prioritized by enrollment, goal alignment, and type.

        Args:
            user_uid: User UID for personalization
            limit: Maximum results

        Returns:
            Result containing LearningPath models
        """
        query = """
        MATCH (lp:Entity {entity_type: 'learning_path'})
        OPTIONAL MATCH (u:User {uid: $user_uid})-[enrolled:ENROLLED_IN]->(lp)
        OPTIONAL MATCH (lp)-[:ALIGNED_WITH_GOAL]->(g:Goal)<-[:OWNS]-(u2:User {uid: $user_uid})
        WITH lp, enrolled, count(g) as goal_alignment
        RETURN lp
        ORDER BY
            CASE
                WHEN enrolled IS NOT NULL THEN 0
                ELSE 1
            END,
            goal_alignment DESC,
            CASE lp.path_type
                WHEN 'adaptive' THEN 0
                WHEN 'structured' THEN 1
                WHEN 'accelerated' THEN 2
                WHEN 'remedial' THEN 3
                ELSE 4
            END,
            lp.updated_at DESC
        LIMIT $limit
        """
        return self._records_to_paths(
            await self.execute_query(query, {"user_uid": user_uid, "limit": limit})
        )

    async def get_paths_containing_step(self, ps_uid: str) -> Result[list[str]]:
        """Get UIDs of all learning paths containing a given path step via HAS_STEP.

        Used by LpProgressService when handling PathStepCompleted events.

        Args:
            ps_uid: PathStep UID

        Returns:
            Result containing list of LP UIDs
        """
        query = """
        MATCH (lp:Entity {entity_type: 'learning_path'})-[:HAS_STEP]->(ps:Entity {uid: $ps_uid})
        RETURN DISTINCT lp.uid as lp_uid
        """
        result = await self.execute_query(query, {"ps_uid": ps_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([r["lp_uid"] for r in (result.value or [])])
