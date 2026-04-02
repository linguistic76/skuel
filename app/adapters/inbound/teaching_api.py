"""
Teaching API Routes
====================

API endpoints for teacher review workflow.

Provides:
- Review queue (pending student submissions)
- Feedback submission
- Revision requests
- Report approval

TEACHER role required for all endpoints.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

import pathlib
from typing import TYPE_CHECKING, Any

from fasthtml.common import Request
from starlette.responses import FileResponse

from adapters.inbound.auth.roles import UserRole, make_service_getter, require_role
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.form_helpers import parse_form_body, parse_json_body
from core.models.teaching.teaching_request import (
    CreateTeachingExerciseRequest,
    RequestRevisionRequest,
    UpdateTeachingExerciseRequest,
)

# NOTE: FastHTML evaluates string annotations at runtime via signature_ex(),
# so types used in @rt() handler return annotations must be real imports.
from core.ports.query_types import (
    ExerciseWithSubmissionCounts,
    GroupMemberProgress,
    ReviewQueueItem,
    StudentSubmissionItem,
    StudentSummaryItem,
    SubmissionDetailResult,
    SubmissionForExercise,
    TeacherDashboardStats,
    TeacherGroupStats,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import TeacherReviewOperations

logger = get_logger(__name__)

_REPORTS_DIR = pathlib.Path(__file__).parents[2] / "data" / "reports"


def _save_report_file(teacher_uid: str, submission_uid: str, content: str) -> str:
    """Save teacher feedback content to data/reports/{teacher_uid}/{submission_uid}/feedback.md.

    Returns the absolute file path as a string.
    """
    dest = _REPORTS_DIR / teacher_uid / submission_uid
    dest.mkdir(parents=True, exist_ok=True)
    file_path = dest / "feedback.md"
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)


def create_teaching_api_routes(
    app: Any,
    rt: Any,
    teacher_review_service: "TeacherReviewOperations",
    user_service: Any,
    exercises_service: Any,
) -> list[Any]:
    """
    Create teaching API routes.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        teacher_review_service: TeacherReviewService instance
        user_service: UserService for role checks
    """

    get_user_service = make_service_getter(user_service)

    @rt("/api/teaching/review-queue", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def review_queue(request: Request, current_user: Any) -> "Result[list[ReviewQueueItem]]":
        """Get teacher's pending review queue."""
        status_filter = request.query_params.get("status", None)
        return await teacher_review_service.get_review_queue(
            teacher_uid=current_user.uid,
            status_filter=status_filter,
        )

    @rt("/api/teaching/review/{uid}/report", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    async def submit_feedback(request: Request, uid: str, current_user: Any) -> Any:
        """Submit a .md feedback file as the teacher report for a student submission."""
        from fasthtml.common import Div, P

        form = await request.form()
        upload = form.get("feedback_file")
        if upload is None or not hasattr(upload, "read"):
            return Div(P("No file uploaded.", cls="text-sm text-destructive"))

        raw = await upload.read()
        if not raw:
            return Div(P("Uploaded file is empty.", cls="text-sm text-destructive"))

        content = raw.decode("utf-8")
        file_path = _save_report_file(current_user.uid, uid, content)

        result = await teacher_review_service.submit_report(
            report_uid=uid,
            teacher_uid=current_user.uid,
            feedback=content,
            file_path=file_path,
        )
        if result.is_error:
            error = result.expect_error()
            return Div(P(error.message, cls="text-sm text-destructive"))

        return Div(
            P("Feedback submitted successfully.", cls="text-sm text-green-600 font-medium"),
            cls="p-3 bg-green-50 rounded border border-green-200",
        )

    @rt("/api/teaching/review/{uid}/revision", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    async def request_revision(request: Request, uid: str, current_user: Any) -> Any:
        """Request revision for a student submission with text notes."""
        from fasthtml.common import Div, P

        result = await parse_form_body(request, RequestRevisionRequest)
        if result.is_error:
            error = result.expect_error()
            return Div(P(error.message, cls="text-sm text-destructive"))

        revision_result = await teacher_review_service.request_revision(
            report_uid=uid,
            teacher_uid=current_user.uid,
            notes=result.value.notes,
        )
        if revision_result.is_error:
            error = revision_result.expect_error()
            return Div(P(error.message, cls="text-sm text-destructive"))

        return Div(
            P("Revision requested.", cls="text-sm text-amber-600 font-medium"),
            cls="p-3 bg-amber-50 rounded border border-amber-200",
        )

    @rt("/api/reports/{report_uid}/download", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    async def download_report_file(
        request: Request, report_uid: str, current_user: Any
    ) -> Any:
        """Download the .md feedback file attached to an ExerciseReport."""
        path_result = await teacher_review_service.get_report_file_path(report_uid)
        if path_result.is_error or not path_result.value:
            from fasthtml.common import Div, P

            return Div(P("Report file not found.", cls="text-sm text-destructive"))

        file_path = pathlib.Path(path_result.value)
        if not file_path.exists():
            from fasthtml.common import Div, P

            return Div(P("Report file not found on disk.", cls="text-sm text-destructive"))

        return FileResponse(
            str(file_path),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="feedback-{report_uid[:12]}.md"'},
        )

    @rt("/api/teaching/review/{uid}/approve", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    async def approve_report(request: Request, uid: str, current_user: Any) -> Any:
        """Approve a student report."""
        from fasthtml.common import Div, P

        result = await teacher_review_service.approve_report(
            report_uid=uid,
            teacher_uid=current_user.uid,
        )
        if result.is_error:
            error = result.expect_error()
            return Div(P(error.message, cls="text-sm text-destructive"))

        return Div(
            P("Submission approved.", cls="text-sm text-green-600 font-medium"),
            cls="p-3 bg-green-50 rounded border border-green-200",
        )

    @rt("/api/teaching/review/{uid}", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_submission_detail(
        request: Request, uid: str, current_user: Any
    ) -> "Result[SubmissionDetailResult]":
        """Get full submission detail for teacher review.

        Returns submission content, student info, and linked exercise.
        Access-controlled: only succeeds if teacher has SHARES_WITH {role: 'teacher'} access.
        """
        return await teacher_review_service.get_submission_detail(
            submission_uid=uid,
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/review/{uid}/panel", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    async def get_review_panel(request: Request, uid: str, current_user: Any) -> Any:
        """Return inline review panel HTML fragment for the student detail tabbed view.

        Loaded by HTMX on first expand of a submission row. Returns:
        - Submission content
        - Feedback history (if any)
        - Action forms (if submission is actionable)
        """
        from ui.teaching.detail import render_review_panel_inline

        detail_result = await teacher_review_service.get_submission_detail(
            submission_uid=uid, teacher_uid=current_user.uid
        )
        history_result = await teacher_review_service.get_report_history(uid)

        detail_data: dict[str, Any] = (
            detail_result.value if not detail_result.is_error and detail_result.value else {}
        )
        history: list[dict[str, Any]] = (
            history_result.value if not history_result.is_error and history_result.value else []
        )

        return render_review_panel_inline(uid, detail_data, history)

    @rt("/api/teaching/exercises", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_exercises(
        request: Request, current_user: Any
    ) -> Result[list[ExerciseWithSubmissionCounts]]:
        """Get teacher's exercises with submission counts."""
        return await teacher_review_service.get_exercises_with_submission_counts(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/exercises/{uid}/submissions", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_exercise_submissions(
        request: Request, uid: str, current_user: Any
    ) -> Result[list[SubmissionForExercise]]:
        """Get all submissions against an exercise."""
        return await teacher_review_service.get_submissions_for_exercise(exercise_uid=uid)

    @rt("/api/teaching/students", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_students(request: Request, current_user: Any) -> Result[list[StudentSummaryItem]]:
        """Get students who shared work with the teacher."""
        return await teacher_review_service.get_students_summary(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/students/{uid}/submissions", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_student_submissions(
        request: Request, uid: str, current_user: Any
    ) -> Result[list[StudentSubmissionItem]]:
        """Get all submissions from a specific student."""
        return await teacher_review_service.get_student_submissions(
            teacher_uid=current_user.uid,
            student_uid=uid,
        )

    @rt("/api/teaching/dashboard", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_dashboard_stats(
        request: Request, current_user: Any
    ) -> "Result[TeacherDashboardStats]":
        """Get at-a-glance stats for the teacher dashboard."""
        return await teacher_review_service.get_dashboard_stats(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/groups", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_groups(request: Request, current_user: Any) -> Result[list[TeacherGroupStats]]:
        """Get teacher's groups with member, exercise, and pending submission counts."""
        return await teacher_review_service.get_teacher_groups_with_stats(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/groups/{uid}", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_group_detail(
        request: Request, uid: str, current_user: Any
    ) -> Result[list[GroupMemberProgress]]:
        """Get members of a specific group with their submission progress."""
        return await teacher_review_service.get_group_detail(
            group_uid=uid,
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/exercises", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler(success_status=201)
    async def create_teaching_exercise(
        request: Request, current_user: Any = None
    ) -> Result[dict[str, Any]]:
        """Create a new exercise owned by the authenticated teacher."""
        if not exercises_service:
            return Result.fail(
                Errors.system(
                    "exercises_service not available", operation="create_teaching_exercise"
                )
            )

        parsed = await parse_form_body(request, CreateTeachingExerciseRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        result = await exercises_service.create_exercise(
            user_uid=current_user.uid,
            name=req.name,
            instructions=req.instructions,
            model=req.model,
            scope=req.scope,
            group_uid=req.group_uid,
            due_date=req.due_date,
            processor_type=req.processor_type,
            context_notes=req.parsed_context_notes,
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value.to_dto().to_dict())

    @rt("/api/teaching/exercises/{uid}", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def update_teaching_exercise(
        request: Request, uid: str, current_user: Any = None
    ) -> Result[dict[str, Any]]:
        """Update an existing exercise."""
        if not exercises_service:
            return Result.fail(
                Errors.system(
                    "exercises_service not available", operation="update_teaching_exercise"
                )
            )

        parsed = await parse_form_body(request, UpdateTeachingExerciseRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        result = await exercises_service.update_exercise(
            uid=uid,
            name=req.name,
            instructions=req.instructions,
            model=req.model,
            context_notes=req.parsed_context_notes,
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value.to_dto().to_dict())

    logger.info("✅ Teaching API routes registered")
    return []
