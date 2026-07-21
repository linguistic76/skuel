"""
Path Step Mastery Service - Pedagogical Tracking
==================================================

Tracks user mastery transitions for PathSteps (curriculum content units).

State Progression:
    NONE -> VIEWED -> IN_PROGRESS -> MASTERED

Responsibilities:
- Record when user views path step content
- Track in-progress learning state
- Manage MASTERED transitions
- Support pedagogical search filters
- Detect PathStep completion when all KUs are mastered

Architecture:
- Delegates Cypher to PathStep backend
- Stores relationship properties for time tracking
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.curriculum_events import PathStepCompleted, PathStepEnrolled
from core.events.learning_events import KnowledgeMastered
from core.models.type_hints import UserUID
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import PsOperations


class LearningState(StrEnum):
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


class PsMasteryService:
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
        backend: "PsOperations",
        event_bus=None,
    ) -> None:
        self.backend = backend
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.ps.mastery")

    async def record_view(
        self,
        user_uid: UserUID,
        ku_uid: str,
        time_spent_seconds: int = 0,
    ) -> Result[bool]:
        """
        Record that a user viewed a knowledge unit.

        Creates or updates VIEWED relationship with timestamps and counts.
        """
        now = datetime.now(UTC).isoformat()
        result = await self.backend.record_view(user_uid, ku_uid, now, time_spent_seconds)

        if result.is_error:
            return Result.fail(result)

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

    async def count_in_progress_steps(self, user_uid: UserUID) -> Result[int]:
        """Count PathSteps the user is currently enrolled in (IN_PROGRESS)."""
        result = await self.backend.count_in_progress_path_steps(user_uid)
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        count = records[0]["cnt"] if records else 0
        return Result.ok(int(count))

    async def get_in_progress_step_uids(self, user_uid: UserUID) -> Result[list[str]]:
        """Get UIDs of PathSteps the user is enrolled in (IN_PROGRESS)."""
        result = await self.backend.get_in_progress_path_step_uids(user_uid)
        if result.is_error:
            return Result.fail(result)
        uids = [rec["uid"] for rec in (result.value or []) if rec.get("uid")]
        return Result.ok(uids)

    async def mark_in_progress(
        self,
        user_uid: UserUID,
        ku_uid: str,
    ) -> Result[bool]:
        """Mark a knowledge unit as in-progress for a user."""
        now = datetime.now(UTC).isoformat()
        result = await self.backend.mark_in_progress(user_uid, ku_uid, now)

        if result.is_error:
            return Result.fail(result)

        if result.value:
            self.logger.debug("Marked in progress", user_uid=user_uid, ku_uid=ku_uid)
            await publish_event(
                self.event_bus,
                PathStepEnrolled(ps_uid=ku_uid, user_uid=user_uid),
                self.logger,
            )
            return Result.ok(True)
        else:
            return Result.fail(Errors.not_found("User or KU", f"{user_uid} / {ku_uid}"))

    async def get_learning_state(
        self,
        user_uid: UserUID,
        ku_uid: str,
    ) -> Result[UserKuProgress]:
        """
        Get user's learning state for a knowledge unit.

        Checks for MASTERED, IN_PROGRESS, and VIEWED relationships in that order
        to determine the highest state achieved.
        """
        result = await self.backend.get_learning_state_raw(user_uid, ku_uid)

        if result.is_error:
            return Result.fail(result)

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
        user_uid: UserUID,
        ku_uids: list[str],
    ) -> Result[dict[str, LearningState]]:
        """Get learning states for multiple KUs in one query."""
        if not ku_uids:
            return Result.ok({})

        result = await self.backend.get_learning_states_batch_raw(user_uid, ku_uids)

        if result.is_error:
            return Result.fail(result)

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

    async def mark_as_learning(self, user_uid: UserUID, ku_uid: str) -> Result[bool]:
        """Transition a completed step back to in-progress (Review again).

        Deletes MARKED_AS_READ, ensures IN_PROGRESS. Does NOT fire PathStepEnrolled
        — this is a re-read, not a new enrollment.
        """
        result = await self.backend.mark_as_learning(user_uid, ku_uid)
        if result.is_error:
            return Result.fail(result)
        if result.value:
            self.logger.debug("Reset to learning", user_uid=user_uid, ku_uid=ku_uid)
            return Result.ok(True)
        return Result.fail(Errors.not_found("User or PathStep", f"{user_uid} / {ku_uid}"))

    async def mark_as_read(
        self,
        user_uid: UserUID,
        ku_uid: str,
    ) -> Result[bool]:
        """Mark a KU as read by the user."""
        result = await self.backend.mark_as_read(user_uid, ku_uid)

        if result.is_error:
            return Result.fail(result)

        self.logger.info(f"Marked KU as read: {user_uid} -> {ku_uid}")
        return Result.ok(True)

    async def set_bookmark(self, user_uid: UserUID, ku_uid: str, desired: bool) -> Result[bool]:
        """Set bookmark to an explicit state — idempotent, safe on retry.

        Use this when the caller knows the intended state (e.g., the PS detail
        page posts on=true|false). Prefer toggle_bookmark only when the caller
        genuinely wants to flip whatever the current state is.
        """
        if desired:
            result = await self.backend.create_bookmark(user_uid, ku_uid)
        else:
            result = await self.backend.delete_bookmark(user_uid, ku_uid)
        if result.is_error:
            return Result.fail(result)
        self.logger.debug("Set bookmark", user_uid=user_uid, ku_uid=ku_uid, desired=desired)
        return Result.ok(desired)

    async def toggle_bookmark(
        self,
        user_uid: UserUID,
        ku_uid: str,
    ) -> Result[bool]:
        """Toggle bookmark state for a KU."""
        # Check if bookmark exists
        check_result = await self.backend.check_bookmark(user_uid, ku_uid)

        if check_result.is_error:
            return Result.fail(check_result)

        is_bookmarked = check_result.value[0]["is_bookmarked"] if check_result.value else False

        if is_bookmarked:
            del_result = await self.backend.delete_bookmark(user_uid, ku_uid)
            if del_result.is_error:
                return Result.fail(del_result)
            self.logger.info(f"Removed bookmark: {user_uid} -> {ku_uid}")
            return Result.ok(False)
        else:
            create_result = await self.backend.create_bookmark(user_uid, ku_uid)
            if create_result.is_error:
                return Result.fail(create_result)
            self.logger.info(f"Added bookmark: {user_uid} -> {ku_uid}")
            return Result.ok(True)

    async def mark_mastered(
        self,
        user_uid: UserUID,
        ku_uid: str,
        mastery_score: float,
        method: str = "report_approval",
    ) -> Result[bool]:
        """
        Mark a KU as mastered by the user.

        Creates or updates a MASTERED relationship. The Cypher uses
        CASE WHEN new > existing so higher scores always win — teacher
        approval scores will upgrade AI feedback scores for the same exercise.

        The mastery_score is determined by MasteryImpact on the Exercise:
        - EntryReportService uses MasteryImpact.get_ai_score() (0.4-0.8)
        - TeacherReviewService uses MasteryImpact.get_teacher_score() (0.6-0.95)

        See: core/models/enums/learning_enums.py - MasteryImpact
        """
        now = datetime.now(UTC).isoformat()
        result = await self.backend.mark_mastered(user_uid, ku_uid, now, mastery_score, method)

        if result.is_error:
            return Result.fail(result)

        if result.value:
            record = result.value[0]
            self.logger.info(
                f"Marked KU as mastered: {user_uid} -> {ku_uid} "
                f"(score={record['mastery_score']}, method={method})"
            )

            # Publish KnowledgeMastered event to activate LP progress chain
            event = KnowledgeMastered(
                ku_uid=ku_uid,
                user_uid=user_uid,
                mastery_score=record["mastery_score"],
            )
            await publish_event(self.event_bus, event, self.logger)

            return Result.ok(True)
        else:
            return Result.fail(Errors.not_found("User or KU", f"{user_uid} / {ku_uid}"))

    # =========================================================================
    # EVENT HANDLERS
    # =========================================================================

    async def handle_knowledge_mastered(self, event: KnowledgeMastered) -> None:
        """
        Detect PathStep completion when a KU is mastered.

        Checks if all KUs linked via USES_KU/CONTAINS_KNOWLEDGE are now mastered.
        If so, publishes PathStepCompleted.

        Best-effort: errors are logged but not raised to prevent
        KU mastery from failing if path step detection fails.
        """
        try:
            result = await self.backend.detect_path_step_completion(event.ku_uid, event.user_uid)

            if result.is_error:
                self.logger.error(f"Failed to check path step completion: {result.error}")
                return

            for record in result.value or []:
                ps_event = PathStepCompleted(
                    ps_uid=record["ps_uid"],
                    user_uid=event.user_uid,
                )
                await publish_event(self.event_bus, ps_event, self.logger)
                self.logger.info(
                    f"Path step completed: {record['ps_uid']} "
                    f"(all KUs mastered by {event.user_uid})"
                )

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Error detecting path step completion: {e}")
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Error detecting path step completion: {e}")

    async def get_bookmarked_kus(
        self,
        user_uid: UserUID,
    ) -> Result[list[str]]:
        """Get list of bookmarked KU UIDs for user."""
        result = await self.backend.get_bookmarked_kus(user_uid)

        if result.is_error:
            return Result.fail(result)

        ku_uids = [record["ku_uid"] for record in (result.value or []) if record.get("ku_uid")]

        self.logger.debug(f"Retrieved {len(ku_uids)} bookmarked KUs for {user_uid}")
        return Result.ok(ku_uids)

    async def get_all_user_knowledge_status(
        self, user_uid: UserUID
    ) -> Result[list[dict[str, Any]]]:
        """Get all knowledge entities with per-user VIEWED/BOOKMARKED/MASTERED status."""
        result = await self.backend.get_all_user_knowledge_status(user_uid)

        if result.is_error:
            return Result.fail(result)

        records = [dict(r) for r in (result.value or [])]
        self.logger.debug(f"Retrieved knowledge status for {len(records)} entities for {user_uid}")
        return Result.ok(records)
