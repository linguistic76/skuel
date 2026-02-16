"""
Assignments API - Factory Pattern Routes
=============================================

Provides:
- Standard CRUD operations via CRUDRouteFactory
- Domain-specific feedback generation (manual route)
"""

from datetime import datetime
from typing import Any

from fasthtml.common import Request

from core.auth import require_teacher
from core.infrastructure.routes import CRUDRouteFactory
from core.models.enums import ContentScope
from core.models.enums.user_enums import UserRole
from core.models.ku import KuFeedbackGenerateRequest
from core.models.ku.assignment_request import (
    AssignmentCreateRequest,
    AssignmentUpdateRequest,
)
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


def create_assignments_api_routes(
    app: Any,
    rt: Any,
    assignments_service: Any,
    transcript_service: Any,
    report_feedback_service: Any,
    user_service: Any = None,
) -> list[Any]:
    """
    Create assignments API routes using factory pattern.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        assignments_service: AssignmentService instance
        transcript_service: TranscriptProcessor for entry lookup
        report_feedback_service: KuFeedbackService for AI feedback
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
        service=assignments_service,
        domain_name="assignments",
        create_schema=AssignmentCreateRequest,
        update_schema=AssignmentUpdateRequest,
        uid_prefix="assignment",
        scope=ContentScope.USER_OWNED,
        require_role=UserRole.TEACHER,
        user_service_getter=get_user_service_instance,
    )

    # Register all standard CRUD routes:
    # - POST /api/assignments/create        (create)
    # - GET  /api/assignments/get?uid=...   (get)
    # - POST /api/assignments/update?uid=.. (update)
    # - POST /api/assignments/delete?uid=.. (delete)
    # - GET  /api/assignments/list          (list with pagination)
    crud_factory.register_routes(app, rt)

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================

    @rt("/api/assignments/feedback", methods=["POST"])
    @require_teacher(get_user_service_instance)
    @boundary_handler()
    async def feedback(request: Request, current_user: Any = None) -> Result[Any]:
        """
        Generate AI feedback for an entry using an assignment.

        This is domain-specific and kept as a manual route because it:
        1. Involves complex coordination between services
        2. Has optional side effects (saving feedback to entry)
        3. Uses custom LLM parameters (temperature, max_tokens)

        Body (JSON):
        - entry_uid: Entry UID (required)
        - project_uid: Assignment UID (required)
        - temperature: Sampling temperature 0-1 (optional, default 0.7)
        - max_tokens: Max tokens to generate (optional, default 4000)
        - save_feedback: Whether to save to entry (optional, default true)

        Returns:
        - 200: Feedback generated
        - 400: Invalid input
        - 404: Entry or assignment not found
        - 503: Service not available
        """
        if not report_feedback_service:
            return Result.fail(
                Errors.system("Feedback service not available", service="KuFeedbackService")
            )

        if not transcript_service:
            return Result.fail(
                Errors.system("Transcript service not available", service="TranscriptProcessor")
            )

        # Parse request body
        try:
            body = await request.json()
            feedback_request = KuFeedbackGenerateRequest(**body)
        except Exception as e:
            return Result.fail(Errors.validation(f"Invalid request body: {e}", field="body"))

        # Get entry and project
        entry_result = await transcript_service.get(feedback_request.entry_uid)
        if entry_result.is_error:
            return Result.fail(Errors.not_found("Entry", feedback_request.entry_uid))

        project_result = await assignments_service.get_project(feedback_request.project_uid)
        if project_result.is_error:
            return Result.fail(Errors.not_found("Assignment", feedback_request.project_uid))

        entry = entry_result.value
        project = project_result.value

        # Generate feedback
        feedback_result = await report_feedback_service.generate_feedback(
            entry=entry,
            project=project,
            temperature=feedback_request.temperature,
            max_tokens=feedback_request.max_tokens,
        )

        if feedback_result.is_error:
            logger.error(f"Failed to generate feedback: {feedback_result.error}")
            return Result.fail(feedback_result)

        feedback_text = feedback_result.value

        # Optionally save feedback to the submission
        if feedback_request.save_feedback:
            update_result = await transcript_service.update(
                feedback_request.entry_uid,
                {
                    "project_uid": feedback_request.project_uid,
                    "feedback": feedback_text,
                    "feedback_generated_at": datetime.now().isoformat(),
                },
            )

            if update_result.is_error:
                logger.warning(f"Generated feedback but failed to save: {update_result.error}")

        return Result.ok(
            {
                "entry_uid": feedback_request.entry_uid,
                "project_uid": feedback_request.project_uid,
                "feedback": feedback_text,
                "generated_at": datetime.now().isoformat(),
                "saved": feedback_request.save_feedback,
            }
        )

    logger.info("Assignments API routes registered (Factory pattern)")
    return []
