"""
Learning Step Progress Service
===============================

Handles path step progress tracking based on Lesson completion.

Mirrors LpProgressService at the LS granularity level:
- LpProgressService tracks LP progress from KU mastery
- PsProgressService tracks LS progress from Lesson completion

Event Chain:
    KnowledgeMastered → LessonCompleted → PsProgressService
    → PathStepProgressUpdated / PathStepCompleted
    → LpProgressService.handle_step_completed
"""

from typing import TYPE_CHECKING

from core.events import publish_event
from core.events.curriculum_events import PathStepCompleted
from core.events.learning_events import LessonCompleted, PathStepProgressUpdated
from core.models.type_hints import UserUID
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.persistence.neo4j.domain_backends import PsBackend


class PsProgressService:
    """
    Learning Step progress tracking and completion management service.

    Handles automatic progress updates when users complete Lessons,
    eliminating direct dependencies between LessonMasteryService and PsService.

    Event-Driven Architecture:
    - Subscribes to LessonCompleted events
    - Calculates LS progress from completed Lessons
    - Publishes PathStepProgressUpdated events
    - Publishes PathStepCompleted when all Lessons completed
    """

    def __init__(
        self,
        backend: "PsBackend | None" = None,
        event_bus=None,
    ) -> None:
        self.backend = backend
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.ps.progress")

    async def handle_lesson_completed(self, event: LessonCompleted) -> None:
        """
        Update path step progress when a Lesson is completed.

        When a Lesson is completed:
        1. Find all LSs that contain this Lesson via HAS_LESSON
        2. For each LS, calculate new progress
        3. Publish PathStepProgressUpdated
        4. If 100%, publish PathStepCompleted

        Errors are logged but not raised — progress updates are best-effort.
        """
        try:
            if not self.backend:
                self.logger.warning("No backend available for Lesson→LS progress tracking")
                return

            result = await self.backend.get_steps_containing_lesson(event.lesson_uid)
            if result.is_error:
                self.logger.error(f"Failed to query path steps: {result.error}")
                return

            ps_uids = result.value or []

            if not ps_uids:
                self.logger.debug(f"No path steps contain Lesson {event.lesson_uid}")
                return

            for ps_uid in ps_uids:
                try:
                    await self._update_ls_from_lesson_completion(
                        ps_uid=ps_uid,
                        user_uid=event.user_uid,
                        newly_mastered_lesson=event.lesson_uid,
                    )
                except NEO4J_EXCEPTIONS as e:
                    self.logger.error(
                        f"Failed to update path step {ps_uid} from Lesson completion: {e}"
                    )
                except Exception as e:  # safety-net: catch unexpected errors
                    self.logger.error(
                        f"Failed to update path step {ps_uid} from Lesson completion: {e}"
                    )

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Error handling lesson.completed event: {e}")
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Error handling lesson.completed event: {e}")

    async def _update_ls_from_lesson_completion(
        self, ps_uid: str, user_uid: UserUID, newly_mastered_lesson: str
    ) -> None:
        """
        Update a single path step's progress from Lesson completion.

        Progress is calculated as: completed_lessons / total_lessons.

        Args:
            ps_uid: Learning step to update
            user_uid: User who completed the Lesson
            newly_mastered_lesson: UID of newly completed Lesson — semantically
                mirrors LpProgressService's concept at the correct granularity
                (Lesson completion drives LS progress, KU mastery drives LP progress).
                Currently unused (progress recalculated fresh), but semantically
                correct for future optimization.
        """
        if not self.backend:
            return

        result = await self.backend.get_lesson_completion_progress(ps_uid, user_uid)
        if result.is_error:
            self.logger.error(f"Failed to query LS progress: {result.error}")
            return

        progress_data = result.value or {}
        total_lessons = int(progress_data.get("total_lessons", 0))
        completed_lessons = int(progress_data.get("completed_lessons", 0))

        if total_lessons == 0:
            self.logger.debug(f"No lessons found for path step {ps_uid}")
            return

        old_progress = max((completed_lessons - 1) / total_lessons, 0.0)
        new_progress = completed_lessons / total_lessons

        if abs(new_progress - old_progress) < 0.001:
            self.logger.debug(f"LS {ps_uid} progress unchanged ({new_progress:.1%}), skipping")
            return

        self.logger.info(
            f"Updated LS {ps_uid} progress: {old_progress:.1%} → {new_progress:.1%} "
            f"({completed_lessons}/{total_lessons} lessons completed)"
        )

        progress_event = PathStepProgressUpdated(
            ps_uid=ps_uid,
            user_uid=user_uid,
            old_progress=old_progress,
            new_progress=new_progress,
            lessons_completed=completed_lessons,
            lessons_total=total_lessons,
        )
        await publish_event(self.event_bus, progress_event, self.logger)

        # If step completed (100%), publish PathStepCompleted
        if new_progress >= 1.0 and old_progress < 1.0:
            completed_event = PathStepCompleted(
                ps_uid=ps_uid,
                user_uid=user_uid,
                completion_score=1.0,
            )
            await publish_event(self.event_bus, completed_event, self.logger)
            self.logger.info(f"LS {ps_uid} completed!")
