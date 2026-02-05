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

Version: 1.0.0
Date: 2026-01-04
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver


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
        driver: "AsyncDriver | None" = None,
        event_bus=None,
    ) -> None:
        """
        Initialize KU interaction service.

        Args:
            driver: Neo4j driver for Cypher queries (REQUIRED)
            event_bus: Optional event bus for publishing events
        """
        self.driver = driver
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
        if not self.driver:
            return Result.fail(Errors.database("record_view", "Driver not available"))

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

        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    user_uid=user_uid,
                    ku_uid=ku_uid,
                    now=now,
                    time_spent=time_spent_seconds,
                )
                record = await result.single()

                if record:
                    self.logger.debug(
                        "Recorded view",
                        user_uid=user_uid,
                        ku_uid=ku_uid,
                        view_count=record["view_count"],
                    )
                    return Result.ok(True)
                else:
                    return Result.fail(Errors.not_found("User or KU", f"{user_uid} / {ku_uid}"))

        except Exception as e:
            self.logger.error("Failed to record view", error=str(e))
            return Result.fail(Errors.database("record_view", f"Failed to record view: {e}"))

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
        if not self.driver:
            return Result.fail(Errors.database("mark_in_progress", "Driver not available"))

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

        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    user_uid=user_uid,
                    ku_uid=ku_uid,
                    now=now,
                )
                record = await result.single()

                if record:
                    self.logger.debug(
                        "Marked in progress",
                        user_uid=user_uid,
                        ku_uid=ku_uid,
                    )
                    return Result.ok(True)
                else:
                    return Result.fail(Errors.not_found("User or KU", f"{user_uid} / {ku_uid}"))

        except Exception as e:
            self.logger.error("Failed to mark in progress", error=str(e))
            return Result.fail(
                Errors.database("mark_in_progress", f"Failed to mark in progress: {e}")
            )

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
        if not self.driver:
            return Result.fail(Errors.database("get_learning_state", "Driver not available"))

        query = """
        MATCH (ku:Ku {uid: $ku_uid})
        OPTIONAL MATCH (u:User {uid: $user_uid})-[v:VIEWED]->(ku)
        OPTIONAL MATCH (u:User {uid: $user_uid})-[p:IN_PROGRESS]->(ku)
        OPTIONAL MATCH (u:User {uid: $user_uid})-[m:MASTERED]->(ku)
        RETURN
            v IS NOT NULL as has_viewed,
            p IS NOT NULL as has_in_progress,
            m IS NOT NULL as has_mastered,
            v.first_viewed_at as first_viewed_at,
            v.last_viewed_at as last_viewed_at,
            v.view_count as view_count,
            v.time_spent_seconds as time_spent_seconds,
            p.started_at as started_at,
            m.mastered_at as mastered_at
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    user_uid=user_uid,
                    ku_uid=ku_uid,
                )
                record = await result.single()

                if not record:
                    return Result.fail(Errors.not_found("KU", ku_uid))

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
                )

                return Result.ok(progress)

        except Exception as e:
            self.logger.error("Failed to get learning state", error=str(e))
            return Result.fail(
                Errors.database("get_learning_state", f"Failed to get learning state: {e}")
            )

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
        if not self.driver:
            return Result.fail(Errors.database("get_learning_states_batch", "Driver not available"))

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

        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    user_uid=user_uid,
                    ku_uids=ku_uids,
                )
                records = await result.data()

                states = {}
                for record in records:
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

        except Exception as e:
            self.logger.error("Failed to get learning states batch", error=str(e))
            return Result.fail(
                Errors.database(
                    "get_learning_states_batch", f"Failed to get learning states batch: {e}"
                )
            )

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
        if not self.driver:
            return Result.fail(
                Errors.system("Neo4j driver required", service="KuInteractionService")
            )

        try:
            query = """
            MATCH (user:User {uid: $user_uid})
            MATCH (ku:Ku {uid: $ku_uid})
            MERGE (user)-[r:MARKED_AS_READ]->(ku)
            ON CREATE SET r.marked_at = datetime()
            RETURN r
            """

            async with self.driver.session() as session:
                await session.run(query, {"user_uid": user_uid, "ku_uid": ku_uid})

            self.logger.info(f"Marked KU as read: {user_uid} -> {ku_uid}")
            return Result.ok(None)

        except Exception as e:
            self.logger.error(f"Failed to mark KU as read: {e}")
            return Result.fail(Errors.database("mark_as_read", f"Failed to mark KU as read: {e}"))

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
        if not self.driver:
            return Result.fail(
                Errors.system("Neo4j driver required", service="KuInteractionService")
            )

        try:
            # Check if bookmark exists
            check_query = """
            MATCH (user:User {uid: $user_uid})-[r:BOOKMARKED]->(ku:Ku {uid: $ku_uid})
            RETURN r IS NOT NULL as is_bookmarked
            """

            async with self.driver.session() as session:
                result = await session.run(check_query, {"user_uid": user_uid, "ku_uid": ku_uid})
                record = await result.single()
                is_bookmarked = record["is_bookmarked"] if record else False

                if is_bookmarked:
                    # Remove bookmark
                    delete_query = """
                    MATCH (user:User {uid: $user_uid})-[r:BOOKMARKED]->(ku:Ku {uid: $ku_uid})
                    DELETE r
                    """
                    await session.run(delete_query, {"user_uid": user_uid, "ku_uid": ku_uid})
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
                    await session.run(create_query, {"user_uid": user_uid, "ku_uid": ku_uid})
                    self.logger.info(f"Added bookmark: {user_uid} -> {ku_uid}")
                    return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to toggle bookmark: {e}")
            return Result.fail(
                Errors.database("toggle_bookmark", f"Failed to toggle bookmark: {e}")
            )

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
        if not self.driver:
            return Result.fail(
                Errors.system("Neo4j driver required", service="KuInteractionService")
            )

        try:
            query = """
            MATCH (user:User {uid: $user_uid})-[r:BOOKMARKED]->(ku:Ku)
            RETURN ku.uid as ku_uid
            ORDER BY r.bookmarked_at DESC
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid})
                records = await result.data()
                ku_uids = [record["ku_uid"] for record in records if record.get("ku_uid")]

            self.logger.debug(f"Retrieved {len(ku_uids)} bookmarked KUs for {user_uid}")
            return Result.ok(ku_uids)

        except Exception as e:
            self.logger.error(f"Failed to get bookmarked KUs: {e}")
            return Result.fail(
                Errors.database("get_bookmarked_kus", f"Failed to get bookmarked KUs: {e}")
            )
