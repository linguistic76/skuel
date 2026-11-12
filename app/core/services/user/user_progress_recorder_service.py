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

This service is part of the refactored UserService architecture:
- UserCoreService: CRUD + Auth
- UserProgressRecorderService: Learning progress recording (THIS FILE)
- UserActivityService: Activity tracking
- UserContextBuilder: Context building
- UserStatsAggregator: Stats aggregation
- UserService: Facade coordinating all sub-services
"""

from core.events import publish_event
from core.events.learning_events import KnowledgeMastered, LearningPathStarted
from core.models.type_hints import UserUID
from core.ports.infrastructure_protocols import EventBusOperations, UserLearningStateOperations
from core.ports.query_types import MasteredWriteRow
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

    Architecture:
    - Protocol-based repository dependency (UserLearningStateOperations)
    - Uses graph relationships for tracking learning state
    """

    def __init__(
        self,
        user_repo: UserLearningStateOperations,
        event_bus: EventBusOperations | None = None,
    ) -> None:
        """
        Initialize user progress recorder service.

        Args:
            user_repo: Repository implementation for user persistence (protocol-based)
            event_bus: Publishes ``KnowledgeMastered`` when a mastery write lands

        Raises:
            ValueError: If user_repo is None
        """
        if not user_repo:
            raise ValueError("User repository is required")
        self.repo = user_repo
        self.event_bus = event_bus

    # ========================================================================
    # KNOWLEDGE MASTERY & PROGRESS
    # ========================================================================

    @with_error_handling("record_knowledge_mastery", error_type="database", uid_param="user_uid")
    async def record_knowledge_mastery(
        self,
        user_uid: UserUID,
        knowledge_uid: str,
        mastery_score: float,
        practice_count: int = 1,
        confidence_level: float = 0.8,
    ) -> Result[MasteredWriteRow]:
        """
        Record knowledge mastery using graph relationships.

        Creates/Updates: (User)-[:MASTERED]->(Knowledge), and publishes
        ``KnowledgeMastered`` for the write that created the edge — every
        Ku-mastery door announces its transition, so the progress chain runs
        however the Ku was mastered; a retry on a mastered Ku is not an event.

        Args:
            user_uid: User's unique identifier
            knowledge_uid: Knowledge unit UID
            mastery_score: Mastery score (0.8 to 1.0)
            practice_count: Number of practice sessions
            confidence_level: User's confidence level

        Returns:
            Result[MasteredWriteRow]: the stored score and ``was_mastered``

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

        if result.is_ok:
            logger.info(
                f"Recorded mastery for user {user_uid}, knowledge {knowledge_uid}: {mastery_score}"
            )
            if not result.value["was_mastered"]:
                await publish_event(
                    self.event_bus,
                    KnowledgeMastered(
                        ku_uid=knowledge_uid,
                        user_uid=user_uid,
                        mastery_score=result.value["mastery_score"],
                    ),
                    logger,
                )

        return result

    @with_error_handling("record_knowledge_progress", error_type="database", uid_param="user_uid")
    async def record_knowledge_progress(
        self,
        user_uid: UserUID,
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
        user_uid: UserUID,
        learning_path_uid: str,
        target_completion: str | None = None,
        weekly_time_commitment: int = 300,
        motivation_note: str = "",
    ) -> Result[bool]:
        """
        Enroll user in a learning path using graph relationships.

        Creates: (User)-[:ENROLLED_IN]->(LearningPath)

        Args:
            user_uid: User's unique identifier
            learning_path_uid: Learning path UID
            target_completion: Target completion date (ISO format)
            weekly_time_commitment: Minutes per week
            motivation_note: User's motivation

        Returns:
            Result[bool]: True when this call created the enrollment

        Error cases:
            - Database operation fails → DATABASE

        The enrollment that is created publishes ``LearningPathStarted``, so the
        progress chain initializes the enrollment's progress from the Kus the
        learner has already mastered; a repeat enroll refreshes the edge and
        announces nothing.
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
            if result.value:
                await publish_event(
                    self.event_bus,
                    LearningPathStarted(path_uid=learning_path_uid, user_uid=user_uid),
                    logger,
                )

        return result

    @with_error_handling("complete_learning_path", error_type="database", uid_param="user_uid")
    async def complete_learning_path(
        self,
        user_uid: UserUID,
        learning_path_uid: str,
        completion_score: float = 1.0,
        feedback_rating: int | None = None,
    ) -> Result[bool]:
        """
        Mark the learner's enrollment in a learning path completed.

        Updates: (User)-[:ENROLLED_IN]->(LearningPath) — its status becomes
        completed, with the completion score and rating. A learner's completed
        paths are read from these edges.

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
        result = await self.repo.complete_learning_path(
            user_uid, learning_path_uid, completion_score, feedback_rating
        )

        if result.is_ok:
            logger.info(f"Completed learning path {learning_path_uid} for user {user_uid}")

        return result

    # ========================================================================
    # INTEREST & BOOKMARKS
    # ========================================================================

    @with_error_handling(
        "express_interest_in_knowledge", error_type="database", uid_param="user_uid"
    )
    async def express_interest_in_knowledge(
        self,
        user_uid: UserUID,
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
        user_uid: UserUID,
        knowledge_uid: str,
        bookmark_reason: str = "reference",
        tags: list[str] | None = None,
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
