"""
User Progress Recorder Service - Learning Progress Recording
=============================================================

Focused service handling user learning progress and knowledge relationship recording.

NOTE: This is the RECORDING service (writes progress). For READING user knowledge
profiles, use the root-level UserProgressService at /core/services/user_progress_service.py

Responsibilities:
- Knowledge mastery recording
- Knowledge progress tracking
- Learning path enrollment and completion
- Interest and bookmark management
- Progress metrics updates

This service is part of the refactored UserService architecture:
- UserCoreService: CRUD + Auth
- UserProgressRecorderService: Learning progress recording (THIS FILE)
- UserActivityService: Activity tracking
- UserContextBuilder: Context building
- UserStatsAggregator: Stats aggregation
- UserService: Facade coordinating all sub-services
"""

from core.ports.infrastructure_protocols import UserOperations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class UserProgressRecorderService:
    """
    Learning progress recording and knowledge relationship management.

    This service handles all operations related to RECORDING user progress through
    learning materials:
    - Recording mastery of knowledge units
    - Tracking in-progress learning
    - Managing learning path enrollments
    - Expressing interest and bookmarking content
    - Updating progress metrics

    Architecture:
    - Protocol-based repository dependency (UserOperations)
    - Uses graph relationships for tracking learning state
    - Integrates with progress metrics system
    """

    def __init__(self, user_repo: UserOperations) -> None:
        """
        Initialize user progress recorder service.

        Args:
            user_repo: Repository implementation for user persistence (protocol-based)

        Raises:
            ValueError: If user_repo is None
        """
        if not user_repo:
            raise ValueError("User repository is required")
        self.repo = user_repo

    # ========================================================================
    # KNOWLEDGE MASTERY & PROGRESS
    # ========================================================================

    @with_error_handling("record_knowledge_mastery", error_type="database", uid_param="user_uid")
    async def record_knowledge_mastery(
        self,
        user_uid: str,
        knowledge_uid: str,
        mastery_score: float,
        practice_count: int = 1,
        confidence_level: float = 0.8,
        update_progress: bool = True,
    ) -> Result[bool]:
        """
        Record knowledge mastery using graph relationships.

        Creates/Updates: (User)-[:MASTERED]->(Knowledge)

        Args:
            user_uid: User's unique identifier
            knowledge_uid: Knowledge unit UID
            mastery_score: Mastery score (0.8 to 1.0)
            practice_count: Number of practice sessions
            confidence_level: User's confidence level
            update_progress: Whether to update overall progress metrics

        Returns:
            Result[bool]: True if recorded successfully

        Error cases:
            - Invalid mastery score → VALIDATION
            - Database operation fails → DATABASE
        """
        if not 0.8 <= mastery_score <= 1.0:
            return Result.fail(Errors.validation("Mastery score must be between 0.8 and 1.0"))

        # Use graph-based method
        result = await self.repo.record_knowledge_mastery(
            user_uid, knowledge_uid, mastery_score, practice_count, confidence_level
        )

        if result.is_ok and update_progress:
            # Update overall progress metrics
            await self._update_progress_metrics(user_uid, knowledge_uid, mastery_score)

        if result.is_ok:
            logger.info(
                f"Recorded mastery for user {user_uid}, knowledge {knowledge_uid}: {mastery_score}"
            )

        return result

    @with_error_handling("record_knowledge_progress", error_type="database", uid_param="user_uid")
    async def record_knowledge_progress(
        self,
        user_uid: str,
        knowledge_uid: str,
        progress: float,
        time_invested_minutes: int = 0,
        difficulty_rating: float | None = None,
    ) -> Result[bool]:
        """
        Record progress on a knowledge unit.

        Creates/Updates: (User)-[:IN_PROGRESS]->(Knowledge)

        Args:
            user_uid: User's unique identifier
            knowledge_uid: Knowledge unit UID
            progress: Progress value (0.0 to 1.0)
            time_invested_minutes: Time spent in minutes
            difficulty_rating: User's difficulty rating (0.0 to 1.0)

        Returns:
            Result[bool]: True if recorded successfully

        Error cases:
            - Database operation fails → DATABASE
        """
        result = await self.repo.record_knowledge_progress(
            user_uid, knowledge_uid, progress, time_invested_minutes, difficulty_rating
        )

        if result.is_ok:
            logger.info(
                f"Recorded progress for user {user_uid}, knowledge {knowledge_uid}: {progress}"
            )

        return result

    # ========================================================================
    # LEARNING PATH MANAGEMENT
    # ========================================================================

    @with_error_handling("enroll_in_learning_path", error_type="database", uid_param="user_uid")
    async def enroll_in_learning_path(
        self,
        user_uid: str,
        learning_path_uid: str,
        target_completion: str | None = None,
        weekly_time_commitment: int = 300,
        motivation_note: str = "",
    ) -> Result[bool]:
        """
        Enroll user in a learning path using graph relationships.

        Creates: (User)-[:ENROLLED]->(LearningPath)

        Args:
            user_uid: User's unique identifier
            learning_path_uid: Learning path UID
            target_completion: Target completion date (ISO format)
            weekly_time_commitment: Minutes per week
            motivation_note: User's motivation

        Returns:
            Result[bool]: True if enrolled successfully

        Error cases:
            - Database operation fails → DATABASE
        """
        result = await self.repo.enroll_in_learning_path(
            user_uid,
            learning_path_uid,
            target_completion,
            weekly_time_commitment,
            motivation_note,
        )

        if result.is_ok:
            logger.info(f"Enrolled user {user_uid} in learning path {learning_path_uid}")

        return result

    @with_error_handling(
        "complete_learning_path_graph", error_type="database", uid_param="user_uid"
    )
    async def complete_learning_path_graph(
        self,
        user_uid: str,
        learning_path_uid: str,
        completion_score: float = 1.0,
        feedback_rating: int | None = None,
    ) -> Result[bool]:
        """
        Mark a learning path as completed using graph relationships.

        Creates: (User)-[:COMPLETED]->(LearningPath)
        Removes: (User)-[:ENROLLED]->(LearningPath)

        Args:
            user_uid: User's unique identifier
            learning_path_uid: Learning path UID
            completion_score: Score (0.0 to 1.0)
            feedback_rating: User's rating (1-5)

        Returns:
            Result[bool]: True if completed successfully

        Error cases:
            - Database operation fails → DATABASE
        """
        result = await self.repo.complete_learning_path_graph(
            user_uid, learning_path_uid, completion_score, feedback_rating
        )

        if result.is_ok:
            logger.info(f"Completed learning path {learning_path_uid} for user {user_uid}")
            # Update progress metrics
            await self._update_path_completion_progress(user_uid, learning_path_uid)

        return result

    # ========================================================================
    # INTEREST & BOOKMARKS
    # ========================================================================

    @with_error_handling(
        "express_interest_in_knowledge", error_type="database", uid_param="user_uid"
    )
    async def express_interest_in_knowledge(
        self,
        user_uid: str,
        knowledge_uid: str,
        interest_score: float = 0.8,
        interest_source: str = "discovery",
        priority: str = "medium",
        notes: str = "",
    ) -> Result[bool]:
        """
        Express interest in a knowledge unit.

        Creates: (User)-[:INTERESTED_IN]->(Knowledge)

        Args:
            user_uid: User's unique identifier
            knowledge_uid: Knowledge unit UID
            interest_score: Interest level (0.0 to 1.0)
            interest_source: Source (discovery, goal, recommendation, manual)
            priority: Priority level (high, medium, low)
            notes: Optional notes

        Returns:
            Result[bool]: True if recorded successfully

        Error cases:
            - Database operation fails → DATABASE
        """
        result = await self.repo.express_interest_in_knowledge(
            user_uid, knowledge_uid, interest_score, interest_source, priority, notes
        )

        if result.is_ok:
            logger.info(f"Recorded interest for user {user_uid} in knowledge {knowledge_uid}")

        return result

    @with_error_handling("bookmark_knowledge", error_type="database", uid_param="user_uid")
    async def bookmark_knowledge(
        self,
        user_uid: str,
        knowledge_uid: str,
        bookmark_reason: str = "reference",
        tags: list | None = None,
        reminder_date: str | None = None,
    ) -> Result[bool]:
        """
        Bookmark a knowledge unit for later.

        Creates: (User)-[:BOOKMARKED]->(Knowledge)

        Args:
            user_uid: User's unique identifier
            knowledge_uid: Knowledge unit UID
            bookmark_reason: Reason (reference, review_later, important)
            tags: Optional list of tags
            reminder_date: Optional reminder date (ISO format)

        Returns:
            Result[bool]: True if bookmarked successfully

        Error cases:
            - Database operation fails → DATABASE
        """
        result = await self.repo.bookmark_knowledge(
            user_uid, knowledge_uid, bookmark_reason, tags, reminder_date
        )

        if result.is_ok:
            logger.info(f"Bookmarked knowledge {knowledge_uid} for user {user_uid}")

        return result

    # ========================================================================
    # PROGRESS METRICS (PRIVATE HELPERS)
    # ========================================================================

    async def _update_progress_metrics(
        self, user_uid: str, _concept_uid: str, mastery_level: float
    ) -> None:
        """
        Update overall progress metrics when mastery changes.

        Args:
            user_uid: User's unique identifier
            _concept_uid: Concept UID (unused - for future use)
            mastery_level: Mastery level achieved

        Note:
            - Increments concepts_mastered if mastery >= 0.8
            - Logs error but doesn't fail operation if update fails
        """
        try:
            # If mastery is high enough, increment concepts mastered
            if mastery_level >= 0.8:
                progress_updates = {
                    "concepts_mastered": "+1"  # Increment by 1
                }
                await self.repo.update_user_progress(user_uid, progress_updates)

        except Exception as e:
            logger.error(f"Error updating progress metrics: {e}")

    async def _update_path_completion_progress(self, user_uid: str, _path_uid: str) -> None:
        """
        Update progress when a learning path is completed.

        Args:
            user_uid: User's unique identifier
            _path_uid: Path UID (unused - for future use)

        Note:
            - Increments total_learning_paths_completed
            - Logs error but doesn't fail operation if update fails
        """
        try:
            progress_updates = {"total_learning_paths_completed": "+1"}
            await self.repo.update_user_progress(user_uid, progress_updates)

        except Exception as e:
            logger.error(f"Error updating path completion progress: {e}")
