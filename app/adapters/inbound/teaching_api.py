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

from datetime import date
from typing import TYPE_CHECKING, Any

from fasthtml.common import Request

from adapters.inbound.auth.roles import UserRole, make_service_getter, require_role
from adapters.inbound.boundary import boundary_handler
from core.models.enums.entity_enums import ProcessorType
from core.models.enums.submissions_enums import ExerciseScope
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import TeacherReviewOperations

logger = get_logger(__name__)


def create_teaching_api_routes(
    app: Any,
    rt: Any,
    teacher_review_service: "TeacherReviewOperations",
    user_service: Any,
    exercises_service: Any = None,
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
    async def review_queue(request: Request, current_user: Any) -> Result[Any]:
        """Get teacher's pending review queue."""
        status_filter = request.query_params.get("status", None)
        return await teacher_review_service.get_review_queue(
            teacher_uid=current_user.uid,
            status_filter=status_filter,
        )

    @rt("/api/teaching/review/{uid}/report", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def submit_feedback(request: Request, uid: str, current_user: Any) -> Result[Any]:
        """Submit feedback for a student report."""
        body = await request.json()
        feedback = body.get("feedback", "")
        if not feedback:
            return Result.fail(Errors.validation("Feedback text is required", field="feedback"))

        return await teacher_review_service.submit_report(
            report_uid=uid,
            teacher_uid=current_user.uid,
            feedback=feedback,
        )

    @rt("/api/teaching/review/{uid}/revision", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def request_revision(request: Request, uid: str, current_user: Any) -> Result[Any]:
        """Request revision for a student report."""
        body = await request.json()
        notes = body.get("notes", "")
        if not notes:
            return Result.fail(Errors.validation("Revision notes are required", field="notes"))

        return await teacher_review_service.request_revision(
            report_uid=uid,
            teacher_uid=current_user.uid,
            notes=notes,
        )

    @rt("/api/teaching/review/{uid}/approve", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def approve_report(request: Request, uid: str, current_user: Any) -> Result[Any]:
        """Approve a student report."""
        return await teacher_review_service.approve_report(
            report_uid=uid,
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/review/{uid}", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_submission_detail(request: Request, uid: str, current_user: Any) -> Result[Any]:
        """Get full submission detail for teacher review.

        Returns submission content, student info, and linked exercise.
        Access-controlled: only succeeds if teacher has SHARES_WITH {role: 'teacher'} access.
        """
        return await teacher_review_service.get_submission_detail(
            submission_uid=uid,
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/exercises", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_exercises(request: Request, current_user: Any) -> Result[Any]:
        """Get teacher's exercises with submission counts."""
        return await teacher_review_service.get_exercises_with_submission_counts(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/exercises/{uid}/submissions", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_exercise_submissions(
        request: Request, uid: str, current_user: Any
    ) -> Result[Any]:
        """Get all submissions against an exercise."""
        return await teacher_review_service.get_submissions_for_exercise(exercise_uid=uid)

    @rt("/api/teaching/students", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_students(request: Request, current_user: Any) -> Result[Any]:
        """Get students who shared work with the teacher."""
        return await teacher_review_service.get_students_summary(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/students/{uid}/submissions", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_student_submissions(request: Request, uid: str, current_user: Any) -> Result[Any]:
        """Get all submissions from a specific student."""
        return await teacher_review_service.get_student_submissions(
            teacher_uid=current_user.uid,
            student_uid=uid,
        )

    @rt("/api/teaching/dashboard", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_dashboard_stats(request: Request, current_user: Any) -> Result[Any]:
        """Get at-a-glance stats for the teacher dashboard."""
        return await teacher_review_service.get_dashboard_stats(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/classes", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_classes(request: Request, current_user: Any) -> Result[Any]:
        """Get teacher's groups with member, exercise, and pending submission counts."""
        return await teacher_review_service.get_teacher_groups_with_stats(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/classes/{uid}", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_class_detail(request: Request, uid: str, current_user: Any) -> Result[Any]:
        """Get members of a specific class with their submission progress."""
        return await teacher_review_service.get_group_detail(
            group_uid=uid,
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/exercises", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler(success_status=201)
    async def create_teaching_exercise(request: Request, current_user: Any = None) -> Result[Any]:
        """Create a new exercise owned by the authenticated teacher."""
        if not exercises_service:
            return Result.fail(
                Errors.system(
                    "exercises_service not available", operation="create_teaching_exercise"
                )
            )

        body = await request.form()
        name = (body.get("name") or "").strip()
        instructions = (body.get("instructions") or "").strip()

        if not name:
            return Result.fail(Errors.validation("name is required", field="name"))
        if not instructions:
            return Result.fail(Errors.validation("instructions is required", field="instructions"))

        scope_str = body.get("scope") or "personal"
        try:
            scope = ExerciseScope(scope_str)
        except ValueError:
            return Result.fail(Errors.validation(f"Invalid scope: {scope_str}", field="scope"))

        group_uid = body.get("group_uid") or None
        if scope == ExerciseScope.ASSIGNED and not group_uid:
            return Result.fail(
                Errors.validation("group_uid is required for assigned exercises", field="group_uid")
            )

        due_date: date | None = None
        due_date_str = body.get("due_date") or ""
        if due_date_str:
            try:
                due_date = date.fromisoformat(due_date_str)
            except ValueError:
                return Result.fail(
                    Errors.validation("Invalid due_date format (use YYYY-MM-DD)", field="due_date")
                )

        processor_type_str = body.get("processor_type") or "llm"
        try:
            processor_type = ProcessorType(processor_type_str)
        except ValueError:
            processor_type = ProcessorType.LLM

        context_notes_raw = body.get("context_notes") or ""
        context_notes = [n.strip() for n in context_notes_raw.splitlines() if n.strip()]

        result = await exercises_service.create_exercise(
            user_uid=current_user.uid,
            name=name,
            instructions=instructions,
            model=body.get("model") or "claude-sonnet-4-6",
            scope=scope,
            group_uid=group_uid,
            due_date=due_date,
            processor_type=processor_type,
            context_notes=context_notes,
        )
        if result.is_error:
            return result  # type: ignore[no-any-return]
        return Result.ok(result.value.to_dto().to_dict())

    @rt("/api/teaching/exercises/{uid}", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def update_teaching_exercise(
        request: Request, uid: str, current_user: Any = None
    ) -> Result[Any]:
        """Update an existing exercise."""
        if not exercises_service:
            return Result.fail(
                Errors.system(
                    "exercises_service not available", operation="update_teaching_exercise"
                )
            )

        body = await request.form()

        name = (body.get("name") or "").strip() or None
        instructions = (body.get("instructions") or "").strip() or None
        model = body.get("model") or None

        context_notes: list[str] | None = None
        context_notes_raw = body.get("context_notes")
        if context_notes_raw is not None:
            context_notes = [n.strip() for n in context_notes_raw.splitlines() if n.strip()]

        result = await exercises_service.update_exercise(
            uid=uid,
            name=name,
            instructions=instructions,
            model=model,
            context_notes=context_notes,
        )
        if result.is_error:
            return result  # type: ignore[no-any-return]
        return Result.ok(result.value.to_dto().to_dict())

    logger.info("✅ Teaching API routes registered")
    return []
