"""
Journal Project API Routes (FastHTML-Aligned)
==============================================

REST API endpoints for journal projects CRUD and feedback generation following FastHTML best practices.

Following SKUEL principles:
- Transparent: User controls instructions and model
- Simple: Clean CRUD operations
- User-initiated: No automatic suggestions

FastHTML Conventions Applied:
- Query parameters over path parameters
- Function names define routes
- Type hints for automatic parameter extraction
- POST for all mutations
"""

from datetime import datetime
from typing import Any

from core.models.shared_enums import Domain
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger

logger = get_logger(__name__)


def create_journal_project_routes(app, services):
    """Create and register journal project routes (FastHTML-aligned)"""

    @app.post("/journal-projects/create")
    @boundary_handler()
    async def create(request) -> Any:
        """
        Create a new journal project.

        Body (form or JSON):
        - user_uid: User UID (required)
        - name: Project name (required)
        - instructions: LLM instructions (required)
        - model: LLM model (optional, defaults to claude-3-5-sonnet)
        - context_notes: Context notes as newline-separated string (optional)
        - domain: Domain categorization (optional)

        Returns:
        - 201: Project created
        - 400: Invalid input
        - 503: Service not available
        """
        if not services.journal_projects:
            return {"error": "Journal projects service not available"}, 503

        try:
            # Parse form data
            form_data = await request.form()

            # Parse context notes (newline-separated)
            context_notes_str = form_data.get("context_notes", "")
            context_notes = [line.strip() for line in context_notes_str.split("\n") if line.strip()]

            # Parse domain
            domain_str = form_data.get("domain")
            domain = Domain(domain_str) if domain_str else None

            # Create project
            result = await services.journal_projects.create_project(
                user_uid=form_data.get("user_uid"),
                name=form_data.get("name"),
                instructions=form_data.get("instructions"),
                model=form_data.get("model", "claude-3-5-sonnet-20241022"),
                context_notes=context_notes if context_notes else None,
                domain=domain,
            )

            if result.is_error:
                logger.error(f"Failed to create project: {result.error}")
                return {"error": "Failed to create project", "details": str(result.error)}, 500

            project = result.value

            return {
                "uid": project.uid,
                "name": project.name,
                "instructions": project.instructions,
                "model": project.model,
                "context_notes": project.context_notes,
                "domain": project.domain.value if project.domain else None,
                "is_active": project.is_active,
                "created_at": project.created_at.isoformat(),
            }, 201

        except Exception as e:
            logger.error(f"Error creating project: {e}")
            return {"error": "Failed to create project", "details": str(e)}, 500

    @app.get("/journal-projects/list")
    @boundary_handler()
    async def list_projects(request) -> Any:
        """
        List user's journal projects.

        Query params:
        - user_uid: User UID (required)
        - active_only: true/false (optional, defaults to true)

        Returns:
        - 200: List of projects
        - 400: Missing user_uid
        - 503: Service not available
        """
        if not services.journal_projects:
            return {"error": "Journal projects service not available"}, 503

        params = dict(request.query_params)
        user_uid = params.get("user_uid")

        if not user_uid:
            return {"error": "user_uid is required"}, 400

        active_only = params.get("active_only", "true").lower() == "true"

        result = await services.journal_projects.list_user_projects(
            user_uid=user_uid, active_only=active_only
        )

        if result.is_error:
            logger.error(f"Failed to list projects: {result.error}")
            return {"error": "Failed to list projects"}, 500

        projects = result.value

        return {
            "projects": [
                {
                    "uid": p.uid,
                    "name": p.name,
                    "instructions": p.instructions,
                    "model": p.model,
                    "context_notes": p.context_notes,
                    "domain": p.domain.value if p.domain else None,
                    "is_active": p.is_active,
                    "created_at": p.created_at.isoformat(),
                    "updated_at": p.updated_at.isoformat(),
                }
                for p in projects
            ]
        }, 200

    @app.get("/journal-projects/get")
    @boundary_handler()
    async def get(uid: str) -> Any:
        """
        Get a specific journal project.

        FastHTML Convention: Query parameter with type hint
        Query params:
            uid: Project UID

        Returns:
        - 200: Project details
        - 404: Project not found
        - 503: Service not available
        """
        if not services.journal_projects:
            return {"error": "Journal projects service not available"}, 503

        result = await services.journal_projects.get_project(uid)

        if result.is_error:
            return {"error": "Failed to get project"}, 500

        if not result.value:
            return {"error": "Project not found"}, 404

        project = result.value

        return {
            "uid": project.uid,
            "user_uid": project.user_uid,
            "name": project.name,
            "instructions": project.instructions,
            "model": project.model,
            "context_notes": project.context_notes,
            "domain": project.domain.value if project.domain else None,
            "is_active": project.is_active,
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
        }, 200

    @app.post("/journal-projects/update")
    @boundary_handler()
    async def update(request, uid: str) -> Any:
        """
        Update a journal project.

        FastHTML Convention: POST for mutations, query param for ID
        Query params:
            uid: Project UID

        Body (form or JSON):
        - name: New name (optional)
        - instructions: New instructions (optional)
        - model: New model (optional)
        - context_notes: New context notes (optional)
        - domain: New domain (optional)
        - is_active: New active status (optional)

        Returns:
        - 200: Updated project
        - 404: Project not found
        - 503: Service not available
        """
        if not services.journal_projects:
            return {"error": "Journal projects service not available"}, 503

        try:
            form_data = await request.form()

            # Parse context notes
            context_notes_str = form_data.get("context_notes")
            context_notes = None
            if context_notes_str:
                context_notes = [
                    line.strip() for line in context_notes_str.split("\n") if line.strip()
                ]

            # Parse domain
            domain_str = form_data.get("domain")
            domain = Domain(domain_str) if domain_str else None

            # Parse is_active
            is_active_str = form_data.get("is_active")
            is_active = is_active_str.lower() == "true" if is_active_str else None

            result = await services.journal_projects.update_project(
                uid=uid,
                name=form_data.get("name"),
                instructions=form_data.get("instructions"),
                model=form_data.get("model"),
                context_notes=context_notes,
                domain=domain,
                is_active=is_active,
            )

            if result.is_error:
                if "not found" in str(result.error).lower():
                    return {"error": "Project not found"}, 404
                return {"error": "Failed to update project"}, 500

            project = result.value

            return {
                "uid": project.uid,
                "name": project.name,
                "instructions": project.instructions,
                "model": project.model,
                "context_notes": project.context_notes,
                "domain": project.domain.value if project.domain else None,
                "is_active": project.is_active,
                "updated_at": project.updated_at.isoformat(),
            }, 200

        except Exception as e:
            logger.error(f"Error updating project: {e}")
            return {"error": "Failed to update project", "details": str(e)}, 500

    @app.post("/journal-projects/delete")
    @boundary_handler()
    async def delete(uid: str) -> Any:
        """
        Delete a journal project.

        FastHTML Convention: POST for mutations, query param for ID
        Query params:
            uid: Project UID

        Returns:
        - 204: Project deleted
        - 404: Project not found
        - 503: Service not available
        """
        if not services.journal_projects:
            return {"error": "Journal projects service not available"}, 503

        result = await services.journal_projects.delete_project(uid)

        if result.is_error:
            return {"error": "Failed to delete project"}, 500

        return "", 204

    @app.post("/journal-projects/feedback")
    @boundary_handler()
    async def feedback(request) -> Any:
        """
        Generate AI feedback for a journal entry using a project.

        Query/Form params:
        - entry_uid: Journal entry UID (required)
        - project_uid: Project UID (required)
        - temperature: Sampling temperature 0-1 (optional, default 0.7)
        - max_tokens: Max tokens to generate (optional, default 4000)
        - save_feedback: Whether to save to entry (optional, default true)

        Returns:
        - 200: Feedback generated
        - 400: Invalid input
        - 503: Service not available
        """
        if not services.journal_feedback:
            return {"error": "Journal feedback service not available"}, 503

        try:
            # Try query params first, then form data
            params = dict(request.query_params)
            if not params:
                form_data = await request.form()
                params = dict(form_data)

            entry_uid = params.get("entry_uid")
            project_uid = params.get("project_uid")

            if not entry_uid or not project_uid:
                return {"error": "entry_uid and project_uid are required"}, 400

            # Get entry and project
            entry_result = await services.journals.get_journal(entry_uid)
            if entry_result.is_error or not entry_result.value:
                return {"error": "Journal entry not found"}, 404

            project_result = await services.journal_projects.get_project(project_uid)
            if project_result.is_error or not project_result.value:
                return {"error": "Project not found"}, 404

            entry = entry_result.value
            project = project_result.value

            # Parse optional params
            temperature = float(params.get("temperature", 0.7))
            max_tokens = int(params.get("max_tokens", 4000))
            save_feedback = params.get("save_feedback", "true").lower() == "true"

            # Generate feedback
            feedback_result = await services.journal_feedback.generate_feedback(
                entry=entry, project=project, temperature=temperature, max_tokens=max_tokens
            )

            if feedback_result.is_error:
                logger.error(f"Failed to generate feedback: {feedback_result.error}")
                return {
                    "error": "Failed to generate feedback",
                    "details": str(feedback_result.error),
                }, 500

            feedback = feedback_result.value

            # Optionally save to entry
            if save_feedback:
                from core.models.journal import journal_dto_to_pure, journal_pure_to_dto

                dto = journal_pure_to_dto(entry)
                dto.project_uid = project_uid
                dto.feedback = feedback
                dto.feedback_generated_at = datetime.now()

                updated_entry = journal_dto_to_pure(dto)
                update_result = await services.journals.update_journal(updated_entry)

                if update_result.is_error:
                    logger.warning(f"Generated feedback but failed to save: {update_result.error}")

            return {
                "entry_uid": entry_uid,
                "project_uid": project_uid,
                "feedback": feedback,
                "generated_at": datetime.now().isoformat(),
                "saved": save_feedback,
            }, 200

        except Exception as e:
            logger.error(f"Error generating feedback: {e}")
            return {"error": "Failed to generate feedback", "details": str(e)}, 500

    logger.info("✅ Journal project API routes registered (FastHTML-aligned)")


__all__ = ["create_journal_project_routes"]
