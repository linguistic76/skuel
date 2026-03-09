"""
Exercises API - Factory Pattern Routes
=========================================

Provides:
- Standard CRUD operations via CRUDRouteFactory
- Domain-specific feedback generation (manual route)
"""

from typing import Any, cast

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user, require_teacher
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories import CRUDRouteFactory
from core.models.enums import ContentScope
from core.models.enums.user_enums import UserRole
from core.models.exercises.exercise_request import (
    ExerciseCreateRequest,
    ExerciseUpdateRequest,
    FeedbackGenerateRequest,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


def create_exercises_api_routes(
    app: Any,
    rt: Any,
    exercises_service: Any,
    transcript_service: Any,
    report_feedback_service: Any,
    user_service: Any = None,
) -> list[Any]:
    """
    Create exercises API routes using factory pattern.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        exercises_service: ExerciseService instance
        transcript_service: ContentEnrichmentService for entry lookup
        report_feedback_service: SubmissionReportService for AI reports
        user_service: UserService for role checks
    """

    # Named function for role decorator (SKUEL012: no lambdas)
    def get_user_service_instance():
        """Get user service for teacher role checks."""
        return user_service

    # ========================================================================
    # STANDARD CRUD ROUTES (Factory-Generated)
    # ========================================================================

    crud_factory = CRUDRouteFactory(
        service=exercises_service,
        domain_name="exercises",
        create_schema=ExerciseCreateRequest,
        update_schema=ExerciseUpdateRequest,
        uid_prefix="exercise",
        scope=ContentScope.USER_OWNED,
        require_role=UserRole.TEACHER,
        user_service_getter=get_user_service_instance,
    )

    # Register all standard CRUD routes:
    # - POST /api/exercises/create (create)
    # - GET /api/exercises/get?uid=... (get)
    # - POST /api/exercises/update?uid=.. (update)
    # - POST /api/exercises/delete?uid=.. (delete)
    # - GET /api/exercises/list (list with pagination)
    crud_factory.register_routes(app, rt)

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================

    @rt("/api/exercises/report", methods=["POST"])
    @require_teacher(get_user_service_instance)
    @boundary_handler()
    async def feedback(request: Request, current_user: Any = None) -> Result[Any]:
        """
        Generate AI feedback for an entry using an exercise.

        Creates a SUBMISSION_REPORT entity (processor_type=LLM) linked to the
        submission via REPORT_FOR — symmetric with human teacher feedback.

        Body (JSON):
        - entry_uid: Entry UID (required)
        - project_uid: Exercise UID (required)
        - temperature: Sampling temperature 0-1 (optional, default 0.7)
        - max_tokens: Max tokens to generate (optional, default 4000)

        Returns:
        - 200: SubmissionReport entity created {report_uid, entry_uid, project_uid, report_content}
        - 400: Invalid input
        - 404: Entry or exercise not found
        - 503: Service not available
        """
        if not report_feedback_service:
            return Result.fail(
                Errors.system("Report service not available", service="SubmissionReportService")
            )

        if not transcript_service:
            return Result.fail(
                Errors.system(
                    "Transcript service not available",
                    service="ContentEnrichmentService",
                )
            )

        user_uid = require_authenticated_user(request)

        # Parse request body
        try:
            body = await request.json()
            feedback_request = FeedbackGenerateRequest(**body)
        except Exception as e:
            return Result.fail(Errors.validation(f"Invalid request body: {e}", field="body"))

        # Get entry and exercise
        entry_result = await transcript_service.get(feedback_request.entry_uid)
        if entry_result.is_error:
            return Result.fail(Errors.not_found("Entry", feedback_request.entry_uid))

        exercise_result = await exercises_service.get_exercise(feedback_request.project_uid)
        if exercise_result.is_error:
            return Result.fail(Errors.not_found("Exercise", feedback_request.project_uid))

        entry = entry_result.value
        exercise = exercise_result.value

        # Generate feedback — creates SUBMISSION_REPORT entity + REPORT_FOR relationship
        feedback_result = await report_feedback_service.generate_feedback(
            entry=entry,
            exercise=exercise,
            user_uid=user_uid,
            temperature=feedback_request.temperature,
            max_tokens=feedback_request.max_tokens,
        )

        if feedback_result.is_error:
            logger.error(f"Failed to generate feedback: {feedback_result.error}")
            return Result.fail(feedback_result.expect_error())

        feedback_entity = feedback_result.value

        return Result.ok(
            {
                "report_uid": feedback_entity.uid,
                "entry_uid": feedback_request.entry_uid,
                "project_uid": feedback_request.project_uid,
                "report_content": feedback_entity.report_content,
            }
        )

    # ========================================================================
    # CURRICULUM LINKING ROUTES
    # ========================================================================

    @rt("/api/exercises/require-knowledge", methods=["POST"])
    @require_teacher(get_user_service_instance)
    @boundary_handler()
    async def require_knowledge(request: Request, current_user: Any = None) -> Result[Any]:
        """
        Link an exercise to a curriculum KU via REQUIRES_KNOWLEDGE.

        Body (JSON):
        - exercise_uid: Exercise UID (required)
        - curriculum_uid: Curriculum KU UID (required)

        Returns:
        - 200: Relationship created
        - 404: Exercise or curriculum KU not found
        """
        body = await request.json()
        exercise_uid = body.get("exercise_uid")
        curriculum_uid = body.get("curriculum_uid")

        if not exercise_uid or not curriculum_uid:
            return Result.fail(
                Errors.validation(
                    "exercise_uid and curriculum_uid are required",
                    field="body",
                )
            )

        return cast(
            "Result[Any]", await exercises_service.link_to_curriculum(exercise_uid, curriculum_uid)
        )

    @rt("/api/exercises/unrequire-knowledge", methods=["POST"])
    @require_teacher(get_user_service_instance)
    @boundary_handler()
    async def unrequire_knowledge(request: Request, current_user: Any = None) -> Result[Any]:
        """
        Remove REQUIRES_KNOWLEDGE relationship between exercise and curriculum KU.

        Body (JSON):
        - exercise_uid: Exercise UID (required)
        - curriculum_uid: Curriculum KU UID (required)

        Returns:
        - 200: Relationship removed
        - 404: Relationship not found
        """
        body = await request.json()
        exercise_uid = body.get("exercise_uid")
        curriculum_uid = body.get("curriculum_uid")

        if not exercise_uid or not curriculum_uid:
            return Result.fail(
                Errors.validation(
                    "exercise_uid and curriculum_uid are required",
                    field="body",
                )
            )

        return cast(
            "Result[Any]",
            await exercises_service.unlink_from_curriculum(exercise_uid, curriculum_uid),
        )

    @rt("/api/exercises/required-knowledge", methods=["GET"])
    @require_teacher(get_user_service_instance)
    @boundary_handler()
    async def get_required_knowledge(request: Request, current_user: Any = None) -> Result[Any]:
        """
        Get all curriculum KUs required by an exercise.

        Query params:
        - uid: Exercise UID (required)

        Returns:
        - 200: List of required curriculum KUs
        """
        uid = request.query_params.get("uid")
        if not uid:
            return Result.fail(Errors.validation("uid is required", field="uid"))

        return cast("Result[Any]", await exercises_service.get_required_knowledge(uid))

    @rt("/api/exercises/for-curriculum", methods=["GET"])
    @require_teacher(get_user_service_instance)
    @boundary_handler()
    async def get_exercises_for_curriculum(
        request: Request, current_user: Any = None
    ) -> Result[Any]:
        """
        Get all exercises that require a specific curriculum KU.

        Query params:
        - curriculum_uid: Curriculum KU UID (required)

        Returns:
        - 200: List of exercises requiring this curriculum KU
        """
        curriculum_uid = request.query_params.get("curriculum_uid")
        if not curriculum_uid:
            return Result.fail(
                Errors.validation("curriculum_uid is required", field="curriculum_uid")
            )

        return cast(
            "Result[Any]", await exercises_service.get_exercises_for_curriculum(curriculum_uid)
        )

    logger.info("Exercises API routes registered (Factory pattern + curriculum linking)")
    return []
