"""
User Progress Backend
=====================

Backend for user learning progress graph operations.
Does NOT extend UniversalNeo4jBackend — takes a Neo4jQueryExecutor directly.

Migrates 15 execute_query calls from UserProgressService.

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor


class UserProgressBackend:
    """Read/write backend for user learning progress operations."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    # ========================================================================
    # Profile Building
    # ========================================================================

    async def get_user_username(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get user's username by UID."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})
            RETURN u.username as username
            """,
            {"user_uid": user_uid},
        )

    async def get_mastered_knowledge(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all mastered knowledge for user with relationship properties."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[r:MASTERED]->(k:Entity)
            RETURN
                k.uid as knowledge_uid,
                r.mastery_score as mastery_score,
                r.achieved_at as achieved_at,
                r.practice_count as practice_count,
                r.last_practiced as last_practiced,
                r.confidence_level as confidence_level,
                r.retention_score as retention_score
            ORDER BY r.last_practiced DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_in_progress_knowledge(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all in-progress knowledge for user."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[r:IN_PROGRESS]->(k:Entity)
            RETURN
                k.uid as knowledge_uid,
                r.progress as progress,
                r.started_at as started_at,
                r.estimated_completion as estimated_completion,
                r.time_invested_minutes as time_invested_minutes,
                r.difficulty_rating as difficulty_rating,
                r.last_accessed as last_accessed
            ORDER BY r.last_accessed DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_completed_prerequisites(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all prerequisites that user has completed (mastered entities that are prereqs)."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:MASTERED]->(mastered:Entity)
            MATCH (target:Entity)-[:REQUIRES_KNOWLEDGE]->(mastered)
            RETURN DISTINCT mastered.uid as prereq_uid
            """,
            {"user_uid": user_uid},
        )

    async def get_prerequisite_map(self) -> Result[list[dict[str, Any]]]:
        """Build map of knowledge units to their prerequisites."""
        return await self._executor.execute_query(
            """
            MATCH (k:Entity)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
            RETURN k.uid as knowledge_uid, collect(prereq.uid) as prereq_uids
            """,
        )

    async def get_active_learning_paths(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get user's active (enrolled) learning paths."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[e:ENROLLED]->(p:Lp)
            WHERE e.enrollment_status = 'active'
            RETURN collect(p.uid) as active_paths
            """,
            {"user_uid": user_uid},
        )

    async def get_completed_learning_paths(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get user's completed learning paths."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[c:COMPLETED]->(p:Lp)
            RETURN collect(p.uid) as completed_paths
            """,
            {"user_uid": user_uid},
        )

    async def get_interested_knowledge(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get knowledge units user is interested in."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:INTERESTED_IN]->(k:Entity)
            RETURN collect(k.uid) as interested_uids
            """,
            {"user_uid": user_uid},
        )

    async def get_bookmarked_knowledge(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get bookmarked knowledge units."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:BOOKMARKED]->(k:Entity)
            RETURN collect(k.uid) as bookmarked_uids
            """,
            {"user_uid": user_uid},
        )

    async def get_struggling_knowledge(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get knowledge units user is struggling with."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:STRUGGLING_WITH]->(k:Entity)
            RETURN collect(k.uid) as struggling_uids
            """,
            {"user_uid": user_uid},
        )

    async def get_needs_review_knowledge(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get knowledge units that need review (due today or earlier)."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[r:NEEDS_REVIEW]->(k:Entity)
            WHERE r.next_review_due <= date()
            RETURN collect(k.uid) as review_uids
            """,
            {"user_uid": user_uid},
        )

    # ========================================================================
    # Readiness Calculation
    # ========================================================================

    async def get_prerequisites_for_entity(self, target_uid: str) -> Result[list[dict[str, Any]]]:
        """Get prerequisite UIDs and count for a target entity."""
        return await self._executor.execute_query(
            """
            MATCH (target:Entity {uid: $target_uid})
            OPTIONAL MATCH (target)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
            WITH target, collect(prereq.uid) as prereq_uids
            RETURN
                size(prereq_uids) as total_prereqs,
                prereq_uids
            """,
            {"target_uid": target_uid},
        )

    # ========================================================================
    # Mastery & Progress Tracking
    # ========================================================================

    async def record_mastery(
        self,
        user_uid: str,
        knowledge_uid: str,
        mastery_score: float,
        practice_count: int,
        confidence_level: float,
    ) -> Result[list[dict[str, Any]]]:
        """Create/update MASTERED relationship and remove IN_PROGRESS if exists."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid}), (k:Entity {uid: $knowledge_uid})
            MERGE (u)-[r:MASTERED]->(k)
            ON CREATE SET
                r.mastery_score = $mastery_score,
                r.achieved_at = datetime(),
                r.practice_count = $practice_count,
                r.last_practiced = datetime(),
                r.confidence_level = $confidence_level,
                r.retention_score = $mastery_score
            ON MATCH SET
                r.mastery_score = $mastery_score,
                r.practice_count = r.practice_count + 1,
                r.last_practiced = datetime(),
                r.confidence_level = $confidence_level,
                r.retention_score = ($mastery_score + r.retention_score) / 2.0

            // Remove IN_PROGRESS if it exists
            WITH u, k
            OPTIONAL MATCH (u)-[ip:IN_PROGRESS]->(k)
            DETACH DELETE ip
            """,
            {
                "user_uid": user_uid,
                "knowledge_uid": knowledge_uid,
                "mastery_score": mastery_score,
                "practice_count": practice_count,
                "confidence_level": confidence_level,
            },
        )

    async def record_progress(
        self,
        user_uid: str,
        knowledge_uid: str,
        progress: float,
        time_invested_minutes: int,
        difficulty_rating: float,
    ) -> Result[list[dict[str, Any]]]:
        """Create/update IN_PROGRESS relationship."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid}), (k:Entity {uid: $knowledge_uid})
            MERGE (u)-[r:IN_PROGRESS]->(k)
            ON CREATE SET
                r.progress = $progress,
                r.started_at = datetime(),
                r.time_invested_minutes = $time_invested,
                r.last_accessed = datetime(),
                r.difficulty_rating = $difficulty_rating
            ON MATCH SET
                r.progress = $progress,
                r.time_invested_minutes = r.time_invested_minutes + $time_invested,
                r.last_accessed = datetime()
            """,
            {
                "user_uid": user_uid,
                "knowledge_uid": knowledge_uid,
                "progress": progress,
                "time_invested": time_invested_minutes,
                "difficulty_rating": difficulty_rating,
            },
        )

    # ========================================================================
    # Knowledge Coverage Analytics
    # ========================================================================

    async def calculate_knowledge_coverage(
        self, user_uid: str, domain: str | None
    ) -> Result[list[dict[str, Any]]]:
        """Calculate coverage of learned knowledge over unlearned topics."""
        return await self._executor.execute_query(
            """
            // Get learned knowledge UIDs
            MATCH (user:User {uid: $user_uid})-[:HAS_PROGRESS]->(up:UserProgress)
                -[:FOR_KNOWLEDGE]->(learned:Entity)
            WHERE up.mastery_level >= 0.7
            WITH collect(learned.uid) as learned_uids

            // Get unlearned knowledge
            MATCH (unlearned:Entity)
            WHERE NOT unlearned.uid IN learned_uids
              AND ($domain IS NULL OR unlearned.domain = $domain)

            // Calculate coverage for each unlearned topic
            OPTIONAL MATCH (unlearned)-[r:REQUIRES_KNOWLEDGE]->(prereq:Entity)
            WHERE prereq.uid IN learned_uids // Only count learned prerequisites

            WITH unlearned,
                 learned_uids,
                 collect(DISTINCT prereq.uid) as satisfied_prereqs,
                 avg(coalesce(r.confidence, 1.0)) as avg_prerequisite_confidence

            // Count total prerequisites (learned or not)
            OPTIONAL MATCH (unlearned)-[:REQUIRES_KNOWLEDGE]->(any_prereq:Entity)
            WITH unlearned,
                 satisfied_prereqs,
                 avg_prerequisite_confidence,
                 count(DISTINCT any_prereq) as total_prereqs

            // Calculate coverage ratio
            WITH unlearned,
                 satisfied_prereqs,
                 total_prereqs,
                 CASE
                     WHEN total_prereqs = 0 THEN 1.0 // No prereqs = ready
                     ELSE toFloat(size(satisfied_prereqs)) / total_prereqs
                 END as coverage_ratio,
                 avg_prerequisite_confidence

            RETURN {
                uid: unlearned.uid,
                title: unlearned.title,
                domain: unlearned.domain,
                coverage_ratio: coverage_ratio,
                confidence: coalesce(avg_prerequisite_confidence, 1.0),
                satisfied_prereqs: size(satisfied_prereqs),
                total_prereqs: total_prereqs,
                ready_to_learn: coverage_ratio >= 0.8
            } as topic
            ORDER BY coverage_ratio DESC, topic.confidence DESC
            """,
            {"user_uid": user_uid, "domain": domain},
        )
