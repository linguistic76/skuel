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

from adapters.persistence.neo4j.query.cypher import build_publication_clause
from core.models.enums.curriculum_enums import EnrollmentStatus
from core.models.pathways.learning_path import LearningPath
from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.query_types import EnrollmentProgressGapRow
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
        # Discovery: the caller holds a GOAL, not these paths — this surfaces
        # curriculum it never referenced, so draft-marked paths are withheld
        # (same line as find_similar_knowledge). NULL-tolerant (#1006).
        published, published_params = build_publication_clause("lp")
        query = f"""
        MATCH (lp:Entity {{entity_type: 'learning_path'}})-[:ALIGNED_WITH_GOAL]->(g:Goal {{uid: $goal_uid}})
        WHERE {published}
        RETURN lp
        ORDER BY datetime(lp.updated_at) DESC
        LIMIT $limit
        """
        return self._records_to_paths(
            await self.execute_query(
                query, {"goal_uid": goal_uid, "limit": limit, **published_params}
            )
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
        # Discovery: anchored on a KU, this returns PATHS the caller never
        # referenced (the docstring calls it search) — draft paths withheld.
        # BOTH hops are gated (Codex P1, #1008): the claim being made is "this
        # path teaches that KU", and the bridging step is what carries it. A
        # published path whose only route to the KU is a DRAFT step would
        # otherwise be advertised as teaching it through unfinished content —
        # true of lp.mindfulness-101 for six KUs on the live graph. Matches the
        # sibling find_learning_paths_teaching_ku. NULL-tolerant (#1006).
        published_ps, ps_params = build_publication_clause("ps")
        published_lp, lp_params = build_publication_clause("lp")
        query = f"""
        MATCH (ku:Entity {{uid: $ku_uid}})<-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]-(ps:Entity {{entity_type: 'path_step'}})<-[:HAS_STEP]-(lp:Entity {{entity_type: 'learning_path'}})
        WHERE {published_ps} AND {published_lp}
        RETURN DISTINCT lp
        ORDER BY datetime(lp.created_at) DESC
        LIMIT $limit
        """
        return self._records_to_paths(
            await self.execute_query(
                query, {"ku_uid": ku_uid, "limit": limit, **ps_params, **lp_params}
            )
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
        # A MIXED surface (Codex P2, #1008), exactly like get_prioritized_steps:
        # an unanchored enumeration of every path (catalogue -> gated) that is
        # also ordered by the user's own enrolment (user-state -> NOT gated).
        # The gate lands AFTER the enrolment match and yields to it — a path the
        # learner is enrolled in is one they reference, and dropping it would
        # remove their own enrolment from the list built to prioritise it.
        published, published_params = build_publication_clause("lp")
        query = f"""
        MATCH (lp:Entity {{entity_type: 'learning_path'}})
        OPTIONAL MATCH (u:User {{uid: $user_uid}})-[enrolled:ENROLLED_IN]->(lp)
        WITH lp, enrolled
        WHERE enrolled IS NOT NULL OR {published}
        OPTIONAL MATCH (lp)-[:ALIGNED_WITH_GOAL]->(g:Goal)<-[:OWNS]-(u2:User {{uid: $user_uid}})
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
            datetime(lp.updated_at) DESC
        LIMIT $limit
        """
        return self._records_to_paths(
            await self.execute_query(
                query, {"user_uid": user_uid, "limit": limit, **published_params}
            )
        )

    async def record_enrollment_progress(
        self, user_uid: UserUID, lp_uid: str, now: str
    ) -> Result[list[Neo4jProperties]]:
        """Recompute the learner's progress in a path and record it on the
        ENROLLED_IN edge, in one statement under the edge's lock; report the
        prior progress, whether the enrollment was already completed, and the
        figure written.

        Progress and completion live on the enrollment edge (``r.progress``,
        ``r.status``), so this one write decides both transitions the chain
        announces: ``LearningPathProgressUpdated`` when the progress changed,
        ``LearningPathCompleted`` when the status flipped. Decided by the write
        (ADR-087, the recompute-under-the-lock shape): the edge's lock is taken
        first (``SET r.status = r.status``), the priors are read under it, the
        path's Kus and the learner's mastered ones are counted under it, and the
        new state is written from that count — so two handlers for different
        Kus of the same path cannot carry a stale fraction past each other, and
        two triggers for the same Ku (its mastery and the step completion it
        causes, or a reconciled step) see one transition between them.
        ``completed_at`` keeps its first value. No row: not enrolled.

        The path's Kus are the same two routes as ``get_paths_containing_ku``;
        both legs are OPTIONAL and the mastery test is an EXISTS predicate, so a
        learner who has mastered nothing reads as 0-of-N and an empty path as
        0-of-0 — never as a vanished row.
        """
        query = """
        MATCH (u:User {uid: $user_uid})-[r:ENROLLED_IN]->(lp:LearningPath {uid: $lp_uid})
        SET r.status = r.status
        WITH u, r, lp, coalesce(r.progress, 0.0) AS prior_progress,
             coalesce(r.status, $active) = $completed AS was_completed
        OPTIONAL MATCH (lp)-[:REQUIRES_KNOWLEDGE]->(direct_ku:Entity:Ku)
        WITH u, r, lp, prior_progress, was_completed, collect(DISTINCT direct_ku) AS direct_kus
        OPTIONAL MATCH (lp)-[:HAS_STEP]->(:Entity)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(step_ku:Entity:Ku)
        WITH u, r, prior_progress, was_completed, direct_kus, collect(DISTINCT step_ku) AS step_kus
        WITH u, r, prior_progress, was_completed, direct_kus + step_kus AS candidate_kus
        UNWIND (CASE WHEN size(candidate_kus) = 0 THEN [null] ELSE candidate_kus END) AS ku
        WITH u, r, prior_progress, was_completed,
             [k IN collect(DISTINCT ku) WHERE k IS NOT NULL] AS lp_kus
        WITH r, prior_progress, was_completed, size(lp_kus) AS total_kus,
             size([k IN lp_kus WHERE EXISTS { (u)-[:MASTERED]->(k) }]) AS mastered_kus
        WITH r, prior_progress, was_completed, total_kus, mastered_kus,
             CASE WHEN total_kus = 0 THEN 0.0 ELSE toFloat(mastered_kus) / total_kus END AS progress
        SET r.progress = progress,
            r.status = CASE WHEN progress >= 1.0 THEN $completed ELSE r.status END,
            r.completed_at = CASE
                WHEN progress >= 1.0 THEN coalesce(r.completed_at, datetime($now))
                ELSE r.completed_at
            END
        RETURN prior_progress, was_completed, progress, total_kus, mastered_kus
        """
        return await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "lp_uid": lp_uid,
                "now": now,
                "active": EnrollmentStatus.ACTIVE.value,
                "completed": EnrollmentStatus.COMPLETED.value,
            },
        )

    async def find_uninitialized_enrollments(self) -> Result[list[EnrollmentProgressGapRow]]:
        """Every enrollment whose progress was never recorded, across all users.

        ``record_enrollment_progress`` runs best-effort behind
        ``LearningPathStarted``; a recount that failed after the enrollment
        committed leaves ``r.progress`` absent, and the event is not replayed.
        The reconciler reads these from the graph's own state and recounts them.
        """
        query = """
        MATCH (u:User)-[r:ENROLLED_IN]->(lp:LearningPath)
        WHERE r.progress IS NULL
        RETURN u.uid AS user_uid, lp.uid AS lp_uid
        ORDER BY u.uid, lp.uid
        """
        result = await self.execute_query(query, {})
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                {"user_uid": str(r["user_uid"]), "lp_uid": str(r["lp_uid"])}
                for r in (result.value or [])
            ]
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
