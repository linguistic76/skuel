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
        teacher_uid: str,
        status_filter: str | None = None,
        entity_type_filter: str | None = None,
    ) -> Result[list[Any]]:
        """Get teacher's pending review queue."""
        return await self._review.get_review_queue(
            teacher_uid=teacher_uid,
            status_filter=status_filter,
            entity_type_filter=entity_type_filter,
        )

    # ------------------------------------------------------------------
    # Submission Detail + Report History
    # ------------------------------------------------------------------

    async def get_submission_detail(
        self, submission_uid: str, teacher_uid: str
    ) -> Result[Any]:
        """Get full submission detail for teacher review (access-checked)."""
        return await self._review.get_submission_detail(
            submission_uid=submission_uid, teacher_uid=teacher_uid
        )

    async def get_report_history(self, submission_uid: str) -> Result[list[Any]]:
        """Get EXERCISE_REPORT nodes linked to a submission."""
        return await self._review.get_report_history(submission_uid)

    # ------------------------------------------------------------------
    # Students
    # ------------------------------------------------------------------

    async def get_students_summary(self, teacher_uid: str) -> Result[list[Any]]:
        """Get students who shared work with teacher, with counts."""
        return await self._review.get_students_summary(teacher_uid=teacher_uid)

    async def get_student_submissions(
        self, teacher_uid: str, student_uid: str
    ) -> Result[list[Any]]:
        """Get all submissions from student shared with teacher."""
        return await self._review.get_student_submissions(
            teacher_uid=teacher_uid, student_uid=student_uid
        )

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    async def get_teacher_groups_with_stats(
        self, teacher_uid: str
    ) -> Result[list[Any]]:
        """Get teacher's groups with member/exercise/pending counts."""
        return await self._review.get_teacher_groups_with_stats(teacher_uid=teacher_uid)

    async def get_group_detail(
        self, group_uid: str, teacher_uid: str
    ) -> Result[list[Any]]:
        """Get group members with submission progress stats."""
        return await self._review.get_group_detail(
            group_uid=group_uid, teacher_uid=teacher_uid
        )

    # ------------------------------------------------------------------
    # KU Detail (optional — degrades when admin_stats is None)
    # ------------------------------------------------------------------

    async def get_student_ku_detail(
        self, student_uid: str
    ) -> dict[str, Any] | None:
        """Fetch KU detail for a student, returning None if unavailable.

        Absorbs the ``_fetch_ku_detail`` helper that was previously in
        ``teaching_ui.py``.
        """
        if not self._admin_stats:
            return None
        result = await self._admin_stats.get_user_ku_detail(student_uid)
        if result.is_error:
            logger.warning(f"Failed to load KU detail for {student_uid}: {result.error}")
            return None
        return result.value or None

    # ------------------------------------------------------------------
    # Composite: Teacher Dashboard
    # ------------------------------------------------------------------

    async def get_teacher_dashboard(
        self, teacher_uid: str
    ) -> Result[dict[str, Any]]:
        """Aggregate at-a-glance dashboard data in one call.

        Combines:
        1. Dashboard stats (pending count, totals)
        2. Recent review queue items (top 5)
        3. Active groups with stats

        Returns a unified dict; partial failures are logged but non-fatal.
        """
        stats: dict[str, Any] = {}
        recent_queue: list[Any] = []
        groups: list[Any] = []

        # 1. Dashboard stats
        stats_result = await self._review.get_dashboard_stats(teacher_uid=teacher_uid)
        if stats_result.is_error:
            logger.warning(f"Dashboard stats failed for {teacher_uid}: {stats_result.error}")
        else:
            stats = dict(stats_result.value or {})

        # 2. Recent queue items (top 5)
        queue_result = await self._review.get_review_queue(teacher_uid=teacher_uid)
        if queue_result.is_error:
            logger.warning(f"Review queue failed for {teacher_uid}: {queue_result.error}")
        else:
            recent_queue = list(queue_result.value or [])[:5]

        # 3. Groups
        groups_result = await self._review.get_teacher_groups_with_stats(
            teacher_uid=teacher_uid
        )
        if groups_result.is_error:
            logger.warning(f"Groups stats failed for {teacher_uid}: {groups_result.error}")
        else:
            groups = list(groups_result.value or [])

        return Result.ok({
            "stats": stats,
            "recent_queue": recent_queue,
            "groups": groups,
        })
