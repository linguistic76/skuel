"""
PathStep Progress Service
==========================

Handles path step progress tracking based on KU mastery.

Event Chain:
    KnowledgeMastered → PsProgressService.handle_knowledge_mastered()
    → PathStepProgressUpdated / PathStepCompleted
    → LpProgressService.handle_step_completed()

Progress is calculated as: kus_mastered / total_kus (via USES_KU + CONTAINS_KNOWLEDGE).
"""

from typing import TYPE_CHECKING

from core.events import publish_event
from core.events.learning_events import KnowledgeMastered, PathStepProgressUpdated
from core.models.type_hints import UserUID
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.neo4j_props import coerce_int

if TYPE_CHECKING:
    from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend


class PsProgressService:
    """
    PathStep progress tracking service.

    Handles automatic progress updates when users master KUs,
    calculating progress as kus_mastered / total_kus for each
    PathStep that contains the mastered KU.

    Event-Driven Architecture:
    - Subscribes to KnowledgeMastered events
    - Finds PathSteps containing the mastered KU via USES_KU/CONTAINS_KNOWLEDGE
    - Calculates progress from KU mastery counts
    - Publishes PathStepProgressUpdated events
    """

    def __init__(
        self,
        backend: "PsBackend | None" = None,
        event_bus=None,
    ) -> None:
        self.backend = backend
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.ps.progress")

    async def handle_knowledge_mastered(self, event: KnowledgeMastered) -> None:
        """
        Update path step progress when a KU is mastered.

        When a KU is mastered:
        1. Find all PathSteps containing this KU via USES_KU/CONTAINS_KNOWLEDGE
        2. For each PathStep, calculate kus_mastered / total_kus
        3. Publish PathStepProgressUpdated if progress changed

        Errors are logged but not raised — progress updates are best-effort.
        """
        try:
            if not self.backend:
                self.logger.warning("No backend available for KU→PathStep progress tracking")
                return

            # Find PathSteps that contain this KU
            result = await self.backend.find_path_steps_for_ku(event.ku_uid)
            if result.is_error:
                self.logger.error(f"Failed to query path steps for KU: {result.error}")
                return

            ps_uids = result.value or []

            if not ps_uids:
                self.logger.debug(f"No path steps contain KU {event.ku_uid}")
                return

            for ps_uid in ps_uids:
                try:
                    await self._update_ps_from_ku_mastery(
                        ps_uid=ps_uid,
                        user_uid=event.user_uid,
                    )
                except NEO4J_EXCEPTIONS as e:
                    self.logger.error(f"Failed to update path step {ps_uid} from KU mastery: {e}")
                except Exception as e:  # safety-net: catch unexpected errors
                    self.logger.error(f"Failed to update path step {ps_uid} from KU mastery: {e}")

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Error handling knowledge.mastered event: {e}")
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Error handling knowledge.mastered event: {e}")

    async def _update_ps_from_ku_mastery(self, ps_uid: str, user_uid: UserUID) -> None:
        """
        Update a single path step's progress from KU mastery.

        Progress is calculated as: kus_mastered / total_kus.
        """
        if not self.backend:
            return

        result = await self.backend.get_ku_completion_progress(ps_uid, user_uid)
        if result.is_error:
            self.logger.error(f"Failed to query PS progress: {result.error}")
            return

        progress_data = result.value or {}
        total_kus = coerce_int(progress_data.get("total_kus"))
        mastered_kus = coerce_int(progress_data.get("mastered_kus"))

        if total_kus == 0:
            self.logger.debug(f"No KUs found for path step {ps_uid}")
            return

        old_progress = max((mastered_kus - 1) / total_kus, 0.0)
        new_progress = mastered_kus / total_kus

        if abs(new_progress - old_progress) < 0.001:
            self.logger.debug(f"PS {ps_uid} progress unchanged ({new_progress:.1%}), skipping")
            return

        self.logger.info(
            f"Updated PS {ps_uid} progress: {old_progress:.1%} → {new_progress:.1%} "
            f"({mastered_kus}/{total_kus} KUs mastered)"
        )

        progress_event = PathStepProgressUpdated(
            ps_uid=ps_uid,
            user_uid=user_uid,
            old_progress=old_progress,
            new_progress=new_progress,
            kus_mastered=mastered_kus,
            kus_total=total_kus,
        )
        await publish_event(self.event_bus, progress_event, self.logger)
