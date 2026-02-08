"""
Report Projects API - Factory Pattern Routes
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
from core.models.report.report_project_request import (
    ReportFeedbackRequest,
    ReportProjectCreateRequest,
    ReportProjectUpdateRequest,
)
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


def create_report_projects_api_routes(
    app: Any,
    rt: Any,
    report_projects_service: Any,
    transcript_service: Any,
    report_feedback_service: Any,
    user_service: Any = None,
) -> list[Any]:
    """
    Create report projects API routes using factory pattern.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        report_projects_service: ReportProjectService instance
        transcript_service: TranscriptProcessor for entry lookup
        report_feedback_service: ReportFeedbackService for AI feedback
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
        service=report_projects_service,
        domain_name="report-projects",
        create_schema=ReportProjectCreateRequest,
        update_schema=ReportProjectUpdateRequest,
        uid_prefix="rp",
        scope=ContentScope.USER_OWNED,
        require_role=UserRole.TEACHER,
        user_service_getter=get_user_service_instance,
    )

    # Register all standard CRUD routes:
    # - POST /api/report-projects/create        (create)
    # - GET  /api/report-projects/get?uid=...   (get)
    # - POST /api/report-projects/update?uid=.. (update)
    # - POST /api/report-projects/delete?uid=.. (delete)
    # - GET  /api/report-projects/list          (list with pagination)
    crud_factory.register_routes(app, rt)

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================

    @rt("/api/report-projects/feedback", methods=["POST"])
    @require_teacher(get_user_service_instance)
    @boundary_handler()
    async def feedback(request: Request, current_user: Any = None) -> Result[Any]:
        """
        Generate AI feedback for an entry using a project.

        This is domain-specific and kept as a manual route because it:
        1. Involves complex coordination between services
        2. Has optional side effects (saving feedback to entry)
        3. Uses custom LLM parameters (temperature, max_tokens)

        Body (JSON):
        - entry_uid: Entry UID (required)
        - project_uid: Project UID (required)
        - temperature: Sampling temperature 0-1 (optional, default 0.7)
        - max_tokens: Max tokens to generate (optional, default 4000)
        - save_feedback: Whether to save to entry (optional, default true)

        Returns:
        - 200: Feedback generated
        - 400: Invalid input
        - 404: Entry or project not found
        - 503: Service not available
        """
        if not report_feedback_service:
            return Result.fail(
                Errors.system(
                    "Report feedback service not available", service="ReportFeedbackService"
                )
            )

        if not transcript_service:
            return Result.fail(
                Errors.system("Transcript service not available", service="TranscriptProcessor")
            )

        # Parse request body
        try:
            body = await request.json()
            feedback_request = ReportFeedbackRequest(**body)
        except Exception as e:
            return Result.fail(Errors.validation(f"Invalid request body: {e}", field="body"))

        # Get entry and project
        entry_result = await transcript_service.get_journal(feedback_request.entry_uid)
        if entry_result.is_error or not entry_result.value:
            return Result.fail(Errors.not_found("Entry", feedback_request.entry_uid))

        project_result = await report_projects_service.get_project(feedback_request.project_uid)
        if project_result.is_error or not project_result.value:
            return Result.fail(Errors.not_found("Report project", feedback_request.project_uid))

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

        # Optionally save to entry
        if feedback_request.save_feedback:
            from core.models.journal import journal_dto_to_pure, journal_pure_to_dto

            dto = journal_pure_to_dto(entry)
            dto.project_uid = feedback_request.project_uid
            dto.feedback = feedback_text
            dto.feedback_generated_at = datetime.now()

            updated_entry = journal_dto_to_pure(dto)
            update_result = await transcript_service.update_journal(updated_entry)

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

    logger.info("Report projects API routes registered (Factory pattern)")
    return []
