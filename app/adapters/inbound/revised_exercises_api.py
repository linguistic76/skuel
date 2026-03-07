"""
Revised Exercises API - Five-Phase Learning Loop
==================================================

API routes for RevisedExercise CRUD operations. Teachers create revised
exercises in response to SubmissionFeedback to guide student revisions.
"""

from typing import Any

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user, require_teacher
from adapters.inbound.boundary import boundary_handler
from core.models.curriculum.revised_exercise_request import (
    RevisedExerciseCreateRequest,
    RevisedExerciseUpdateRequest,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


def create_revised_exercises_api_routes(
    app: Any,
    rt: Any,
    revised_exercise_service: Any,
    user_service: Any = None,
) -> list[Any]:
    """Create revised exercises API routes."""

    def get_user_service_instance():
        """Get user service for teacher role checks."""
        return user_service

    # ========================================================================
    # CREATE
    # ========================================================================

    @rt("/api/revised-exercises/create", methods=["POST"])
    @require_teacher(get_user_service_instance)
    @boundary_handler(success_status=201)
    async def create_revised_exercise(
        request: Request, current_user: Any = None
    ) -> Result[Any]:
        """Create a new RevisedExercise."""
        teacher_uid = require_authenticated_user(request)

        try:
            body = await request.json()
            req = RevisedExerciseCreateRequest(**body)
        except Exception as e:
            return Result.fail(Errors.validation(f"Invalid request body: {e}", field="body"))

        return await revised_exercise_service.create_revised_exercise(
            teacher_uid=teacher_uid,
            original_exercise_uid=req.original_exercise_uid,
            feedback_uid=req.feedback_uid,
            student_uid=req.student_uid,
            instructions=req.instructions,
            title=req.title,
            model=req.model,
            context_notes=req.context_notes,
            feedback_points_addressed=req.feedback_points_addressed,
            revision_rationale=req.revision_rationale,
        )

    # ========================================================================
    # READ
    # ========================================================================

    @rt("/api/revised-exercises/get", methods=["GET"])
    @require_teacher(get_user_service_instance)
    @boundary_handler()
    async def get_revised_exercise(
        request: Request, current_user: Any = None
    ) -> Result[Any]:
        """Get a RevisedExercise by UID."""
        uid = request.query_params.get("uid")
        if not uid:
            return Result.fail(Errors.validation("uid is required", field="uid"))
        return await revised_exercise_service.get_revised_exercise(uid)

    @rt("/api/revised-exercises/list", methods=["GET"])
    @require_teacher(get_user_service_instance)
    @boundary_handler()
    async def list_revised_exercises(
        request: Request, current_user: Any = None
    ) -> Result[Any]:
        """List revised exercises for the current teacher."""
        teacher_uid = require_authenticated_user(request)
        return await revised_exercise_service.list_for_teacher(teacher_uid)

    @rt("/api/revised-exercises/for-student", methods=["GET"])
    @require_teacher(get_user_service_instance)
    @boundary_handler()
    async def list_for_student(
        request: Request, current_user: Any = None
    ) -> Result[Any]:
        """List revised exercises targeting a specific student (scoped to requesting teacher)."""
        teacher_uid = require_authenticated_user(request)
        student_uid = request.query_params.get("student_uid")
        if not student_uid:
            return Result.fail(
                Errors.validation("student_uid is required", field="student_uid")
            )
        return await revised_exercise_service.list_for_student(
            student_uid, teacher_uid=teacher_uid
        )

    @rt("/api/revised-exercises/chain", methods=["GET"])
    @require_teacher(get_user_service_instance)
    @boundary_handler()
    async def get_revision_chain(
        request: Request, current_user: Any = None
    ) -> Result[Any]:
        """Get the revision chain for an original exercise."""
        exercise_uid = request.query_params.get("exercise_uid")
        if not exercise_uid:
            return Result.fail(
                Errors.validation("exercise_uid is required", field="exercise_uid")
            )
        return await revised_exercise_service.get_revision_chain(exercise_uid)

    # ========================================================================
    # UPDATE
    # ========================================================================

    @rt("/api/revised-exercises/update", methods=["POST"])
    @require_teacher(get_user_service_instance)
    @boundary_handler()
    async def update_revised_exercise(
        request: Request, current_user: Any = None
    ) -> Result[Any]:
        """Update a RevisedExercise."""
        uid = request.query_params.get("uid")
        if not uid:
            return Result.fail(Errors.validation("uid is required", field="uid"))

        try:
            body = await request.json()
            req = RevisedExerciseUpdateRequest(**body)
        except Exception as e:
            return Result.fail(Errors.validation(f"Invalid request body: {e}", field="body"))

        return await revised_exercise_service.update_revised_exercise(
            uid=uid,
            instructions=req.instructions,
            title=req.title,
            model=req.model,
            context_notes=req.context_notes,
            feedback_points_addressed=req.feedback_points_addressed,
            revision_rationale=req.revision_rationale,
        )

    # ========================================================================
    # STUDENT-FACING (no role decorator — authenticated users only)
    # ========================================================================

    @rt("/api/revised-exercises/my-revisions", methods=["GET"])
    @boundary_handler()
    async def my_revisions(request: Request) -> Result[Any]:
        """List revised exercises targeting the current user (student view)."""
        user_uid = require_authenticated_user(request)
        return await revised_exercise_service.list_for_student(user_uid)

    @rt("/api/revised-exercises/view", methods=["GET"])
    @boundary_handler()
    async def view_revised_exercise(request: Request) -> Result[Any]:
        """View a RevisedExercise (student or owning teacher)."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid")
        if not uid:
            return Result.fail(Errors.validation("uid is required", field="uid"))
        result = await revised_exercise_service.get_revised_exercise(uid)
        if result.is_error:
            return result
        entity = result.value
        # Ownership check: student_uid OR user_uid (teacher/owner)
        if entity.student_uid != user_uid and entity.user_uid != user_uid:
            return Result.fail(
                Errors.not_found(resource="RevisedExercise", identifier=uid)
            )
        return result

    # ========================================================================
    # DELETE
    # ========================================================================

    @rt("/api/revised-exercises/delete", methods=["POST"])
    @require_teacher(get_user_service_instance)
    @boundary_handler()
    async def delete_revised_exercise(
        request: Request, current_user: Any = None
    ) -> Result[Any]:
        """Delete a RevisedExercise."""
        uid = request.query_params.get("uid")
        if not uid:
            return Result.fail(Errors.validation("uid is required", field="uid"))
        return await revised_exercise_service.delete_revised_exercise(uid)

    logger.info("Revised Exercises API routes registered (five-phase learning loop)")
    return []
