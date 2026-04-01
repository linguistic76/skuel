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

from core.models.type_hints import UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins
    import logging

    from core.models.type_hints import Neo4jProperties


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
        self, user_uid: UserUID, ku_uid: str, now: str, mastery_score: float, method: str
    ) -> Result[list[Neo4jProperties]]:
        """MERGE MASTERED relationship with score comparison."""
        query = """
        MATCH (user:User {uid: $user_uid})
        MATCH (ku:Entity {uid: $ku_uid})
        MERGE (user)-[r:MASTERED]->(ku)
        ON CREATE SET
            r.mastered_at = datetime($now),
            r.mastery_score = $mastery_score,
            r.confidence = $mastery_score,
            r.method = $method
        ON MATCH SET
            r.mastery_score = CASE
                WHEN $mastery_score > r.mastery_score THEN $mastery_score
                ELSE r.mastery_score
            END,
            r.confidence = CASE
                WHEN $mastery_score > coalesce(r.confidence, 0) THEN $mastery_score
                ELSE r.confidence
            END,
            r.method = $method
        RETURN r.mastery_score as mastery_score
        """
        return await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "ku_uid": ku_uid,
                "now": now,
                "mastery_score": mastery_score,
                "method": method,
            },
        )

    async def count_in_progress_path_steps(self, user_uid: UserUID) -> Result[list["Neo4jProperties"]]:
        """Count PathSteps with an IN_PROGRESS relationship for a user."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:IN_PROGRESS]->(ps:Entity:PathStep)
        RETURN count(ps) AS cnt
        """
        return await self.execute_query(query, {"user_uid": user_uid})

    async def get_in_progress_path_step_uids(self, user_uid: UserUID) -> Result[list["Neo4jProperties"]]:
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
        """Fetch all user-entity learning relationships in one query."""
        query = """
        MATCH (ku:Entity {uid: $ku_uid})
        OPTIONAL MATCH (u:User {uid: $user_uid})-[v:VIEWED]->(ku)
        OPTIONAL MATCH (u:User {uid: $user_uid})-[p:IN_PROGRESS]->(ku)
        OPTIONAL MATCH (u:User {uid: $user_uid})-[m:MASTERED]->(ku)
        OPTIONAL MATCH (u:User {uid: $user_uid})-[mr:MARKED_AS_READ]->(ku)
        OPTIONAL MATCH (u:User {uid: $user_uid})-[bk:BOOKMARKED]->(ku)
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
        """Batch query learning states for multiple KUs."""
        query = """
        UNWIND $ku_uids as ku_uid
        MATCH (ku:Entity {uid: ku_uid})
        OPTIONAL MATCH (u:User {uid: $user_uid})-[v:VIEWED]->(ku)
        OPTIONAL MATCH (u:User {uid: $user_uid})-[p:IN_PROGRESS]->(ku)
        OPTIONAL MATCH (u:User {uid: $user_uid})-[m:MASTERED]->(ku)
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
        """Find PathSteps where all KUs are mastered after a KU mastery event."""
        query = """
        MATCH (ps:Entity:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        WITH ps
        MATCH (ps)-[:USES_KU|CONTAINS_KNOWLEDGE]->(all_ku:Entity)
        WITH ps, collect(DISTINCT all_ku.uid) as all_ku_uids, count(DISTINCT all_ku) as total
        OPTIONAL MATCH (user:User {uid: $user_uid})-[:MASTERED]->(mastered_ku:Entity)
        WHERE mastered_ku.uid IN all_ku_uids
        WITH ps, total, count(DISTINCT mastered_ku) as mastered_count, all_ku_uids
        WHERE mastered_count = total
        RETURN ps.uid as ps_uid, ps.title as ps_title, all_ku_uids
        """
        return await self.execute_query(query, {"ku_uid": ku_uid, "user_uid": user_uid})

    async def get_bookmarked_kus(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get all bookmarked KU UIDs for a user."""
        query = """
        MATCH (user:User {uid: $user_uid})-[r:BOOKMARKED]->(ku:Entity)
        RETURN ku.uid as ku_uid
        ORDER BY r.bookmarked_at DESC
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

    # ========================================================================
    # USER LEARNING CONTEXT (migrated from ContextRetriever)
    # ========================================================================

    async def get_user_learning_context(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get complete user learning context in a single query.

        Retrieves:
        - Current knowledge state (mastered, learning, blocked)
        - Active learning paths with progress
        - Related tasks and goals
        - Knowledge prerequisites and relationships

        Returns:
            Single record with 'context' key containing structured learning state.
        """
        query = """
        MATCH (u:User {uid: $user_uid})

        // Knowledge state
        OPTIONAL MATCH (u)-[:MASTERED]->(mastered:Entity)
        OPTIONAL MATCH (u)-[:LEARNING]->(learning:Entity)

        // Blocked knowledge - KUs required by tasks but not mastered
        OPTIONAL MATCH (u)-[:HAS_TASK]->(t:Task)-[:APPLIES_KNOWLEDGE]->(blocked_ku:Entity)
        WHERE NOT (u)-[:MASTERED]->(blocked_ku)

        // Learning paths
        OPTIONAL MATCH (u)-[:ENROLLED_IN]->(lp:Lp)

        // Active tasks
        OPTIONAL MATCH (u)-[:HAS_TASK]->(task:Task)
        WHERE task.status IN ['pending', 'in_progress']

        // Active goals
        OPTIONAL MATCH (u)-[:HAS_GOAL]->(goal:Goal)
        WHERE goal.status = 'active'

        // Prerequisites for blocked knowledge (limited depth)
        OPTIONAL MATCH (blocked_ku)-[:REQUIRES_KNOWLEDGE*1..3]->(prereq:Entity)
        WHERE NOT (u)-[:MASTERED]->(prereq)

        WITH u,
             collect(DISTINCT mastered) AS mastered_knowledge,
             collect(DISTINCT learning) AS learning_knowledge,
             collect(DISTINCT blocked_ku) AS blocked_knowledge,
             collect(DISTINCT lp) AS learning_paths,
             collect(DISTINCT task) AS active_tasks,
             collect(DISTINCT goal) AS active_goals,
             collect(DISTINCT prereq) AS unmastered_prerequisites

        RETURN {
            user_uid: u.uid,
            mastered_knowledge: [ku IN mastered_knowledge | {uid: ku.uid, title: ku.title, mastery_level: 1.0}],
            learning_knowledge: [ku IN learning_knowledge | {uid: ku.uid, title: ku.title, mastery_level: 0.5}],
            blocked_knowledge: [ku IN blocked_knowledge | {uid: ku.uid, title: ku.title, mastery_level: 0.0}],
            learning_paths: [lp IN learning_paths | {uid: lp.uid, title: lp.title}],
            active_tasks: [t IN active_tasks | {uid: t.uid, title: t.title, status: t.status}],
            active_goals: [g IN active_goals | {uid: g.uid, title: g.title, status: g.status}],
            unmastered_prerequisites: [ku IN unmastered_prerequisites | {uid: ku.uid, title: ku.title}]
        } AS context
        """
        return await self.execute_query(query, {"user_uid": user_uid})
