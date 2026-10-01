"""
Learning State Mixin
====================

User progress tracking operations for domain backends.

Manages learning-state relationships between User and Entity nodes:
VIEWED, IN_PROGRESS, MASTERED, MARKED_AS_READ, BOOKMARKED.

These methods are entity-agnostic internally (they operate on :Entity + :User
nodes), enabling reuse by any curriculum backend — not just PsBackend.

Requires on concrete class:
    execute_query, logger  (provided by UniversalNeo4jBackend)

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.query.cypher import build_publication_clause
from core.models.type_hints import UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins
    import logging

    from core.models.type_hints import Neo4jProperties
    from core.ports.query_types import MasteredWriteRow, StepMasteryGapRow


def to_mastered_write_rows(
    records: list[dict[str, Any]],  # boundary: raw neo4j-driver rows (AsyncResult.data())
) -> list[MasteredWriteRow]:
    """Project a MASTERED writer's rows onto MasteredWriteRow (KeyError on alias drift).

    Shared by every writer of the edge — ``_LearningStateMixin.mark_mastered``,
    ``KuBackend.mark_mastered`` and ``UserBackend.record_knowledge_mastery`` —
    so the transition flag has one spelling.
    """
    return [
        {"mastery_score": float(row["mastery_score"]), "was_mastered": bool(row["was_mastered"])}
        for row in records
    ]


class _LearningStateMixin:
    """User progress tracking operations (VIEWED, IN_PROGRESS, MASTERED, etc.).

    Domain backends that track learning state should add ``_LearningStateMixin``
    to their class bases. All methods are entity-agnostic — they operate on
    :Entity and :User nodes without filtering by entity_type.

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
    # STATE TRANSITION METHODS
    # ========================================================================

    async def record_view(
        self, user_uid: UserUID, ku_uid: str, now: str, time_spent: int
    ) -> Result[list[Neo4jProperties]]:
        """MERGE VIEWED relationship with timestamp and count tracking."""
        query = """
        MATCH (u:User {uid: $user_uid})
        MATCH (ku:Entity {uid: $ku_uid})
        MERGE (u)-[r:VIEWED]->(ku)
        ON CREATE SET
            r.first_viewed_at = datetime($now),
            r.last_viewed_at = datetime($now),
            r.view_count = 1,
            r.time_spent_seconds = $time_spent
        ON MATCH SET
            r.last_viewed_at = datetime($now),
            r.view_count = COALESCE(r.view_count, 0) + 1,
            r.time_spent_seconds = COALESCE(r.time_spent_seconds, 0) + $time_spent
        RETURN r.view_count as view_count
        """
        return await self.execute_query(
            query,
            {"user_uid": user_uid, "ku_uid": ku_uid, "now": now, "time_spent": time_spent},
        )

    async def mark_in_progress(
        self, user_uid: UserUID, ku_uid: str, now: str
    ) -> Result[list[Neo4jProperties]]:
        """MERGE IN_PROGRESS relationship."""
        query = """
        MATCH (u:User {uid: $user_uid})
        MATCH (ku:Entity {uid: $ku_uid})
        MERGE (u)-[r:IN_PROGRESS]->(ku)
        ON CREATE SET
            r.started_at = datetime($now),
            r.last_activity_at = datetime($now),
            r.progress_score = 0.0
        ON MATCH SET
            r.last_activity_at = datetime($now)
        RETURN true as success
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid, "now": now})

    async def mark_as_learning(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Delete MARKED_AS_READ and ensure IN_PROGRESS (Review again action)."""
        query = """
        MATCH (u:User {uid: $user_uid})
        MATCH (ku:Entity {uid: $ku_uid})
        OPTIONAL MATCH (u)-[r:MARKED_AS_READ]->(ku)
        DELETE r
        MERGE (u)-[ip:IN_PROGRESS]->(ku)
        ON CREATE SET ip.started_at = datetime(), ip.last_activity_at = datetime(), ip.progress_score = 0.0
        ON MATCH SET ip.last_activity_at = datetime()
        RETURN true AS success
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})

    async def mark_as_read(self, user_uid: UserUID, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """MERGE MARKED_AS_READ relationship."""
        query = """
        MATCH (user:User {uid: $user_uid})
        MATCH (ku:Entity {uid: $ku_uid})
        MERGE (user)-[r:MARKED_AS_READ]->(ku)
        ON CREATE SET r.marked_at = datetime()
        RETURN r
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})

    async def mark_mastered(
        self, user_uid: UserUID, entity_uid: str, now: str, mastery_score: float, method: str
    ) -> Result[list[MasteredWriteRow]]:
        """MERGE the MASTERED edge onto a Ku or a PathStep; the higher score wins.

        One writer, one edge shape for both targets: ``mastered_at`` (the
        caller's ISO instant), ``mastery_score``, ``confidence``, ``method``.
        Mastery is the terminal learning state, so the entity's IN_PROGRESS
        edge is retired in the same statement — a mastered step holds no
        enrollment-cap slot (``count_in_progress_path_steps``).

        Reports ``was_mastered`` — whether the edge existed before this write —
        so the caller publishes on the transition only, never on a repeat. The
        verdict is decided BY the write (ADR-087): ``MERGE`` sets a marker in
        its ``ON CREATE`` / ``ON MATCH`` branch, under the lock it holds on the
        pair, and the marker is removed before the row is returned. A read
        taken before the ``MERGE`` would let two concurrent first writes both
        report a transition.
        """
        query = """
        MATCH (user:User {uid: $user_uid})
        MATCH (entity:Entity {uid: $entity_uid})
        MERGE (user)-[r:MASTERED]->(entity)
        ON CREATE SET
            r.mastered_at = datetime($now),
            r.mastery_score = $mastery_score,
            r.confidence = $mastery_score,
            r.method = $method,
            r.transition = true
        ON MATCH SET
            r.mastery_score = CASE
                WHEN $mastery_score > r.mastery_score THEN $mastery_score
                ELSE r.mastery_score
            END,
            r.confidence = CASE
                WHEN $mastery_score > coalesce(r.confidence, 0) THEN $mastery_score
                ELSE r.confidence
            END,
            r.method = $method,
            r.transition = false
        WITH user, entity, r, NOT r.transition AS was_mastered
        REMOVE r.transition
        WITH user, entity, r, was_mastered
        OPTIONAL MATCH (user)-[ip:IN_PROGRESS]->(entity)
        DELETE ip
        RETURN r.mastery_score AS mastery_score, was_mastered
        """
        result = await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "entity_uid": entity_uid,
                "now": now,
                "mastery_score": mastery_score,
                "method": method,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(to_mastered_write_rows(result.value or []))

    async def count_in_progress_path_steps(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Count PathSteps with an IN_PROGRESS relationship for a user."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:IN_PROGRESS]->(ps:Entity:PathStep)
        RETURN count(ps) AS cnt
        """
        return await self.execute_query(query, {"user_uid": user_uid})

    async def get_in_progress_path_step_uids(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get UIDs of PathSteps the user is enrolled in (IN_PROGRESS)."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:IN_PROGRESS]->(ps:Entity:PathStep)
        RETURN ps.uid AS uid
        ORDER BY ps.title
        """
        return await self.execute_query(query, {"user_uid": user_uid})

    # ========================================================================
    # BOOKMARK OPERATIONS
    # ========================================================================

    async def check_bookmark(self, user_uid: UserUID, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Check if BOOKMARKED relationship exists."""
        query = """
        MATCH (user:User {uid: $user_uid})-[r:BOOKMARKED]->(ku:Entity {uid: $ku_uid})
        RETURN r IS NOT NULL as is_bookmarked
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})

    async def delete_bookmark(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Delete BOOKMARKED relationship."""
        query = """
        MATCH (user:User {uid: $user_uid})-[r:BOOKMARKED]->(ku:Entity {uid: $ku_uid})
        DELETE r
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})

    async def create_bookmark(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """MERGE BOOKMARKED relationship."""
        query = """
        MATCH (user:User {uid: $user_uid})
        MATCH (ku:Entity {uid: $ku_uid})
        MERGE (user)-[r:BOOKMARKED]->(ku)
        ON CREATE SET r.bookmarked_at = datetime()
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})

    # ========================================================================
    # QUERY OPERATIONS
    # ========================================================================

    async def get_learning_state_raw(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Fetch all user-entity learning relationships in one query.

        The user is bound ONCE, optionally, before the edge probes. Binding
        ``u`` inside the first OPTIONAL MATCH would null it for a learner with
        no VIEWED edge, and every later probe on ``u`` would then read null
        too — a step mastered without ever being viewed would report NONE.
        """
        query = """
        MATCH (ku:Entity {uid: $ku_uid})
        OPTIONAL MATCH (u:User {uid: $user_uid})
        OPTIONAL MATCH (u)-[v:VIEWED]->(ku)
        OPTIONAL MATCH (u)-[p:IN_PROGRESS]->(ku)
        OPTIONAL MATCH (u)-[m:MASTERED]->(ku)
        OPTIONAL MATCH (u)-[mr:MARKED_AS_READ]->(ku)
        OPTIONAL MATCH (u)-[bk:BOOKMARKED]->(ku)
        RETURN
            v IS NOT NULL as has_viewed,
            p IS NOT NULL as has_in_progress,
            m IS NOT NULL as has_mastered,
            mr IS NOT NULL as has_marked_as_read,
            bk IS NOT NULL as has_bookmarked,
            v.first_viewed_at as first_viewed_at,
            v.last_viewed_at as last_viewed_at,
            v.view_count as view_count,
            v.time_spent_seconds as time_spent_seconds,
            p.started_at as started_at,
            m.mastered_at as mastered_at
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})

    async def get_learning_states_batch_raw(
        self, user_uid: UserUID, ku_uids: list[str]
    ) -> Result[list[Neo4jProperties]]:
        """Batch query learning states for multiple KUs (user bound once, as above)."""
        query = """
        UNWIND $ku_uids as ku_uid
        MATCH (ku:Entity {uid: ku_uid})
        OPTIONAL MATCH (u:User {uid: $user_uid})
        OPTIONAL MATCH (u)-[v:VIEWED]->(ku)
        OPTIONAL MATCH (u)-[p:IN_PROGRESS]->(ku)
        OPTIONAL MATCH (u)-[m:MASTERED]->(ku)
        RETURN
            ku.uid as ku_uid,
            v IS NOT NULL as has_viewed,
            p IS NOT NULL as has_in_progress,
            m IS NOT NULL as has_mastered
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uids": ku_uids})

    async def detect_path_step_completion(
        self, ku_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Find PathSteps where all KUs are mastered after a KU mastery event.

        Uses the canonical PathStep→Ku triple. ``TRAINS_KU`` (a step's declared
        objectives, from ``trains_ku_uids``) counts toward completion exactly as
        ``USES_KU``/``CONTAINS_KNOWLEDGE`` (its content) does — a step whose
        objectives are unmastered is not complete.

        The composition targets counted are ``:Ku`` only: the edge writer
        (``create_step_node``) matches its target by uid alone, so a step can
        point one of these edges at another step, and a step's mastery is
        announced as ``PathStepCompleted`` — never ``KnowledgeMastered`` — so
        a non-Ku target in the tally would leave the parent underivable. The
        trigger is ``:Ku`` for the same reason from the other side: a mastery
        announced for a non-Ku uid must not enter the derivation, or a step
        whose only target is another step would tally 0 of 0 and be mastered.

        Publication-gated: a draft step is never derived. Its mastery would be
        a learner-state reference to curriculum the learner never saw, and the
        learner-state reads (``MASTERED_PATH_STEPS_QUERY``) carry no gate of
        their own. A step published later is a gap ``find_step_mastery_gaps``
        reports and the reconciler closes.
        """
        published, published_params = build_publication_clause("ps")
        query = f"""
        MATCH (ps:Entity:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku:Entity:Ku {{uid: $ku_uid}})
        WHERE {published}
        WITH ps
        MATCH (ps)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(all_ku:Entity:Ku)
        WITH ps, collect(DISTINCT all_ku.uid) as all_ku_uids, count(DISTINCT all_ku) as total
        OPTIONAL MATCH (user:User {{uid: $user_uid}})-[:MASTERED]->(mastered_ku:Entity)
        WHERE mastered_ku.uid IN all_ku_uids
        WITH ps, total, count(DISTINCT mastered_ku) as mastered_count, all_ku_uids
        WHERE mastered_count = total
        RETURN ps.uid as ps_uid, ps.title as ps_title, all_ku_uids
        """
        return await self.execute_query(
            query, {"ku_uid": ku_uid, "user_uid": user_uid, **published_params}
        )

    async def find_step_mastery_gaps(self) -> Result[list[StepMasteryGapRow]]:
        """Every (user, step) pair where the user has mastered all of the step's
        Kus and the step's own MASTERED edge is absent — across all users.

        The derived writer runs best-effort behind ``KnowledgeMastered``; a
        detection or write that failed after the Ku edge committed leaves this
        gap, and the transition event is not replayed. The reconciler reads the
        gaps from the graph's own state and closes them. The tally is ``:Ku``
        only and the step must be published, as in ``detect_path_step_completion``
        — which is also how a step published after its Kus were mastered gets
        its edge.
        """
        published, published_params = build_publication_clause("ps")
        query = f"""
        MATCH (ps:Entity:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku:Entity:Ku)
        WHERE {published}
        WITH ps, collect(DISTINCT ku) AS kus
        MATCH (user:User)-[:MASTERED]->(mastered:Entity)
        WHERE mastered IN kus
        WITH ps, kus, user, count(DISTINCT mastered) AS mastered_count
        WHERE mastered_count = size(kus) AND NOT EXISTS {{ (user)-[:MASTERED]->(ps) }}
        RETURN user.uid AS user_uid, ps.uid AS ps_uid
        ORDER BY user.uid, ps.uid
        """
        result = await self.execute_query(query, published_params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                {"user_uid": str(r["user_uid"]), "ps_uid": str(r["ps_uid"])}
                for r in (result.value or [])
            ]
        )

    async def get_bookmarked_kus(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get all bookmarked KU UIDs for a user."""
        query = """
        MATCH (user:User {uid: $user_uid})-[r:BOOKMARKED]->(ku:Entity)
        RETURN ku.uid as ku_uid
        ORDER BY datetime(r.bookmarked_at) DESC
        """
        return await self.execute_query(query, {"user_uid": user_uid})

    async def get_all_user_knowledge_status(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get all Ku entities with per-user interaction status."""
        query = """
        MATCH (ku:Entity:Ku)
        OPTIONAL MATCH (u:User {uid: $user_uid})-[v:VIEWED]->(ku)
        OPTIONAL MATCH (u2:User {uid: $user_uid})-[b:BOOKMARKED]->(ku)
        OPTIONAL MATCH (u3:User {uid: $user_uid})-[m:MASTERED]->(ku)
        OPTIONAL MATCH (u4:User {uid: $user_uid})-[ip:IN_PROGRESS]->(ku)
        RETURN ku.uid AS uid, ku.title AS title, ku.domain AS domain,
               v IS NOT NULL AS viewed,
               b IS NOT NULL AS bookmarked,
               m IS NOT NULL AS mastered,
               ip IS NOT NULL AS studying
        ORDER BY ku.title ASC, ku.uid ASC
        """
        return await self.execute_query(query, {"user_uid": user_uid})

    async def get_user_mastery(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get mastery level for a specific user-KU pair."""
        query = """
        MATCH (user:User {uid: $user_uid})-[r:MASTERED]->(ku:Entity {uid: $ku_uid})
        RETURN r.level as mastery
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})
