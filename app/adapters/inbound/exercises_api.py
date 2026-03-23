"""
Exercises API - Domain-Specific Routes
========================================

CRUD routes are config-driven via CRUDRouteConfig in exercises_routes.py.
This file contains only domain-specific manual routes (report generation,
curriculum linking).
"""

from typing import Any, cast

from fasthtml.common import Request

from adapters.inbound.auth import make_service_getter, require_authenticated_user, require_teacher
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.form_helpers import parse_json_body
from core.models.exercises.exercise_request import (
    ExerciseKnowledgeRequest,
    ReportGenerateRequest,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


def create_exercises_api_routes(
    app: Any,
    rt: Any,
    exercises_service: Any,
    transcript_service: Any,
    submission_report_service: Any,
    user_service: Any = None,
) -> list[Any]:
    """
    Create exercises API routes using factory pattern.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        exercises_service: ExerciseService instance
        transcript_service: ContentEnrichmentService for entry lookup
        submission_report_service: SubmissionReportService for AI reports
        user_service: UserService for role checks
    """

    get_user_service = make_service_getter(user_service)

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================

    @rt("/api/exercises/report", methods=["POST"])
    @require_teacher(get_user_service)
    @boundary_handler()
    async def generate_report(request: Request, current_user: Any = None) -> Result[Any]:
        """
        Generate AI report for an entry using an exercise.

        Creates a SUBMISSION_REPORT entity (processor_type=LLM) linked to the
        submission via REPORT_FOR — symmetric with human teacher reports.

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
        if not submission_report_service:
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
        parsed = await parse_json_body(request, ReportGenerateRequest)
        if parsed.is_error:
            return parsed  # type: ignore[return-value]
        report_request = parsed.value

        # Get entry and exercise
        entry_result = await transcript_service.get(report_request.entry_uid)
        if entry_result.is_error:
            return Result.fail(Errors.not_found("Entry", report_request.entry_uid))

        exercise_result = await exercises_service.get_exercise(report_request.project_uid)
        if exercise_result.is_error:
            return Result.fail(Errors.not_found("Exercise", report_request.project_uid))

        entry = entry_result.value
        exercise = exercise_result.value

        # Generate report — creates SUBMISSION_REPORT entity + REPORT_FOR relationship
        report_result = await submission_report_service.generate_report(
            entry=entry,
            exercise=exercise,
            user_uid=user_uid,
            temperature=report_request.temperature,
            max_tokens=report_request.max_tokens,
        )

        if report_result.is_error:
            logger.error(f"Failed to generate report: {report_result.error}")
            return Result.fail(report_result)

        report_entity = report_result.value

        return Result.ok(
            {
                "report_uid": report_entity.uid,
                "entry_uid": report_request.entry_uid,
                "project_uid": report_request.project_uid,
                "report_content": report_entity.report_content,
            }
        )

    # ========================================================================
    # CURRICULUM LINKING ROUTES
    # ========================================================================

    @rt("/api/exercises/require-knowledge", methods=["POST"])
    @require_teacher(get_user_service)
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
        result = await parse_json_body(request, ExerciseKnowledgeRequest)
        if result.is_error:
            return result  # type: ignore[return-value]
        req = result.value

        return cast(
            "Result[Any]",
            await exercises_service.link_to_curriculum(req.exercise_uid, req.curriculum_uid),
        )

    @rt("/api/exercises/unrequire-knowledge", methods=["POST"])
    @require_teacher(get_user_service)
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
        result = await parse_json_body(request, ExerciseKnowledgeRequest)
        if result.is_error:
            return result  # type: ignore[return-value]
        req = result.value

        return cast(
            "Result[Any]",
            await exercises_service.unlink_from_curriculum(req.exercise_uid, req.curriculum_uid),
        )

    @rt("/api/exercises/required-knowledge", methods=["GET"])
    @require_teacher(get_user_service)
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
    @require_teacher(get_user_service)
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
