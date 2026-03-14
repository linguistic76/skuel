"""
Form Templates API - Admin CRUD Routes
=======================================

Admin-only routes for managing FormTemplate entities.
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Request
from pydantic import ValidationError

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.boundary import boundary_handler
from core.models.forms.form_template_request import (
    FormLessonLinkRequest,
    FormTemplateCreateRequest,
    FormTemplateUpdateRequest,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.forms.form_template_service import FormTemplateService

logger = get_logger(__name__)


def create_form_templates_api_routes(
    app: Any,
    rt: Any,
    form_template_service: "FormTemplateService",
    user_service: Any = None,
) -> list[Any]:
    """Create form template API routes (admin-only)."""

    get_user_service = make_service_getter(user_service)

    # ========================================================================
    # CREATE
    # ========================================================================

    @rt("/api/form-templates/create", methods=["POST"])
    @require_admin(get_user_service)
    @boundary_handler(success_status=201)
    async def create_form_template(request: Request, current_user: Any = None) -> Result[Any]:
        """Create a new FormTemplate."""
        try:
            body = await request.json()
            req = FormTemplateCreateRequest(**body)
        except Exception as e:
            return Result.fail(Errors.validation(f"Invalid request body: {e}", field="body"))

        return await form_template_service.create_form_template(
            title=req.title,
            form_schema=req.form_schema,
            description=req.description,
            instructions=req.instructions,
            tags=req.tags,
        )

    # ========================================================================
    # READ
    # ========================================================================

    @rt("/api/form-templates/get", methods=["GET"])
    @boundary_handler()
    async def get_form_template(request: Request) -> Result[Any]:
        """Get a FormTemplate by UID."""
        uid = request.query_params.get("uid")
        if not uid:
            return Result.fail(Errors.validation("uid is required", field="uid"))
        return await form_template_service.get_form_template(uid)

    @rt("/api/form-templates", methods=["GET"])
    @boundary_handler()
    async def list_form_templates(request: Request) -> Result[Any]:
        """List all form templates."""
        limit = int(request.query_params.get("limit", "50"))
        return await form_template_service.list_form_templates(limit=limit)

    # ========================================================================
    # UPDATE
    # ========================================================================

    @rt("/api/form-templates/update", methods=["PUT"])
    @require_admin(get_user_service)
    @boundary_handler()
    async def update_form_template(request: Request, current_user: Any = None) -> Result[Any]:
        """Update a FormTemplate."""
        uid = request.query_params.get("uid")
        if not uid:
            return Result.fail(Errors.validation("uid is required", field="uid"))

        try:
            body = await request.json()
            req = FormTemplateUpdateRequest(**body)
        except Exception as e:
            return Result.fail(Errors.validation(f"Invalid request body: {e}", field="body"))

        return await form_template_service.update_form_template(
            uid=uid,
            title=req.title,
            description=req.description,
            instructions=req.instructions,
            form_schema=req.form_schema,
            tags=req.tags,
            status=req.status,
        )

    # ========================================================================
    # DELETE
    # ========================================================================

    @rt("/api/form-templates/delete", methods=["DELETE"])
    @require_admin(get_user_service)
    @boundary_handler()
    async def delete_form_template(request: Request, current_user: Any = None) -> Result[Any]:
        """Delete a FormTemplate."""
        uid = request.query_params.get("uid")
        if not uid:
            return Result.fail(Errors.validation("uid is required", field="uid"))
        return await form_template_service.delete_form_template(uid)

    # ========================================================================
    # LESSON LINKING
    # ========================================================================

    @rt("/api/form-templates/link-lesson", methods=["POST"])
    @require_admin(get_user_service)
    @boundary_handler()
    async def link_form_to_lesson(request: Request, current_user: Any = None) -> Result[Any]:
        """Link a FormTemplate to a Lesson via EMBEDS_FORM."""
        try:
            body = await request.json()
            req = FormLessonLinkRequest(**body)
        except ValidationError as e:
            return Result.fail(Errors.validation(str(e), field="body"))
        except Exception as e:
            return Result.fail(Errors.validation(f"Invalid request body: {e}", field="body"))

        return await form_template_service.link_to_lesson(req.form_template_uid, req.lesson_uid)

    @rt("/api/form-templates/unlink-lesson", methods=["POST"])
    @require_admin(get_user_service)
    @boundary_handler()
    async def unlink_form_from_lesson(request: Request, current_user: Any = None) -> Result[Any]:
        """Remove EMBEDS_FORM link between FormTemplate and Lesson."""
        try:
            body = await request.json()
            req = FormLessonLinkRequest(**body)
        except ValidationError as e:
            return Result.fail(Errors.validation(str(e), field="body"))
        except Exception as e:
            return Result.fail(Errors.validation(f"Invalid request body: {e}", field="body"))

        return await form_template_service.unlink_from_lesson(
            req.form_template_uid, req.lesson_uid
        )

    return []
