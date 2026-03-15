"""
Learning Path Progress Service
===============================

Handles learning path progress tracking based on KU mastery.

Responsibilities:
- Progress calculation from KU mastery
- Automatic LP progress updates via events
- Completion detection and celebration
- Milestone management
"""

from datetime import datetime
from typing import TYPE_CHECKING

from core.events import LearningPathCompleted, LearningPathProgressUpdated, publish_event
from core.events.curriculum_events import LearningStepCompleted
from core.events.learning_events import KnowledgeMastered
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.persistence.neo4j.domain_backends import LpBackend


class LpProgressService:
    """
    Learning Path progress tracking and completion management service.

    Handles automatic progress updates when users master knowledge units,
    eliminating direct dependencies between LessonService and LpService.

    Event-Driven Architecture:
    - Subscribes to KnowledgeMastered events
    - Calculates LP progress from mastered KUs
    - Publishes LearningPathProgressUpdated events
    - Publishes LearningPathCompleted when all KUs mastered
    """

    def __init__(
        self,
        backend: "LpBackend | None" = None,
        event_bus=None,
    ) -> None:
        """
        Initialize learning path progress service.

        Args:
            backend: LpBackend for KU mastery graph queries (REQUIRED)
            event_bus: Optional event bus for publishing events
        """
        self.backend = backend
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.lp.progress")

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def handle_knowledge_mastered(self, event: KnowledgeMastered) -> None:
        """
        Update learning path progress when a knowledge unit is mastered.

        This handler implements event-driven LP progress updates,
        eliminating direct dependency between LessonService and LpService.

        When a KU is mastered:
        1. Find all learning paths that contain this KU
        2. For each path, check if user is enrolled/active
        3. Calculate new progress (mastered KUs / total KUs)
        4. Update LP progress in database
        5. Publish LearningPathProgressUpdated event
        6. If 100%, publish LearningPathCompleted event

        Args:
            event: KnowledgeMastered event containing ku_uid and user_uid

        Note:
            Errors are logged but not raised - progress updates are best-effort
            to prevent KU mastery from failing if LP update fails.
        """
        try:
            if not self.backend:
                self.logger.warning("No backend available for KU→LP event integration")
                return

            self.logger.debug(
                f"Querying for learning paths containing KU {event.ku_uid}, user {event.user_uid}"
            )

            result = await self.backend.get_paths_containing_ku(event.ku_uid)
            if result.is_error:
                self.logger.error(f"Failed to query learning paths: {result.error}")
                return

            lp_uids = result.value or []

            self.logger.debug(f"Found {len(lp_uids)} learning paths containing KU: {lp_uids}")

            if not lp_uids:
                self.logger.debug(f"No learning paths contain KU {event.ku_uid}")
                return

            # Update each linked learning path
            for lp_uid in lp_uids:
                try:
                    await self._update_lp_from_ku_mastery(
                        lp_uid=lp_uid,
                        user_uid=event.user_uid,
                    )
                except Exception as e:
                    # Best-effort: Don't let one LP failure block others
                    self.logger.error(
                        f"Failed to update learning path {lp_uid} from KU mastery: {e}"
                    )

        except Exception as e:
            # Best-effort: Log error but don't raise (prevent KU mastery failure)
            self.logger.error(f"Error handling knowledge_mastered event: {e}")

    async def handle_step_completed(self, event: LearningStepCompleted) -> None:
        """
        Update learning path progress when a learning step is completed.

        Finds all LPs containing this LS (via HAS_STEP) and rechecks
        LP progress. Reuses existing KU-based progress calculation
        since LS completion implies underlying KU mastery.

        Errors are logged but not raised — progress updates are best-effort.
        """
        try:
            if not self.backend:
                self.logger.warning("No backend available for LS→LP event integration")
                return

            # Find LPs containing this LS via HAS_STEP
            query = """
            MATCH (lp:Entity {entity_type: 'learning_path'})-[:HAS_STEP]->(ls:Entity {uid: $ls_uid})
            RETURN DISTINCT lp.uid as lp_uid
            """
            result = await self.backend.execute_query(query, {"ls_uid": event.ls_uid})
            if result.is_error:
                self.logger.error(f"Failed to query LPs for LS {event.ls_uid}: {result.error}")
                return

            lp_uids = [r["lp_uid"] for r in (result.value or [])]

            if not lp_uids:
                self.logger.debug(f"No learning paths contain LS {event.ls_uid}")
                return

            for lp_uid in lp_uids:
                try:
                    await self._update_lp_from_ku_mastery(
                        lp_uid=lp_uid,
                        user_uid=event.user_uid,
                    )
                except Exception as e:
                    self.logger.error(
                        f"Failed to update LP {lp_uid} from LS completion: {e}"
                    )

        except Exception as e:
            self.logger.error(f"Error handling learning_step.completed event: {e}")

    # FUTURE-IMPL: FUTURE-IMPL-009 - See docs/reference/DEFERRED_IMPLEMENTATIONS.md
    async def _update_lp_from_ku_mastery(
        self, lp_uid: str, user_uid: str
    ) -> None:
        """
        Internal helper to update a single learning path's progress from KU mastery.

        For learning paths, progress is calculated as:
        - progress = (mastered_kus_count / total_kus_count) * 100

        Args:
            lp_uid: Learning path to update
            user_uid: User who mastered the KU
        """
        if not self.backend:
            self.logger.warning("No backend available for LP progress tracking")
            return

        result = await self.backend.get_ku_mastery_progress(lp_uid, user_uid)
        if result.is_error:
            self.logger.error(f"Failed to query LP progress: {result.error}")
            return

        progress_data = result.value or {}

        if not progress_data or progress_data.get("total_kus", 0) == 0:
            self.logger.debug(f"No KUs found for learning path {lp_uid}")
            return

        total_kus = progress_data.get("total_kus", 0)
        mastered_kus = progress_data.get("mastered_kus", 0)

        # Calculate old and new progress
        # Note: We need to get the user's current LP progress from storage
        # For now, we'll calculate it fresh each time
        # In a real implementation, we'd query a UserLpProgress entity
        old_progress_percentage = ((mastered_kus - 1) / total_kus) * 100 if total_kus > 0 else 0.0
        new_progress_percentage = (mastered_kus / total_kus) * 100 if total_kus > 0 else 0.0

        # Skip update if progress unchanged
        if abs(new_progress_percentage - old_progress_percentage) < 0.01:
            self.logger.debug(
                f"LP {lp_uid} progress unchanged ({new_progress_percentage:.1f}%), skipping update"
            )
            return

        self.logger.info(
            f"Updated LP {lp_uid} progress: {old_progress_percentage:.1f}% → {new_progress_percentage:.1f}% "
            f"({mastered_kus}/{total_kus} KUs mastered)"
        )

        # Publish LearningPathProgressUpdated event
        progress_event = LearningPathProgressUpdated(
            path_uid=lp_uid,
            user_uid=user_uid,
            occurred_at=datetime.now(),
            old_progress=old_progress_percentage / 100.0,  # Convert to 0.0-1.0
            new_progress=new_progress_percentage / 100.0,  # Convert to 0.0-1.0
            kus_completed=mastered_kus,
            kus_total=total_kus,
        )
        await publish_event(self.event_bus, progress_event, self.logger)

        # If path completed (100%), publish LearningPathCompleted event
        if new_progress_percentage >= 100 and old_progress_percentage < 100:
            # Calculate time to completion (would need UserLpProgress entity with start_date)
            # For now, using estimated hours from LP
            completed_event = LearningPathCompleted(
                path_uid=lp_uid,
                user_uid=user_uid,
                occurred_at=datetime.now(),
                kus_mastered=mastered_kus,
                average_mastery_score=1.0,  # Would calculate from actual mastery scores
            )
            await publish_event(self.event_bus, completed_event, self.logger)
            self.logger.info(f"🎉 LP {lp_uid} completed!")
