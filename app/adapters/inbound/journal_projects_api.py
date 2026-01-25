"""
Journal Projects API - Factory Pattern Migration
=================================================

Migrated from legacy routes to factory pattern following tasks_api.py pilot.

Provides:
- Standard CRUD operations via CRUDRouteFactory
- Domain-specific feedback generation (manual route)

Legacy file: routes/api/journal_project_routes.py (389 lines)
Modern file: This file (~80 lines, 80% reduction)
"""

from datetime import datetime
from typing import Any

from fasthtml.common import Request

from core.infrastructure.routes import CRUDRouteFactory
from core.models.enums import ContentScope
from core.models.journal.journal_project_request import (
    JournalFeedbackRequest,
    JournalProjectCreateRequest,
    JournalProjectUpdateRequest,
)
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


def create_journal_projects_api_routes(
    app: Any,
    rt: Any,
    journal_projects_service: Any,
    journals_service: Any,
    journal_feedback_service: Any,
) -> list[Any]:
    """
    Create journal projects API routes using factory pattern.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        journal_projects_service: JournalProjectService instance
        journals_service: JournalsService for entry lookup
        journal_feedback_service: JournalFeedbackService for AI feedback
    """

    # ========================================================================
    # STANDARD CRUD ROUTES (Factory-Generated)
    # ========================================================================

    crud_factory = CRUDRouteFactory(
        service=journal_projects_service,
        domain_name="journal-projects",
        create_schema=JournalProjectCreateRequest,
        update_schema=JournalProjectUpdateRequest,
        uid_prefix="journal_project",
        scope=ContentScope.USER_OWNED,
    )

    # Register all standard CRUD routes:
    # - POST /api/journal-projects/create        (create)
    # - GET  /api/journal-projects/get?uid=...   (get)
    # - POST /api/journal-projects/update?uid=.. (update)
    # - POST /api/journal-projects/delete?uid=.. (delete)
    # - GET  /api/journal-projects/list          (list with pagination)
    crud_factory.register_routes(app, rt)

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================

    @rt("/api/journal-projects/feedback", methods=["POST"])
    @boundary_handler()
    async def feedback(request: Request) -> Result[Any]:
        """
        Generate AI feedback for a journal entry using a project.

        This is domain-specific and kept as a manual route because it:
        1. Involves complex coordination between services
        2. Has optional side effects (saving feedback to entry)
        3. Uses custom LLM parameters (temperature, max_tokens)

        Body (JSON):
        - entry_uid: Journal entry UID (required)
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
        if not journal_feedback_service:
            return Result.fail(
                Errors.system(
                    "Journal feedback service not available", service="JournalFeedbackService"
                )
            )

        if not journals_service:
            return Result.fail(
                Errors.system("Journals service not available", service="JournalsService")
            )

        # Parse request body
        try:
            body = await request.json()
            feedback_request = JournalFeedbackRequest(**body)
        except Exception as e:
            return Result.fail(Errors.validation(f"Invalid request body: {e}", field="body"))

        # Get entry and project
        entry_result = await journals_service.get_journal(feedback_request.entry_uid)
        if entry_result.is_error or not entry_result.value:
            return Result.fail(Errors.not_found("Journal entry", feedback_request.entry_uid))

        project_result = await journal_projects_service.get_project(feedback_request.project_uid)
        if project_result.is_error or not project_result.value:
            return Result.fail(Errors.not_found("Journal project", feedback_request.project_uid))

        entry = entry_result.value
        project = project_result.value

        # Generate feedback
        feedback_result = await journal_feedback_service.generate_feedback(
            entry=entry,
            project=project,
            temperature=feedback_request.temperature,
            max_tokens=feedback_request.max_tokens,
        )

        if feedback_result.is_error:
            logger.error(f"Failed to generate feedback: {feedback_result.error}")
            return feedback_result

        feedback_text = feedback_result.value

        # Optionally save to entry
        if feedback_request.save_feedback:
            from core.models.journal import journal_dto_to_pure, journal_pure_to_dto

            dto = journal_pure_to_dto(entry)
            dto.project_uid = feedback_request.project_uid
            dto.feedback = feedback_text
            dto.feedback_generated_at = datetime.now()

            updated_entry = journal_dto_to_pure(dto)
            update_result = await journals_service.update_journal(updated_entry)

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

    logger.info("✅ Journal projects API routes registered (Factory pattern)")
    return []
