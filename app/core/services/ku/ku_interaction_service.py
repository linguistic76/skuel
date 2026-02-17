"""
Knowledge Interaction Service - Pedagogical Tracking
=====================================================

Tracks user interactions with knowledge units for self-directed learning.

State Progression:
    NONE -> VIEWED -> IN_PROGRESS -> MASTERED

Responsibilities:
- Record when user views KU content
- Track in-progress learning state
- Query user's learning state for a KU
- Support pedagogical search filters

Architecture:
- Uses direct Cypher queries via Neo4j driver
- Returns Result[T] for error handling
- Stores relationship properties for time tracking
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.protocols import BackendOperations


class LearningState(str, Enum):
    """User's learning state for a knowledge unit."""

    NONE = "none"  # User has never interacted with this KU
    VIEWED = "viewed"  # User has seen/read this KU
    IN_PROGRESS = "in_progress"  # User is actively learning
    MASTERED = "mastered"  # User has mastered this KU


@dataclass(frozen=True)
class UserKuProgress:
    """User's progress on a specific knowledge unit."""

    ku_uid: str
    state: LearningState
    first_viewed_at: datetime | None = None
    last_viewed_at: datetime | None = None
    view_count: int = 0
    started_at: datetime | None = None  # When IN_PROGRESS started
    mastered_at: datetime | None = None
    time_spent_seconds: int = 0  # Accumulated time spent
    is_marked_as_read: bool = False  # MARKED_AS_READ relationship exists
    is_bookmarked: bool = False  # BOOKMARKED relationship exists


