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

See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
"""

import pathlib
import secrets
from typing import TYPE_CHECKING, Any

import starlette.datastructures
from fasthtml.common import Request
from starlette.responses import FileResponse

from adapters.inbound.auth.roles import UserRole, make_service_getter, require_role
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.form_helpers import parse_form_body
from core.models.teaching.teaching_request import RequestRevisionRequest

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
    TeacherGroupStats,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from ui.components import ButtonT
from ui.primitives import ButtonLink

if TYPE_CHECKING:
    from core.ports import TeacherReviewOperations
    from core.ports.report_protocols import EntryReportOperations

logger = get_logger(__name__)

_REPORTS_DIR = pathlib.Path(__file__).parents[2] / "data" / "reports"


def _save_report_file(teacher_uid: str, submission_uid: str, content: str) -> str:
    """Save teacher feedback to data/reports/{teacher_uid}/{submission_uid}/feedback-<token>.md.

    The filename is unique per submit — the path is persisted on the
    EntryReport and read back by the download route, and the file is written
    BEFORE the service validates the submission status. With a fixed name, a
    retried submit against an already-completed submission would overwrite
    (and its rejection cleanup delete) the file an earlier persisted report
    references. Returns the absolute file path as a string.
    """
    dest = _REPORTS_DIR / teacher_uid / submission_uid
    dest.mkdir(parents=True, exist_ok=True)
    file_path = dest / f"feedback-{secrets.token_hex(4)}.md"
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)


def create_teaching_api_routes(
    app: Any,
    rt: Any,
    teacher_review_service: "TeacherReviewOperations",
    user_service: Any,
    exercises_service: Any,
    user_entry_service: Any = None,
    revised_exercise_service: Any = None,
    entry_report_service: "EntryReportOperations | None" = None,
) -> list[Any]:
    """
    Create teaching API routes.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        teacher_review_service: TeacherReviewService instance
        user_service: UserService for role checks
        user_entry_service: UserEntryService — teacher-authorized entry deletion (ADR-054)
        revised_exercise_service: Retained for DomainRouteConfig signature compatibility
    """

    get_user_service = make_service_getter(user_service)

    @rt("/api/teaching/review-queue", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def review_queue(
        request: Request, current_user: Any = None
    ) -> "Result[list[ReviewQueueItem]]":
        """Get teacher's pending review queue (group-shared entries only)."""
        status_filter = request.query_params.get("status", None)
        return await teacher_review_service.get_review_queue(
            teacher_uid=current_user.uid,
            status_filter=status_filter,
        )

    @rt("/api/teaching/review/{uid}/report", methods=["POST"])
    @csrf_protected
    @require_role(UserRole.TEACHER, get_user_service)
    async def submit_feedback(request: Request, uid: str, current_user: Any = None) -> Any:
        """Submit a .md feedback file as the teacher report for a student submission."""
        from fasthtml.common import Div, P

        form = await request.form()
        upload = form.get("feedback_file")
        if upload is None or not isinstance(upload, starlette.datastructures.UploadFile):
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
            # The service refused (e.g. the entry is no longer in a reviewable
            # status) — remove the file written above so a rejected submit
            # leaves no orphan on disk.
            pathlib.Path(file_path).unlink(missing_ok=True)
            error = result.expect_error()
            return Div(P(error.message, cls="text-sm text-destructive"))

        return Div(
            P("Feedback submitted successfully.", cls="text-sm text-green-600 font-medium"),
            cls="p-3 bg-green-50 rounded border border-green-200",
        )

    @rt("/api/teaching/review/{uid}/revision", methods=["POST"])
    @csrf_protected
    @require_role(UserRole.TEACHER, get_user_service)
    async def request_revision(request: Request, uid: str, current_user: Any = None) -> Any:
        """Request revision for a student submission with structured feedback.

        When exercise_uid is present, creates EntryReport + RevisedExercise
        atomically in a single transaction. Falls back to report-only when
        exercise_uid is absent.
        """
        from fasthtml.common import Div, P

        # Parse form data
        result = await parse_form_body(request, RequestRevisionRequest)
        if result.is_error:
            error = result.expect_error()
            return Div(P(error.message, cls="text-sm text-destructive"))

        form_data = result.value

        # Atomic path: EntryReport + RevisedExercise in one transaction
        if form_data.exercise_uid:
            # Parse feedback points from form arrays
            raw_form = await request.form()
            feedback_points: list[dict[str, str]] = []
            for i in range(form_data.fp_count):
                category = raw_form.get(f"fp_category_{i}", "")
                detail = raw_form.get(f"fp_detail_{i}", "")
                if category and detail:
                    feedback_points.append({"category": str(category), "detail": str(detail)})

            atomic_result = await teacher_review_service.request_revision_with_exercise(
                submission_uid=uid,
                teacher_uid=current_user.uid,
                notes=form_data.instructions,
                original_exercise_uid=form_data.exercise_uid,
                feedback_points=feedback_points,
                revision_rationale=form_data.revision_rationale,
            )
            if atomic_result.is_error:
                error = atomic_result.expect_error()
                return Div(P(error.message, cls="text-sm text-destructive"))

            re_uid = atomic_result.value["revised_exercise_uid"]
            return Div(
                P("Revision requested.", cls="text-sm text-amber-600 font-medium"),
                ButtonLink(
                    "View revision instructions →",
                    href=f"/revised-exercises/detail?uid={re_uid}",
                    cls=(ButtonT.ghost, "mt-1"),
                    size="sm",
                ),
                cls="p-3 bg-amber-50 rounded border border-amber-200",
            )

        # Fallback: report-only revision (no exercise context)
        revision_result = await teacher_review_service.request_revision(
            report_uid=uid,
            teacher_uid=current_user.uid,
            notes=form_data.instructions,
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
        request: Request, report_uid: str, current_user: Any = None
    ) -> Any:
        """Download the .md feedback file attached to an EntryReport.

        Owner-scoped, not just teacher-gated: ``get_report_file_path`` returns a
        path only for a report on a submission the caller shares an active group
        with — the same audience that may write the feedback. A report outside
        the caller's classroom, or one that does not exist, both return ``None``
        and yield the same real 404 (a denied read must not reach a client or
        cache as a 200 success).
        """
        from starlette.responses import Response

        def _not_found() -> Response:
            return Response("Report not found", status_code=404, media_type="text/plain")

        path_result = await teacher_review_service.get_report_file_path(
            report_uid, current_user.uid
        )
        if path_result.is_error or not path_result.value:
            return _not_found()

        file_path = pathlib.Path(path_result.value)
        if not file_path.exists():
            return _not_found()

        return FileResponse(
            str(file_path),
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="feedback-{report_uid[:12]}.md"'
            },
        )

    @rt("/api/teaching/review/{uid}/approve", methods=["POST"])
    @csrf_protected
    @require_role(UserRole.TEACHER, get_user_service)
    async def approve_report(request: Request, uid: str, current_user: Any = None) -> Any:
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
        request: Request, uid: str, current_user: Any = None
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
    @boundary_handler()
    async def get_review_panel(request: Request, uid: str, current_user: Any = None) -> Any:
        """Return inline review panel HTML fragment for the student detail tabbed view.

        Loaded by HTMX on first expand of a submission row. Returns:
        - Submission content
        - Feedback history (if any)
        - Action forms (if submission is actionable)
        """
        from ui.teaching.detail import render_review_panel_inline

        # get_submission_detail gates on shared-group access; a denied/missing
        # submission returns not-found. The feedback history below is this
        # student's private work, so it must not be read until that gate passes
        # — otherwise a teacher outside the classroom reads the reports while the
        # submission itself reads "unavailable". Empty panel either way, so a
        # denied read is indistinguishable from a missing one.
        detail_result = await teacher_review_service.get_submission_detail(
            submission_uid=uid, teacher_uid=current_user.uid
        )
        detail_value = detail_result.value if not detail_result.is_error else None
        if not detail_value:
            return render_review_panel_inline(uid, {}, [])

        if entry_report_service is None:
            history: list[Any] = []
        else:
            history_result = await entry_report_service.list_for_submission(uid)
            history = list(
                history_result.value if not history_result.is_error and history_result.value else []
            )

        return render_review_panel_inline(uid, dict(detail_value), history)

    @rt("/api/teaching/exercises", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_exercises(
        request: Request, current_user: Any = None
    ) -> Result[list[ExerciseWithSubmissionCounts]]:
        """Get teacher's exercises with submission counts."""
        return await teacher_review_service.get_exercises_with_submission_counts(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/exercises/{uid}/submissions", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_exercise_submissions(
        request: Request, uid: str, current_user: Any = None
    ) -> Result[list[SubmissionForExercise]]:
        """Get all submissions against an exercise (scoped to the teacher's classroom)."""
        return await teacher_review_service.get_submissions_for_exercise(
            exercise_uid=uid, teacher_uid=current_user.uid
        )

    @rt("/api/teaching/students", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_students(
        request: Request, current_user: Any = None
    ) -> Result[list[StudentSummaryItem]]:
        """Get students who shared work with the teacher."""
        return await teacher_review_service.get_students_summary(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/students/{uid}/submissions", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_student_submissions(
        request: Request, uid: str, current_user: Any = None
    ) -> Result[list[StudentSubmissionItem]]:
        """Get all submissions from a specific student."""
        return await teacher_review_service.get_student_submissions(
            teacher_uid=current_user.uid,
            student_uid=uid,
        )

    @rt("/api/teaching/groups", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_groups(
        request: Request, current_user: Any = None
    ) -> Result[list[TeacherGroupStats]]:
        """Get teacher's groups with member, exercise, and pending submission counts."""
        return await teacher_review_service.get_teacher_groups_with_stats(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/groups/{uid}", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_group_detail(
        request: Request, uid: str, current_user: Any = None
    ) -> Result[list[GroupMemberProgress]]:
        """Get members of a specific group with their submission progress."""
        return await teacher_review_service.get_group_detail(
            group_uid=uid,
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/submissions/{uid}/delete", methods=["POST"])
    @csrf_protected
    @require_role(UserRole.TEACHER, get_user_service)
    async def delete_submission(request: Request, uid: str, current_user: Any = None) -> Any:
        """Delete a student UserEntry (teacher action).

        Authorized when the teacher shares an active group with the entry's
        owner (see ``UserEntryService.delete_entry_as_teacher``). Hard-deletes
        the Neo4j node via cascade. Returns an empty response so HTMX removes
        the row.
        """
        from fasthtml.common import Div, P

        if not user_entry_service:
            return Div(P("Submission deletion not available.", cls="text-sm text-destructive"))

        result = await user_entry_service.delete_entry_as_teacher(uid, current_user.uid)
        if result.is_error:
            return Div(
                P(f"Failed to delete: {result.error}", cls="text-sm text-destructive"),
            )

        return ""

    logger.info("Teaching API routes registered")

    return []
