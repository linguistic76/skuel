"""
Group & Teaching Domain Protocols
==================================

Route-facing protocols for Group management and Teacher review workflow.
ISP-compliant: each protocol captures only the methods called from routes.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class GroupOperations(Protocol):
    """Group CRUD and membership management operations.

    Route consumer: groups_api.py (primary), groups_ui.py
    Implementation: GroupService
    """

    async def create_group(
        self,
        teacher_uid: str,
        name: str,
        description: str | None = None,
        max_members: int | None = None,
    ) -> Result[Any]:
        """Create a new group. Returns Result[Group]."""
        ...

    async def get_group(self, uid: str) -> Result[Any | None]:
        """Get group by UID. Returns Result[Group | None]."""
        ...

    async def list_teacher_groups(self, teacher_uid: str) -> Result[list[Any]]:
        """List groups owned by a teacher. Returns Result[list[Group]]."""
        ...

    async def get_user_groups(self, user_uid: str) -> Result[list[Any]]:
        """List groups the user is a member of. Returns Result[list[Group]]."""
        ...

    async def update_group(
        self,
        uid: str,
        name: str | None = None,
        description: str | None = None,
        max_members: int | None = None,
        is_active: bool | None = None,
    ) -> Result[Any]:
        """Update a group. Returns Result[Group]."""
        ...

    async def delete_group(self, uid: str) -> Result[bool]:
        """Delete a group. Returns Result[bool]."""
        ...

    async def add_member(
        self,
        group_uid: str,
        user_uid: str,
        role: str = "student",
    ) -> Result[bool]:
        """Add a member to a group. Returns Result[bool]."""
        ...

    async def remove_member(
        self,
        group_uid: str,
        user_uid: str,
    ) -> Result[bool]:
        """Remove a member from a group. Returns Result[bool]."""
        ...

    async def get_members(self, group_uid: str) -> Result[list[dict[str, Any]]]:
        """Get group members. Returns Result[list[dict]]."""
        ...


@runtime_checkable
class TeacherReviewOperations(Protocol):
    """Teacher review workflow operations.

    Route consumer: teaching_api.py (primary)
    Implementation: TeacherReviewService
    """

    async def get_review_queue(
        self,
        teacher_uid: str,
        status_filter: str | None = None,
        ku_type_filter: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """Get teacher's pending review queue. Returns Result[list[dict]]."""
        ...

    async def get_feedback_history(
        self,
        submission_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """Get SUBMISSION_FEEDBACK nodes linked to a submission. Returns Result[list[dict]]."""
        ...

    async def submit_feedback(
        self,
        report_uid: str,
        teacher_uid: str,
        feedback: str,
    ) -> Result[dict[str, Any]]:
        """Submit feedback for a student report. Returns Result[dict]."""
        ...

    async def request_revision(
        self,
        report_uid: str,
        teacher_uid: str,
        notes: str,
    ) -> Result[dict[str, Any]]:
        """Request revision for a student report. Returns Result[dict]."""
        ...

    async def approve_report(
        self,
        report_uid: str,
        teacher_uid: str,
    ) -> Result[dict[str, Any]]:
        """Approve a student report. Returns Result[dict]."""
        ...

    async def get_exercises_with_submission_counts(
        self, teacher_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Get teacher's exercises with submission/reviewed counts. Returns Result[list[dict]]."""
        ...

    async def get_submissions_for_exercise(self, exercise_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all submissions against an exercise. Returns Result[list[dict]]."""
        ...

    async def get_students_summary(self, teacher_uid: str) -> Result[list[dict[str, Any]]]:
        """Get students who shared work with teacher, with counts. Returns Result[list[dict]]."""
        ...

    async def get_student_submissions(
        self, teacher_uid: str, student_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Get all submissions from student shared with teacher. Returns Result[list[dict]]."""
        ...

    async def get_submission_detail(
        self, submission_uid: str, teacher_uid: str
    ) -> Result[dict[str, Any]]:
        """Get full submission detail for teacher review (access-checked). Returns Result[dict]."""
        ...

    async def get_dashboard_stats(self, teacher_uid: str) -> Result[dict[str, Any]]:
        """Get at-a-glance stats for dashboard. Returns Result[dict]."""
        ...

    async def get_teacher_groups_with_stats(self, teacher_uid: str) -> Result[list[dict[str, Any]]]:
        """Get teacher's groups with member/exercise/pending counts. Returns Result[list[dict]]."""
        ...

    async def get_group_detail(
        self, group_uid: str, teacher_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Get group members with submission progress stats. Returns Result[list[dict]]."""
        ...
