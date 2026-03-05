"""
User Progress Service
=====================

Manages user learning progress through Neo4j graph relationships.
This service is THE interface for all User-Knowledge graph operations.

Handles:
- User mastery tracking (MASTERED relationships)
- Learning progress (IN_PROGRESS relationships)
- Prerequisites and readiness calculations
- Learning path enrollment and completion
- Personalized knowledge profile building

Following SKUEL principles:
- No backwards compatibility - graph-first approach
- Fail-fast - requires Neo4j with APOC
- Result[T] error handling
- Protocol-based dependencies
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import QueryExecutor

logger = get_logger(__name__)


# ============================================================================
# DATA STRUCTURES
# ============================================================================


@dataclass
class UserKnowledgeMastery:
    """Represents user's mastery of a knowledge unit."""

    knowledge_uid: str
    mastery_score: float
    achieved_at: datetime
    practice_count: int
    last_practiced: datetime
    confidence_level: float
    retention_score: float


@dataclass
class UserLearningProgress:
    """Represents user's progress in learning a knowledge unit."""

    knowledge_uid: str
    progress: float
    started_at: datetime
    estimated_completion: date
    time_invested_minutes: int
    difficulty_rating: float
    last_accessed: datetime


@dataclass
class UserKnowledgeProfile:
    """
    Complete user knowledge profile built from graph relationships.

    This represents the user's actual learning state as stored in Neo4j,
    not assumptions or empty defaults.
    """

    user_uid: str
    username: str

    # Mastery data
    mastered_knowledge: list[UserKnowledgeMastery]
    mastered_uids: set[str]

    # In-progress data
    in_progress_knowledge: list[UserLearningProgress]
    in_progress_uids: set[str]

    # Prerequisites
    completed_prerequisites: set[str]
    prerequisite_map: dict[str, list[str]]  # target_uid -> [prereq_uids]

    # Learning paths
    active_learning_paths: list[str]
    completed_paths: set[str]

    # Interests and bookmarks
    interested_uids: set[str]
    bookmarked_uids: set[str]

    # Struggle identification
    struggling_uids: set[str]
    needs_review_uids: set[str]


# ============================================================================
# USER PROGRESS SERVICE
# ============================================================================


