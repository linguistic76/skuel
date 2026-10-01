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
    from core.ports.query_types import MasteredEntityUidRow


def _to_mastered_entity_uid_rows(
    records: list[dict[str, Any]],  # boundary: raw neo4j-driver rows (AsyncResult.data())
) -> list[MasteredEntityUidRow]:
    """Project raw rows onto MasteredEntityUidRow (KeyError on alias drift).

    Indexing the alias turns a renamed RETURN into a failed ``Result`` at the
    boundary instead of a silently-empty membership set downstream.
    """
    return [{"uid": str(row["uid"])} for row in records]


class UserProgressBackend:
    """Read/write backend for user learning progress operations."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    # ========================================================================
    # Profile Building
    # ========================================================================

    async def get_user_username(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get user's username by UID (stored in `title` — the User model's username field)."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})
            RETURN u.title as username
            """,
            {"user_uid": user_uid},
        )

    async def get_mastered_knowledge(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Every Ku the user has mastered, with the edge's properties.

        ``:Ku`` — a PathStep carries a MASTERED edge of its own (derived when its
        last Ku is mastered), and the knowledge list feeds concept counts
        (``concepts_mastered``) that must not grow by one per completed step.
        Membership across both kinds is ``get_mastered_entity_uids``.
        """
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[r:MASTERED]->(k:Entity:Ku)
            RETURN
                k.uid as knowledge_uid,
                r.mastery_score as mastery_score,
                r.achieved_at as achieved_at,
                r.practice_count as practice_count,
                r.last_practiced as last_practiced,
                r.confidence_level as confidence_level,
                r.retention_score as retention_score
            ORDER BY datetime(r.last_practiced) DESC
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
            ORDER BY datetime(r.last_accessed) DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_mastered_entity_uids(self, user_uid: str) -> Result[list[MasteredEntityUidRow]]:
        """The uid of every entity the user has mastered — a Ku or a PathStep.

        The membership set: a path page asks "is this step mastered?", a
        prerequisite chain asks it of Kus and steps alike. Counting is
        ``get_mastered_knowledge``'s job.
        """
        result = await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:MASTERED]->(e:Entity)
            RETURN e.uid AS uid
            """,
            {"user_uid": user_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(_to_mastered_entity_uid_rows(result.value or []))

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
        """Get user's active (enrolled) learning paths.

        Enrollment lifecycle lives on the ENROLLED_IN relationship's r.status
        (written by UserBackend.enroll_in_learning_path / complete_learning_path) —
        an ENROLLED edge with enrollment_status never had a writer.
        """
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[r:ENROLLED_IN]->(p:LearningPath)
            WHERE coalesce(r.status, 'active') IN ['active', 'in_progress']
            RETURN collect(p.uid) as active_paths
            """,
            {"user_uid": user_uid},
        )

    async def get_completed_learning_paths(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get user's completed learning paths.

        Reads r.status='completed' on ENROLLED_IN — the state
        UserBackend.complete_learning_path actually writes (a :COMPLETED edge
        to LearningPath never had a writer).
        """
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[r:ENROLLED_IN]->(p:LearningPath)
            WHERE r.status = 'completed'
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

    # NOTE: get_struggling_knowledge / get_needs_review_knowledge removed
    # (SKUEL030 tranche 3) — they matched :STRUGGLING_WITH / :NEEDS_REVIEW
    # edges that no writer ever created. Both names are real, but as PROPERTY
    # values on RelationshipMetadata ("struggling_with" / "needs_review" in
    # core/models/enums/metadata_enums.py), not as edge types: an edge-vs-property
    # mix-up, so there is nothing to repoint onto. Re-deriving these signals is
    # semantic-layer roadmap work, not a rename.

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
            DELETE ip
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
        """Calculate coverage of learned knowledge over unlearned topics.

        "Learned" is the MASTERED edge's existence, not a score threshold.
        ADR-002's UserProgress node was to carry a single continuous
        `mastery_level` (read here as `>= 0.7`), but that model was never built;
        the live vocabulary splits the same continuum across two edge types —
        IN_PROGRESS carries `progress`, MASTERED is its terminal state. Mastery
        is therefore the edge, not a property comparison: `mastery_score` is
        per-writer (`UserBackend.record_knowledge_mastery` sets it, the derived
        PathStep edge pins it at 1.0), and a numeric filter would encode one
        writer's scale as the rule for all.

        The mastery match is OPTIONAL and the query anchors on the User. A
        mandatory match yields zero rows for a user who has mastered nothing,
        which kills the whole query and reports "no unlearned topics" for
        exactly the learner who has the most (Codex P2 on #737). A brand-new
        user is the meaningful case here: every topic unlearned, and the ones
        with no prerequisites already ready. `collect()` skips nulls, so
        `learned_uids` is simply `[]`.
        """
        return await self._executor.execute_query(
            """
            // Get learned knowledge UIDs (empty list when the user has none)
            MATCH (user:User {uid: $user_uid})
            OPTIONAL MATCH (user)-[:MASTERED]->(learned:Entity)
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