class KuInteractionService:
    """
    Tracks user interactions with knowledge units.

    This service enables pedagogical search by tracking what users have
    seen, are learning, and have mastered. It's the foundation for
    "show me what I haven't seen yet" and "show me what I'm working on"
    search filters.

    State Transitions:
        - record_view(): NONE -> VIEWED (or updates existing VIEWED)
        - mark_in_progress(): VIEWED -> IN_PROGRESS
        - mark_mastered(): IN_PROGRESS -> MASTERED (handled elsewhere)

    Relationship Properties:
        VIEWED: first_viewed_at, last_viewed_at, view_count, time_spent_seconds
        IN_PROGRESS: started_at, last_activity_at, progress_score
        MASTERED: mastered_at, confidence, method
    """

    def __init__(
        self,
        backend: "BackendOperations[Any] | None" = None,
        event_bus=None,
    ) -> None:
        """
        Initialize KU interaction service.

        Args:
            backend: BackendOperations for Cypher queries (REQUIRED)
            event_bus: Optional event bus for publishing events
        """
        self.backend = backend
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.ku.interaction")

    async def record_view(
        self,
        user_uid: str,
        ku_uid: str,
        time_spent_seconds: int = 0,
    ) -> Result[bool]:
        """
        Record that a user viewed a knowledge unit.

        Creates or updates VIEWED relationship with timestamps and counts.
        This is called when a user views a nous topic or KU detail page.

        Args:
            user_uid: User's UID
            ku_uid: Knowledge unit's UID
            time_spent_seconds: Time spent on this view (optional)

        Returns:
            Result[bool]: True if recorded successfully
        """
        if not self.backend:
            return Result.fail(Errors.database("record_view", "Backend not available"))

        now = datetime.now(UTC).isoformat()

        query = """
        MATCH (u:User {uid: $user_uid})
        MATCH (ku:Ku {uid: $ku_uid})
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

        result = await self.backend.execute_query(
            query,
            {
                "user_uid": user_uid,
                "ku_uid": ku_uid,
                "now": now,
                "time_spent": time_spent_seconds,
            },
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        if result.value:
            record = result.value[0]
            self.logger.debug(
                "Recorded view",
                user_uid=user_uid,
                ku_uid=ku_uid,
                view_count=record["view_count"],
            )
            return Result.ok(True)
        else:
            return Result.fail(Errors.not_found("User or KU", f"{user_uid} / {ku_uid}"))

    async def mark_in_progress(
        self,
        user_uid: str,
        ku_uid: str,
    ) -> Result[bool]:
        """
        Mark a knowledge unit as in-progress for a user.

        Creates IN_PROGRESS relationship. User should have VIEWED first,
        but this will work regardless.

        Args:
            user_uid: User's UID
            ku_uid: Knowledge unit's UID

        Returns:
            Result[bool]: True if marked successfully
        """
        if not self.backend:
            return Result.fail(Errors.database("mark_in_progress", "Backend not available"))

        now = datetime.now(UTC).isoformat()

        query = """
        MATCH (u:User {uid: $user_uid})
        MATCH (ku:Ku {uid: $ku_uid})
        MERGE (u)-[r:IN_PROGRESS]->(ku)
        ON CREATE SET
            r.started_at = datetime($now),
            r.last_activity_at = datetime($now),
            r.progress_score = 0.0
        ON MATCH SET
            r.last_activity_at = datetime($now)
        RETURN true as success
        """

        result = await self.backend.execute_query(
            query,
            {"user_uid": user_uid, "ku_uid": ku_uid, "now": now},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        if result.value:
            self.logger.debug(
                "Marked in progress",
                user_uid=user_uid,
                ku_uid=ku_uid,
            )
            return Result.ok(True)
        else:
            return Result.fail(Errors.not_found("User or KU", f"{user_uid} / {ku_uid}"))

    async def get_learning_state(
        self,
        user_uid: str,
        ku_uid: str,
    ) -> Result[UserKuProgress]:
        """
        Get user's learning state for a knowledge unit.

        Checks for MASTERED, IN_PROGRESS, and VIEWED relationships in that order
        to determine the highest state achieved.

        Args:
            user_uid: User's UID
            ku_uid: Knowledge unit's UID

        Returns:
            Result[UserKuProgress]: User's progress on this KU
        """
        if not self.backend:
            return Result.fail(Errors.database("get_learning_state", "Backend not available"))

        query = """
        MATCH (ku:Ku {uid: $ku_uid})
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

        result = await self.backend.execute_query(
            query,
            {"user_uid": user_uid, "ku_uid": ku_uid},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.fail(Errors.not_found("KU", ku_uid))

        record = result.value[0]

        # Determine state from highest relationship
        if record["has_mastered"]:
            state = LearningState.MASTERED
        elif record["has_in_progress"]:
            state = LearningState.IN_PROGRESS
        elif record["has_viewed"]:
            state = LearningState.VIEWED
        else:
            state = LearningState.NONE

        # Parse datetime fields
        first_viewed = None
        if record["first_viewed_at"]:
            first_viewed = record["first_viewed_at"].to_native()

        last_viewed = None
        if record["last_viewed_at"]:
            last_viewed = record["last_viewed_at"].to_native()

        started = None
        if record["started_at"]:
            started = record["started_at"].to_native()

        mastered = None
        if record["mastered_at"]:
            mastered = record["mastered_at"].to_native()

        progress = UserKuProgress(
            ku_uid=ku_uid,
            state=state,
            first_viewed_at=first_viewed,
            last_viewed_at=last_viewed,
            view_count=record["view_count"] or 0,
            started_at=started,
            mastered_at=mastered,
            time_spent_seconds=record["time_spent_seconds"] or 0,
            is_marked_as_read=record["has_marked_as_read"],
            is_bookmarked=record["has_bookmarked"],
        )

        return Result.ok(progress)

    async def get_learning_states_batch(
        self,
        user_uid: str,
        ku_uids: list[str],
    ) -> Result[dict[str, LearningState]]:
        """
        Get learning states for multiple KUs in one query.

        Optimized for search results - returns just the state, not full progress.

        Args:
            user_uid: User's UID
            ku_uids: List of KU UIDs to check

        Returns:
            Result[dict[str, LearningState]]: Map of ku_uid -> LearningState
        """
        if not self.backend:
            return Result.fail(
                Errors.database("get_learning_states_batch", "Backend not available")
            )

        if not ku_uids:
            return Result.ok({})

        query = """
        UNWIND $ku_uids as ku_uid
        MATCH (ku:Ku {uid: ku_uid})
        OPTIONAL MATCH (u:User {uid: $user_uid})-[v:VIEWED]->(ku)
        OPTIONAL MATCH (u:User {uid: $user_uid})-[p:IN_PROGRESS]->(ku)
        OPTIONAL MATCH (u:User {uid: $user_uid})-[m:MASTERED]->(ku)
        RETURN
            ku.uid as ku_uid,
            v IS NOT NULL as has_viewed,
            p IS NOT NULL as has_in_progress,
            m IS NOT NULL as has_mastered
        """

        result = await self.backend.execute_query(
            query,
            {"user_uid": user_uid, "ku_uids": ku_uids},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        states = {}
        for record in result.value or []:
            if record["has_mastered"]:
                state = LearningState.MASTERED
            elif record["has_in_progress"]:
                state = LearningState.IN_PROGRESS
            elif record["has_viewed"]:
                state = LearningState.VIEWED
            else:
                state = LearningState.NONE
            states[record["ku_uid"]] = state

        return Result.ok(states)

    # =========================================================================
    # MVP PHASE A: Reading Interface Methods
    # =========================================================================

    async def mark_as_read(
        self,
        user_uid: str,
        ku_uid: str,
    ) -> Result[None]:
        """
        Mark a KU as read by the user.

        Creates a MARKED_AS_READ relationship to track KUs the user has finished reading.
        This is a lighter-weight alternative to MASTERED for simple reading completion.

        Args:
            user_uid: User's unique identifier
            ku_uid: Knowledge unit identifier

        Returns:
            Result[None]: Success or database error
        """
        if not self.backend:
            return Result.fail(Errors.system("Backend required", service="KuInteractionService"))

        query = """
        MATCH (user:User {uid: $user_uid})
        MATCH (ku:Ku {uid: $ku_uid})
        MERGE (user)-[r:MARKED_AS_READ]->(ku)
        ON CREATE SET r.marked_at = datetime()
        RETURN r
        """

        result = await self.backend.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})

        if result.is_error:
            return Result.fail(result.expect_error())

        self.logger.info(f"Marked KU as read: {user_uid} -> {ku_uid}")
        return Result.ok(None)

    async def toggle_bookmark(
        self,
        user_uid: str,
        ku_uid: str,
    ) -> Result[bool]:
        """
        Toggle bookmark state for a KU.

        Creates BOOKMARKED relationship if not exists, removes if exists.

        Args:
            user_uid: User's unique identifier
            ku_uid: Knowledge unit identifier

        Returns:
            Result[bool]: True if bookmarked, False if unbookmarked
        """
        if not self.backend:
            return Result.fail(Errors.system("Backend required", service="KuInteractionService"))

        # Check if bookmark exists
        check_query = """
        MATCH (user:User {uid: $user_uid})-[r:BOOKMARKED]->(ku:Ku {uid: $ku_uid})
        RETURN r IS NOT NULL as is_bookmarked
        """

        check_result = await self.backend.execute_query(
            check_query, {"user_uid": user_uid, "ku_uid": ku_uid}
        )

        if check_result.is_error:
            return Result.fail(check_result.expect_error())

        is_bookmarked = check_result.value[0]["is_bookmarked"] if check_result.value else False

        if is_bookmarked:
            # Remove bookmark
            delete_query = """
            MATCH (user:User {uid: $user_uid})-[r:BOOKMARKED]->(ku:Ku {uid: $ku_uid})
            DELETE r
            """
            del_result = await self.backend.execute_query(
                delete_query, {"user_uid": user_uid, "ku_uid": ku_uid}
            )
            if del_result.is_error:
                return Result.fail(del_result.expect_error())
            self.logger.info(f"Removed bookmark: {user_uid} -> {ku_uid}")
            return Result.ok(False)
        else:
            # Add bookmark
            create_query = """
            MATCH (user:User {uid: $user_uid})
            MATCH (ku:Ku {uid: $ku_uid})
            MERGE (user)-[r:BOOKMARKED]->(ku)
            ON CREATE SET r.bookmarked_at = datetime()
            """
            create_result = await self.backend.execute_query(
                create_query, {"user_uid": user_uid, "ku_uid": ku_uid}
            )
            if create_result.is_error:
                return Result.fail(create_result.expect_error())
            self.logger.info(f"Added bookmark: {user_uid} -> {ku_uid}")
            return Result.ok(True)

    async def mark_mastered(
        self,
        user_uid: str,
        ku_uid: str,
        mastery_score: float = 0.8,
        method: str = "report_approval",
    ) -> Result[bool]:
        """
        Mark a KU as mastered by the user.

        Creates or updates a MASTERED relationship. Called when a teacher
        approves a report that APPLIES_KNOWLEDGE to this KU.

        Args:
            user_uid: User's unique identifier
            ku_uid: Knowledge unit identifier
            mastery_score: Mastery confidence score (0.0-1.0, default 0.8)
            method: How mastery was achieved (e.g., "report_approval")

        Returns:
            Result[bool]: True if mastered successfully
        """
        if not self.backend:
            return Result.fail(Errors.system("Backend required", service="KuInteractionService"))

        now = datetime.now(UTC).isoformat()

        query = """
        MATCH (user:User {uid: $user_uid})
        MATCH (ku:Ku {uid: $ku_uid})
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

        result = await self.backend.execute_query(
            query,
            {
                "user_uid": user_uid,
                "ku_uid": ku_uid,
                "now": now,
                "mastery_score": mastery_score,
                "method": method,
            },
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        if result.value:
            record = result.value[0]
            self.logger.info(
                f"Marked KU as mastered: {user_uid} -> {ku_uid} "
                f"(score={record['mastery_score']}, method={method})"
            )
            return Result.ok(True)
        else:
            return Result.fail(Errors.not_found("User or KU", f"{user_uid} / {ku_uid}"))

    async def get_bookmarked_kus(
        self,
        user_uid: str,
    ) -> Result[list[str]]:
        """
        Get list of bookmarked KU UIDs for user.

        Args:
            user_uid: User's unique identifier

        Returns:
            Result[list[str]]: List of bookmarked KU UIDs
        """
        if not self.backend:
            return Result.fail(Errors.system("Backend required", service="KuInteractionService"))

        query = """
        MATCH (user:User {uid: $user_uid})-[r:BOOKMARKED]->(ku:Ku)
        RETURN ku.uid as ku_uid
        ORDER BY r.bookmarked_at DESC
        """

        result = await self.backend.execute_query(query, {"user_uid": user_uid})

        if result.is_error:
            return Result.fail(result.expect_error())

        ku_uids = [record["ku_uid"] for record in (result.value or []) if record.get("ku_uid")]

        self.logger.debug(f"Retrieved {len(ku_uids)} bookmarked KUs for {user_uid}")
        return Result.ok(ku_uids)
