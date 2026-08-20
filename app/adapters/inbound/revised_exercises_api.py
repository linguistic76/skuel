"""
Revised Exercises API - Four-Phase Learning Loop
==================================================

Domain-specific API routes for RevisedExercise operations. CRUD routes
(create, get, list, update, delete) are handled by CRUDRouteFactory.

Remaining routes:
- list_for_student: Teacher-scoped listing by student
- get_revision_chain: Revision chain for an exercise
- my_revisions: Student-facing listing
- view_revised_exercise: Student/teacher ownership-checked view
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Request

from adapters.inbound.auth import make_service_getter, require_authenticated_user, require_teacher
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.result_helpers import require_found
from core.models.exercises.revised_exercise import RevisedExercise
from core.ports.query_types import RevisionChainResult
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.revised_exercises.revised_exercise_service import RevisedExerciseService

logger = get_logger(__name__)


def create_revised_exercises_api_routes(
    app: Any,
    rt: Any,
    revised_exercise_service: "RevisedExerciseService",
    user_service: Any = None,
) -> list[Any]:
    """Create revised exercises domain-specific API routes."""

    get_user_service = make_service_getter(user_service)

    # ========================================================================
    # TEACHER-FACING (domain-specific queries)
    # ========================================================================

    @rt("/api/revised-exercises/for-student", methods=["GET"])
    @require_teacher(get_user_service)
    @boundary_handler()
    async def list_for_student(
        request: Request, current_user: Any = None
    ) -> Result[list[RevisedExercise]]:
        """List revised exercises targeting a specific student (scoped to requesting teacher)."""
        teacher_uid = current_user.uid
        student_uid = request.query_params.get("student_uid")
        if not student_uid:
            return Result.fail(Errors.validation("student_uid is required", field="student_uid"))
        return await revised_exercise_service.list_for_student(student_uid, teacher_uid=teacher_uid)

    @rt("/api/revised-exercises/chain", methods=["GET"])
    @require_teacher(get_user_service)
    @boundary_handler()
    async def get_revision_chain(
        request: Request, current_user: Any = None
    ) -> Result[list[RevisionChainResult]]:
        """Revision chain for an original exercise, scoped to the teacher's classrooms."""
        exercise_uid = request.query_params.get("exercise_uid")
        if not exercise_uid:
            return Result.fail(Errors.validation("exercise_uid is required", field="exercise_uid"))
        return await revised_exercise_service.get_revision_chain(
            exercise_uid,
            teacher_uid=current_user.uid,
            student_uid=request.query_params.get("student_uid"),
        )

    # ========================================================================
    # STUDENT-FACING (no role decorator — authenticated users only)
    # ========================================================================

    @rt("/api/revised-exercises/my-revisions", methods=["GET"])
    @boundary_handler()
    async def my_revisions(request: Request) -> Result[list[RevisedExercise]]:
        """List revised exercises targeting the current user (student view)."""
        user_uid = require_authenticated_user(request)
        return await revised_exercise_service.list_for_student(user_uid)

    @rt("/api/revised-exercises/view", methods=["GET"])
    @boundary_handler()
    async def view_revised_exercise(request: Request) -> Result[RevisedExercise | None]:
        """View a RevisedExercise (student or owning teacher)."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid")
        if not uid:
            return Result.fail(Errors.validation("uid is required", field="uid"))
        found = require_found(
            await revised_exercise_service.get(uid),
            "RevisedExercise",
            uid,
        )
        if found.is_error:
            return Result.fail(found)
        entity = found.value
        # Ownership check: student_uid OR user_uid (teacher/owner)
        if entity.student_uid != user_uid and entity.user_uid != user_uid:
            return Result.fail(Errors.not_found(resource="RevisedExercise", identifier=uid))
        return Result.ok(entity)

    logger.info("Revised Exercises API routes registered (four-phase learning loop)")

    return []
