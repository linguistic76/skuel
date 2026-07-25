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

from core.models.type_hints import UserUID
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.user_progress_protocols import UserProgressBackendOperations

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

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-safe dictionary."""
        return {
            "knowledge_uid": self.knowledge_uid,
            "mastery_score": self.mastery_score,
            "achieved_at": self.achieved_at.isoformat() if self.achieved_at else None,
            "practice_count": self.practice_count,
            "last_practiced": self.last_practiced.isoformat() if self.last_practiced else None,
            "confidence_level": self.confidence_level,
            "retention_score": self.retention_score,
        }


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

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-safe dictionary."""
        return {
            "knowledge_uid": self.knowledge_uid,
            "progress": self.progress,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "estimated_completion": self.estimated_completion.isoformat()
            if self.estimated_completion
            else None,
            "time_invested_minutes": self.time_invested_minutes,
            "difficulty_rating": self.difficulty_rating,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
        }


@dataclass
class UserKnowledgeProfile:
    """
    Complete user knowledge profile built from graph relationships.

    This represents the user's actual learning state as stored in Neo4j,
    not assumptions or empty defaults.
    """

    user_uid: UserUID
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

    # NOTE: struggling_uids / needs_review_uids removed (SKUEL030 tranche 3).
    # They were fed by :STRUGGLING_WITH / :NEEDS_REVIEW edge reads that no
    # writer ever created, so both sets were always empty — see
    # UserProgressBackend for why there is nothing to repoint onto.

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-safe dictionary with datetime/set handling."""
        return {
            "user_uid": self.user_uid,
            "username": self.username,
            "mastered_knowledge": [m.to_dict() for m in self.mastered_knowledge],
            "mastered_uids": sorted(self.mastered_uids),
            "in_progress_knowledge": [p.to_dict() for p in self.in_progress_knowledge],
            "in_progress_uids": sorted(self.in_progress_uids),
            "completed_prerequisites": sorted(self.completed_prerequisites),
            "prerequisite_map": self.prerequisite_map,
            "active_learning_paths": self.active_learning_paths,
            "completed_paths": sorted(self.completed_paths),
            "interested_uids": sorted(self.interested_uids),
            "bookmarked_uids": sorted(self.bookmarked_uids),
        }


# ============================================================================
# USER PROGRESS SERVICE
# ============================================================================


class UserProgressService:
    """
    THE service for User-Knowledge graph operations.

    All user learning progress, mastery, and personalization data
    flows through this service.
    """

    def __init__(self, backend: "UserProgressBackendOperations") -> None:
        """
        Initialize with backend.

        Args:
            backend: UserProgressBackendOperations (required)

        Raises:
            ValueError: If backend is not provided
        """
        if not backend:
            raise ValueError("UserProgressBackendOperations is required - no fallback")

        self.backend = backend
        self.logger = logger

    @with_error_handling("get_mastered_uids", error_type="database")
    async def get_mastered_uids(self, user_uid: UserUID) -> Result[set[str]]:
        """Mastered-knowledge UIDs for a user, propagating read failures.

        Unlike :meth:`build_user_knowledge_profile` — which is deliberately
        resilient, swallowing each constituent query's error to always return a
        best-effort profile — this preserves the mastery read's ``Result``. Use
        it where a failed mastery read must fail the caller loudly rather than be
        silently rendered as "nothing mastered" (e.g. per-item mastery
        annotations that would otherwise mark everything unmastered).

        Backend: UserProgressBackend.get_mastered_knowledge
        """
        result = await self.backend.get_mastered_knowledge(user_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({row["knowledge_uid"] for row in result.value if row.get("knowledge_uid")})

    # ========================================================================
    # PROFILE BUILDING (Core Functionality)
    # ========================================================================

    @with_error_handling("build_user_knowledge_profile", error_type="database")
    async def build_user_knowledge_profile(self, user_uid: UserUID) -> Result[UserKnowledgeProfile]:
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
        user_result = await self.backend.get_user_username(user_uid)
        if user_result.is_error:
            return Result.fail(user_result)

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
        )

        self.logger.info(
            f"✅ Profile built: {len(mastered)} mastered, "
            f"{len(in_progress)} in-progress, {len(active_paths)} active paths"
        )

        return Result.ok(profile)

    # ========================================================================
    # MASTERY TRACKING
    # ========================================================================

    @with_error_handling("record_mastery", error_type="database")
    async def record_mastery(
        self,
        user_uid: UserUID,
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

        result = await self.backend.record_mastery(
            user_uid=user_uid,
            knowledge_uid=knowledge_uid,
            mastery_score=mastery_score,
            practice_count=practice_count,
            confidence_level=confidence_level,
        )
        if result.is_error:
            self.logger.warning(f"Failed to record mastery: {result.error}")

        self.logger.info(f"✅ Recorded mastery: {user_uid} -> {knowledge_uid} ({mastery_score})")

        return Result.ok(True)

    @with_error_handling("record_progress", error_type="database")
    async def record_progress(
        self,
        user_uid: UserUID,
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

        result = await self.backend.record_progress(
            user_uid=user_uid,
            knowledge_uid=knowledge_uid,
            progress=progress,
            time_invested_minutes=time_invested_minutes,
            difficulty_rating=difficulty_rating or 0.5,
        )
        if result.is_error:
            self.logger.warning(f"Failed to record progress: {result.error}")

        self.logger.info(f"✅ Recorded progress: {user_uid} -> {knowledge_uid} ({progress})")

        return Result.ok(True)

    # ========================================================================
    # PRIVATE HELPER METHODS (Graph Queries)
    # ========================================================================

    async def _get_mastered_knowledge(self, user_uid: UserUID) -> list[UserKnowledgeMastery]:
        """Get all mastered knowledge for user."""
        result = await self.backend.get_mastered_knowledge(user_uid)
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

    async def _get_in_progress_knowledge(self, user_uid: UserUID) -> list[UserLearningProgress]:
        """Get all in-progress knowledge for user."""
        result = await self.backend.get_in_progress_knowledge(user_uid)
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
        self, user_uid: UserUID, _mastered_uids: set[str]
    ) -> set[str]:
        """Get all prerequisites that user has completed."""
        result = await self.backend.get_completed_prerequisites(user_uid)
        if result.is_error:
            return set()

        return {record["prereq_uid"] for record in (result.value or [])}

    async def _build_prerequisite_map(self, user_uid: UserUID) -> dict[str, list[str]]:
        """Build map of knowledge units to their prerequisites."""
        result = await self.backend.get_prerequisite_map()
        if result.is_error:
            return {}

        return {record["knowledge_uid"]: record["prereq_uids"] for record in (result.value or [])}

    async def _get_learning_paths(self, user_uid: UserUID) -> tuple[list[str], set[str]]:
        """Get active and completed learning paths."""
        active_result = await self.backend.get_active_learning_paths(user_uid)

        active_records = active_result.value or [] if active_result.is_ok else []
        active_record = active_records[0] if active_records else None
        active_paths = active_record["active_paths"] if active_record else []

        completed_result = await self.backend.get_completed_learning_paths(user_uid)

        completed_records = completed_result.value or [] if completed_result.is_ok else []
        completed_record = completed_records[0] if completed_records else None
        completed_paths = set(completed_record["completed_paths"]) if completed_record else set()

        return active_paths, completed_paths

    async def _get_interested_knowledge(self, user_uid: UserUID) -> set[str]:
        """Get knowledge units user is interested in."""
        result = await self.backend.get_interested_knowledge(user_uid)
        if result.is_error:
            return set()

        records = result.value or []
        record = records[0] if records else None
        return set(record["interested_uids"]) if record else set()

    async def _get_bookmarked_knowledge(self, user_uid: UserUID) -> set[str]:
        """Get bookmarked knowledge units."""
        result = await self.backend.get_bookmarked_knowledge(user_uid)
        if result.is_error:
            return set()

        records = result.value or []
        record = records[0] if records else None
        return set(record["bookmarked_uids"]) if record else set()

    # ========================================================================
    # PHASE 4.5: Knowledge Coverage Analytics (October 6, 2025)
    # ========================================================================

    @with_error_handling("calculate_knowledge_coverage", error_type="database")
    async def calculate_knowledge_coverage(
        self, user_uid: UserUID, domain: str | None = None
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
        result = await self.backend.calculate_knowledge_coverage(user_uid, domain)
        if result.is_error:
            return Result.fail(result)

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
