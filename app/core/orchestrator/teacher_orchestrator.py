"""Teacher UI Orchestrator
=========================

Application orchestrator for the Teaching & Review Hub. Consolidates
TeacherReviewService and AdminStatsService into a single unified facade
for UI rendering.

All service dependencies except admin_stats are required — bootstrap raises
if any are missing (Fail-Fast Dependency Philosophy).

admin_stats is optional — KU detail degrades gracefully when unavailable
(same pattern as ProfileOrchestrator's context_intelligence).
"""

from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityStatus
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports import TeacherReviewOperations
    from core.services.admin_stats_service import AdminStatsService


logger = get_logger("skuel.orchestrators.teacher")


class TeacherOrchestrator:
    """Facade for the Teaching & Review Hub UI layer.

    Abstracts cross-domain reads so the UI routing layer depends only on this
    orchestrator.  ``teacher_review`` is required; ``admin_stats`` is optional
    (degrades gracefully — KU detail returns ``None``).
    """

    def __init__(
        self,
        teacher_review_service: "TeacherReviewOperations",
        admin_stats: "AdminStatsService | None" = None,
    ) -> None:
        self._review = teacher_review_service
        self._admin_stats = admin_stats

    # ------------------------------------------------------------------
    # Review Queue
    # ------------------------------------------------------------------

    async def get_review_queue(
        self,
        teacher_uid: UserUID,
        status_filter: str | None = None,
        student_uid: str | None = None,
    ) -> Result[list[Any]]:
        """Get teacher's pending review queue (group-shared entries only)."""
        return await self._review.get_review_queue(
            teacher_uid=teacher_uid,
            status_filter=status_filter,
            student_uid=student_uid,
        )

    # ------------------------------------------------------------------
    # Submission Detail
    # ------------------------------------------------------------------

    async def get_submission_detail(self, submission_uid: str, teacher_uid: UserUID) -> Result[Any]:
        """Get full submission detail for teacher review (access-checked)."""
        return await self._review.get_submission_detail(
            submission_uid=submission_uid, teacher_uid=teacher_uid
        )

    # ------------------------------------------------------------------
    # Students
    # ------------------------------------------------------------------

    async def get_students_summary(self, teacher_uid: UserUID) -> Result[list[Any]]:
        """Get students who shared work with teacher, with counts."""
        return await self._review.get_students_summary(teacher_uid=teacher_uid)

    async def get_student_submissions(
        self, teacher_uid: UserUID, student_uid: str
    ) -> Result[list[Any]]:
        """Get all submissions from student shared with teacher."""
        auth_check = await self._review.verify_teacher_authority(teacher_uid, student_uid)
        if auth_check.is_error:
            return Result.fail(auth_check)

        return await self._review.get_student_submissions(
            teacher_uid=teacher_uid, student_uid=student_uid
        )

    async def get_bucketed_student_submissions(
        self, teacher_uid: UserUID, student_uid: str
    ) -> Result[tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str]]:
        """Fetch and bucket student submissions into (pending, revision, completed, student_name).

        Neither Needs Review nor Revision Requested is a status read: each is
        the review queue scoped to this student — Needs Review with the
        default pending statuses, Revision Requested with the
        ``revision_requested`` status — the same query, the same copy-revision
        collapse, so the queue page and the student page can never disagree in
        either direction. An entry both queues omit (a superseded copy, even a
        revision-requested one whose student already resubmitted) is history
        and buckets to completed.
        """
        result = await self.get_student_submissions(
            teacher_uid=teacher_uid, student_uid=student_uid
        )
        if result.is_error:
            return Result.fail(result)

        queue_result = await self._review.get_review_queue(
            teacher_uid=teacher_uid, student_uid=student_uid
        )
        if queue_result.is_error:
            return Result.fail(queue_result)
        needs_review_uids = {item["submission_uid"] for item in queue_result.value or []}

        waiting_result = await self._review.get_review_queue(
            teacher_uid=teacher_uid,
            status_filter=EntityStatus.REVISION_REQUESTED.value,
            student_uid=student_uid,
        )
        if waiting_result.is_error:
            return Result.fail(waiting_result)
        waiting_uids = {item["submission_uid"] for item in waiting_result.value or []}

        pending: list[dict[str, Any]] = []
        revision: list[dict[str, Any]] = []
        completed: list[dict[str, Any]] = []
        student_name = student_uid

        for item in result.value or []:
            raw_name = item.get("student_name")
            if raw_name and student_name == student_uid:
                student_name = str(raw_name)
            if item.get("uid") in needs_review_uids:
                pending.append(item)
            elif item.get("uid") in waiting_uids:
                revision.append(item)
            else:
                completed.append(item)

        return Result.ok((pending, revision, completed, student_name))

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    async def get_teacher_groups_with_stats(self, teacher_uid: UserUID) -> Result[list[Any]]:
        """Get teacher's groups with member/exercise/pending counts."""
        return await self._review.get_teacher_groups_with_stats(teacher_uid=teacher_uid)

    async def get_group_detail(self, group_uid: str, teacher_uid: UserUID) -> Result[list[Any]]:
        """Get group members with submission progress stats."""
        return await self._review.get_group_detail(group_uid=group_uid, teacher_uid=teacher_uid)

    # ------------------------------------------------------------------
    # KU Detail (optional — degrades when admin_stats is None)
    # ------------------------------------------------------------------

    async def get_student_ku_detail(
        self, teacher_uid: UserUID, student_uid: str
    ) -> dict[str, Any] | None:
        """Fetch KU detail for a student, returning None if unavailable.

        Absorbs the ``_fetch_ku_detail`` helper that was previously in
        ``teaching_ui.py``. Enforces explicit ownership verification.
        """
        auth_check = await self._review.verify_teacher_authority(teacher_uid, student_uid)
        if auth_check.is_error:
            logger.warning(
                f"Unauthorized access attempt to KU detail "
                f"for student {student_uid} by teacher {teacher_uid}"
            )
            return None

        if not self._admin_stats:
            return None
        result = await self._admin_stats.get_user_ku_detail(UserUID(student_uid))
        if result.is_error:
            logger.warning(f"Failed to load KU detail for {student_uid}: {result.error}")
            return None
        return result.value or None
