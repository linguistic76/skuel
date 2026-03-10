"""
ZPD Event Handler — Snapshot persistence on significant events
===============================================================

Takes a ZPD snapshot when pedagogically significant events occur:
- SubmissionApproved — student work validated
- ReportSubmitted — teacher feedback delivered
- KnowledgeMastered — KU mastery confirmed
- LearningStepCompleted — curriculum progress
- LearningPathProgressUpdated — LP advancement

Each handler extracts the user_uid from the event and delegates to
_take_snapshot(), which reassesses the zone and persists the result.

See: adapters/persistence/neo4j/zpd_snapshot_backend.py
See: services_bootstrap.py — event subscription wiring
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.persistence.neo4j.zpd_snapshot_backend import ZPDSnapshotBackend
    from core.events.curriculum_events import LearningStepCompleted
    from core.events.learning_events import KnowledgeMastered, LearningPathProgressUpdated
    from core.events.submission_events import ReportSubmitted, SubmissionApproved
    from core.services.zpd.zpd_service import ZPDService

logger = get_logger(__name__)


class ZPDSnapshotHandler:
    """Handles pedagogically significant events by taking ZPD snapshots.

    Args:
        zpd_service: ZPDService for reassessing the zone.
        snapshot_backend: ZPDSnapshotBackend for persisting snapshots.
    """

    def __init__(self, zpd_service: ZPDService, snapshot_backend: ZPDSnapshotBackend) -> None:
        self._zpd_service = zpd_service
        self._snapshot_backend = snapshot_backend
        self._logger = logger

    async def handle_submission_approved(self, event: SubmissionApproved) -> None:
        """Snapshot when a submission is approved — mastery signal."""
        await self._take_snapshot(event.student_uid, "submission.approved")

    async def handle_report_submitted(self, event: ReportSubmitted) -> None:
        """Snapshot when a teacher submits a report — feedback delivered."""
        await self._take_snapshot(event.student_uid, "submission.report_submitted")

    async def handle_knowledge_mastered(self, event: KnowledgeMastered) -> None:
        """Snapshot when a KU is mastered — zone shift."""
        await self._take_snapshot(event.user_uid, "knowledge.mastered")

    async def handle_learning_step_completed(self, event: LearningStepCompleted) -> None:
        """Snapshot when a learning step is completed — curriculum progress."""
        await self._take_snapshot(event.user_uid, "learning_step.completed")

    async def handle_learning_path_progress(self, event: LearningPathProgressUpdated) -> None:
        """Snapshot when learning path progress changes — LP advancement."""
        await self._take_snapshot(event.user_uid, "learning_path.progress_updated")

    async def _take_snapshot(self, user_uid: str, trigger: str) -> None:
        """Reassess the user's zone and persist the snapshot."""
        assessment_result = await self._zpd_service.assess_zone(user_uid)
        if assessment_result.is_error:
            self._logger.warning(
                "ZPD snapshot skipped for %s (trigger: %s): %s",
                user_uid,
                trigger,
                assessment_result.expect_error(),
            )
            return

        assessment = assessment_result.value
        if assessment.is_empty():
            self._logger.debug(
                "ZPD snapshot skipped for %s (trigger: %s): empty assessment", user_uid, trigger
            )
            return

        save_result = await self._snapshot_backend.save_snapshot(user_uid, assessment, trigger)
        if save_result.is_error:
            self._logger.warning(
                "ZPD snapshot persistence failed for %s (trigger: %s): %s",
                user_uid,
                trigger,
                save_result.expect_error(),
            )
        else:
            self._logger.info(
                "ZPD snapshot taken for %s (trigger: %s, zone: %d current, %d proximal)",
                user_uid,
                trigger,
                len(assessment.current_zone),
                len(assessment.proximal_zone),
            )