class UserProgressService:
    """
    THE service for User-Knowledge graph operations.

    All user learning progress, mastery, and personalization data
    flows through this service.
    """

    def __init__(self, executor: "QueryExecutor") -> None:
        """
        Initialize with QueryExecutor.

        Args:
            executor: QueryExecutor (required)

        Raises:
            ValueError: If executor is not provided
        """
        if not executor:
            raise ValueError("QueryExecutor is required - no fallback")

        self.executor = executor
        self.logger = logger

    # ========================================================================
    # PROFILE BUILDING (Core Functionality)
    # ========================================================================

    @with_error_handling("build_user_knowledge_profile", error_type="database")
    async def build_user_knowledge_profile(self, user_uid: str) -> Result[UserKnowledgeProfile]:
        """
        Build complete user knowledge profile from Neo4j graph.

        This is THE method for getting user learning state.
        Traverses all User-Knowledge relationships to build comprehensive profile.

        Args:
            user_uid: User UID

        Returns:
            Result[UserKnowledgeProfile] with complete learning state
        """
        self.logger.info(f"🔍 Building knowledge profile for user {user_uid}")

        # Get user basic info
        user_result = await self.executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})
            RETURN u.username as username
            """,
            {"user_uid": user_uid},
        )
        if user_result.is_error:
            return Result.fail(user_result.expect_error())

        user_records = user_result.value or []
        user_record = user_records[0] if user_records else None
        if not user_record:
            return Result.fail(Errors.not_found("User", user_uid))

        username = user_record["username"] or "User"

        # Get mastered knowledge
        mastered = await self._get_mastered_knowledge(user_uid)
        mastered_uids = {m.knowledge_uid for m in mastered}

        # Get in-progress knowledge
        in_progress = await self._get_in_progress_knowledge(user_uid)
        in_progress_uids = {p.knowledge_uid for p in in_progress}

        # Get completed prerequisites
        completed_prereqs = await self._get_completed_prerequisites(user_uid, mastered_uids)

        # Get prerequisite map (what knowledge needs what prereqs)
        prereq_map = await self._build_prerequisite_map(user_uid)

        # Get learning path enrollments
        active_paths, completed_paths = await self._get_learning_paths(user_uid)

        # Get interests and bookmarks
        interested = await self._get_interested_knowledge(user_uid)
        bookmarked = await self._get_bookmarked_knowledge(user_uid)

        # Get struggle and review needs
        struggling = await self._get_struggling_knowledge(user_uid)
        needs_review = await self._get_needs_review_knowledge(user_uid)

        profile = UserKnowledgeProfile(
            user_uid=user_uid,
            username=username,
            mastered_knowledge=mastered,
            mastered_uids=mastered_uids,
            in_progress_knowledge=in_progress,
            in_progress_uids=in_progress_uids,
            completed_prerequisites=completed_prereqs,
            prerequisite_map=prereq_map,
            active_learning_paths=active_paths,
            completed_paths=completed_paths,
            interested_uids=interested,
            bookmarked_uids=bookmarked,
            struggling_uids=struggling,
            needs_review_uids=needs_review,
        )

        self.logger.info(
            f"✅ Profile built: {len(mastered)} mastered, "
            f"{len(in_progress)} in-progress, {len(active_paths)} active paths"
        )

        return Result.ok(profile)

    @with_error_handling("calculate_readiness_for_knowledge", error_type="database")
    async def calculate_readiness_for_knowledge(
        self, user_uid: str, knowledge_uid: str, profile: UserKnowledgeProfile | None = None
    ) -> Result[float]:
        """
        Calculate user's readiness for specific knowledge unit.

        Readiness is based on:
        - Already mastered (low readiness - they've moved past it)
        - Currently learning (high readiness - they're engaged)
        - Prerequisites completed (proportional readiness)

        Args:
            user_uid: User UID,
            knowledge_uid: Target knowledge UID,
            profile: Optional pre-built profile (for efficiency)

        Returns:
            Result[float] with readiness score 0.0-1.0
        """
        # Use provided profile or build new one
        if not profile:
            profile_result = await self.build_user_knowledge_profile(user_uid)
            if profile_result.is_error:
                # Error building profile: Result[UserKnowledgeProfile] → Result[float]
                return Result.fail(profile_result.expect_error())
            profile = profile_result.value

        # Already mastered? Low readiness (they've moved past it)
        if knowledge_uid in profile.mastered_uids:
            return Result.ok(0.2)

        # Currently learning? High readiness
        if knowledge_uid in profile.in_progress_uids:
            # Check progress level
            for progress in profile.in_progress_knowledge:
                if progress.knowledge_uid == knowledge_uid:
                    # Scale readiness based on progress (0.7-0.95)
                    return Result.ok(0.7 + (progress.progress * 0.25))
            return Result.ok(0.9)

        # Check prerequisites
        prereq_result = await self.executor.execute_query(
            """
            MATCH (target:Entity {uid: $target_uid})
            OPTIONAL MATCH (target)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
            WITH target, collect(prereq.uid) as prereq_uids
            RETURN
                size(prereq_uids) as total_prereqs,
                prereq_uids
            """,
            {"target_uid": knowledge_uid},
        )
        if prereq_result.is_error:
            return Result.fail(prereq_result.expect_error())

        prereq_records = prereq_result.value or []
        record = prereq_records[0] if prereq_records else None
        if not record:
            return Result.ok(0.5)  # Knowledge not found, moderate readiness

        total_prereqs = record["total_prereqs"]
        prereq_uids = record["prereq_uids"]

        if total_prereqs == 0:
            # No prerequisites, high readiness
            return Result.ok(0.75)

        # Calculate how many prereqs are met
        met_prereqs = sum(1 for p_uid in prereq_uids if p_uid in profile.completed_prerequisites)

        readiness = met_prereqs / total_prereqs

        # Boost if user is interested
        if knowledge_uid in profile.interested_uids:
            readiness = min(1.0, readiness + 0.1)

        # Reduce if user is struggling with related content
        if knowledge_uid in profile.struggling_uids:
            readiness = max(0.0, readiness - 0.2)

        return Result.ok(readiness)

    # ========================================================================
    # MASTERY TRACKING
    # ========================================================================

    @with_error_handling("record_mastery", error_type="database")
    async def record_mastery(
        self,
        user_uid: str,
        knowledge_uid: str,
        mastery_score: float,
        practice_count: int = 1,
        confidence_level: float = 0.8,
    ) -> Result[bool]:
        """
        Record that user has mastered a knowledge unit.

        Creates or updates MASTERED relationship.

        Args:
            user_uid: User UID,
            knowledge_uid: Knowledge UID,
            mastery_score: Mastery score (0.8-1.0),
            practice_count: Number of practice sessions,
            confidence_level: User's confidence level

        Returns:
            Result[bool] indicating success
        """
        if mastery_score < 0.8:
            return Result.fail(
                Errors.validation("Mastery score must be >= 0.8", field="mastery_score")
            )

        result = await self.executor.execute_query(
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
        if result.is_error:
            self.logger.warning(f"Failed to record mastery: {result.error}")

        self.logger.info(f"✅ Recorded mastery: {user_uid} -> {knowledge_uid} ({mastery_score})")

        return Result.ok(True)

    @with_error_handling("record_progress", error_type="database")
    async def record_progress(
        self,
        user_uid: str,
        knowledge_uid: str,
        progress: float,
        time_invested_minutes: int = 0,
        difficulty_rating: float | None = None,
    ) -> Result[bool]:
        """
        Record user's learning progress for a knowledge unit.

        Creates or updates IN_PROGRESS relationship.

        Args:
            user_uid: User UID,
            knowledge_uid: Knowledge UID,
            progress: Progress percentage (0.0-1.0),
            time_invested_minutes: Minutes invested,
            difficulty_rating: Optional difficulty rating (0.0-1.0)

        Returns:
            Result[bool] indicating success
        """
        if not 0.0 <= progress <= 1.0:
            return Result.fail(
                Errors.validation("Progress must be between 0.0 and 1.0", field="progress")
            )

        result = await self.executor.execute_query(
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
                "difficulty_rating": difficulty_rating or 0.5,
            },
        )
        if result.is_error:
            self.logger.warning(f"Failed to record progress: {result.error}")

        self.logger.info(f"✅ Recorded progress: {user_uid} -> {knowledge_uid} ({progress})")

        return Result.ok(True)

    # ========================================================================
    # PRIVATE HELPER METHODS (Graph Queries)
    # ========================================================================

    async def _get_mastered_knowledge(self, user_uid: str) -> list[UserKnowledgeMastery]:
        """Get all mastered knowledge for user."""
        result = await self.executor.execute_query(
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
        if result.is_error:
            return []

        return [
            UserKnowledgeMastery(
                knowledge_uid=record["knowledge_uid"],
                mastery_score=record["mastery_score"],
                achieved_at=record["achieved_at"],
                practice_count=record["practice_count"],
                last_practiced=record["last_practiced"],
                confidence_level=record["confidence_level"],
                retention_score=record["retention_score"],
            )
            for record in (result.value or [])
        ]

    async def _get_in_progress_knowledge(self, user_uid: str) -> list[UserLearningProgress]:
        """Get all in-progress knowledge for user."""
        result = await self.executor.execute_query(
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
        if result.is_error:
            return []

        return [
            UserLearningProgress(
                knowledge_uid=record["knowledge_uid"],
                progress=record["progress"],
                started_at=record["started_at"],
                estimated_completion=record["estimated_completion"],
                time_invested_minutes=record["time_invested_minutes"],
                difficulty_rating=record["difficulty_rating"],
                last_accessed=record["last_accessed"],
            )
            for record in (result.value or [])
        ]

    async def _get_completed_prerequisites(
        self, user_uid: str, _mastered_uids: set[str]
    ) -> set[str]:
        """
        Get all prerequisites that user has completed.

        This is THE key query for readiness calculation.
        """
        result = await self.executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:MASTERED]->(mastered:Entity)
            MATCH (target:Entity)-[:REQUIRES_KNOWLEDGE]->(mastered)
            RETURN DISTINCT mastered.uid as prereq_uid
            """,
            {"user_uid": user_uid},
        )
        if result.is_error:
            return set()

        return {record["prereq_uid"] for record in (result.value or [])}

    async def _build_prerequisite_map(self, user_uid: str) -> dict[str, list[str]]:
        """Build map of knowledge units to their prerequisites."""
        result = await self.executor.execute_query(
            """
            MATCH (k:Entity)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
            RETURN k.uid as knowledge_uid, collect(prereq.uid) as prereq_uids
            """,
            {"user_uid": user_uid},
        )
        if result.is_error:
            return {}

        return {record["knowledge_uid"]: record["prereq_uids"] for record in (result.value or [])}

    async def _get_learning_paths(self, user_uid: str) -> tuple[list[str], set[str]]:
        """Get active and completed learning paths."""
        active_result = await self.executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[e:ENROLLED]->(p:Lp)
            WHERE e.enrollment_status = 'active'
            RETURN collect(p.uid) as active_paths
            """,
            {"user_uid": user_uid},
        )

        active_records = active_result.value or [] if active_result.is_ok else []
        active_record = active_records[0] if active_records else None
        active_paths = active_record["active_paths"] if active_record else []

        completed_result = await self.executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[c:COMPLETED]->(p:Lp)
            RETURN collect(p.uid) as completed_paths
            """,
            {"user_uid": user_uid},
        )

        completed_records = completed_result.value or [] if completed_result.is_ok else []
        completed_record = completed_records[0] if completed_records else None
        completed_paths = set(completed_record["completed_paths"]) if completed_record else set()

        return active_paths, completed_paths

    async def _get_interested_knowledge(self, user_uid: str) -> set[str]:
        """Get knowledge units user is interested in."""
        result = await self.executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:INTERESTED_IN]->(k:Entity)
            RETURN collect(k.uid) as interested_uids
            """,
            {"user_uid": user_uid},
        )
        if result.is_error:
            return set()

        records = result.value or []
        record = records[0] if records else None
        return set(record["interested_uids"]) if record else set()

    async def _get_bookmarked_knowledge(self, user_uid: str) -> set[str]:
        """Get bookmarked knowledge units."""
        result = await self.executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:BOOKMARKED]->(k:Entity)
            RETURN collect(k.uid) as bookmarked_uids
            """,
            {"user_uid": user_uid},
        )
        if result.is_error:
            return set()

        records = result.value or []
        record = records[0] if records else None
        return set(record["bookmarked_uids"]) if record else set()

    async def _get_struggling_knowledge(self, user_uid: str) -> set[str]:
        """Get knowledge units user is struggling with."""
        result = await self.executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:STRUGGLING_WITH]->(k:Entity)
            RETURN collect(k.uid) as struggling_uids
            """,
            {"user_uid": user_uid},
        )
        if result.is_error:
            return set()

        records = result.value or []
        record = records[0] if records else None
        return set(record["struggling_uids"]) if record else set()

    async def _get_needs_review_knowledge(self, user_uid: str) -> set[str]:
        """Get knowledge units that need review."""
        result = await self.executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[r:NEEDS_REVIEW]->(k:Entity)
            WHERE r.next_review_due <= date()
            RETURN collect(k.uid) as review_uids
            """,
            {"user_uid": user_uid},
        )
        if result.is_error:
            return set()

        records = result.value or []
        record = records[0] if records else None
        return set(record["review_uids"]) if record else set()

    # ========================================================================
    # PHASE 4.5: Knowledge Coverage Analytics (October 6, 2025)
    # ========================================================================

    @with_error_handling("calculate_knowledge_coverage", error_type="database")
    async def calculate_knowledge_coverage(
        self, user_uid: str, domain: str | None = None
    ) -> Result[dict[str, Any]]:
        """
        Calculate how well learned knowledge covers unlearned topics.

        Uses edge metadata:
        - User progress (what's learned)
        - Prerequisite edges (what enables what)
        - Edge confidence (how reliable the relationship)

        Args:
            user_uid: User UID,
            domain: Optional domain filter

        Returns:
            Result containing coverage statistics and topic details
        """
        query = """
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
        """

        result = await self.executor.execute_query(query, {"user_uid": user_uid, "domain": domain})
        if result.is_error:
            return Result.fail(result.expect_error())

        topics = [record["topic"] for record in (result.value or [])]

        # Aggregate statistics
        if topics:
            ready_count = sum(1 for t in topics if t["ready_to_learn"])
            avg_coverage = sum(t["coverage_ratio"] for t in topics) / len(topics)
        else:
            ready_count = 0
            avg_coverage = 0.0

        coverage_data = {
            "total_unlearned": len(topics),
            "ready_to_learn": ready_count,
            "average_coverage": avg_coverage,
            "topics": topics[:50],  # Limit to top 50 for performance
        }

        self.logger.info(
            f"📊 Coverage for {user_uid}: "
            f"{ready_count}/{len(topics)} topics ready "
            f"(avg coverage: {avg_coverage:.1%})"
        )

        return Result.ok(coverage_data)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "UserKnowledgeMastery",
    "UserKnowledgeProfile",
    "UserLearningProgress",
    "UserProgressService",
]
