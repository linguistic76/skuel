"""
Upload UI Routes - Per-User Bulk File Upload Page
==================================================

User-facing page for uploading Activity Domain YAML files.
Uses HTMX for file upload and results display.

Routes:
- GET /upload - Render upload page
- POST /upload/files - HTMX endpoint for file upload (returns HTML fragment)
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H3,
    A,
    Code,
    Div,
    Form,
    Li,
    P,
    Span,
    Ul,
)
from starlette.datastructures import UploadFile

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.auth.roles import get_user_role
from adapters.inbound.fasthtml_types import Request
from core.models.enums.user_enums import UserRole
from core.services.ingestion.user_upload_service import MAX_FILES_PER_REQUEST
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonT
from ui.forms.components import Input
from ui.patterns import PageHeader
from ui.patterns.upload_results import UploadError, UploadResultsSummary
from ui.workbench.nav import render_submissions_sidebar_page

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.ingestion.user_upload_service import UserUploadService

logger = get_logger("skuel.routes.upload")


def _supported_types_section(is_teacher: bool = False) -> Div:
    """Inline documentation about supported YAML types."""
    items = [
        Li(Span("Task", cls="font-bold"), " — required field: ", Code("title")),
        Li(Span("Goal", cls="font-bold"), " — required field: ", Code("title")),
        Li(Span("Habit", cls="font-bold"), " — required field: ", Code("title")),
        Li(Span("Event", cls="font-bold"), " — required field: ", Code("title")),
        Li(Span("Choice", cls="font-bold"), " — required field: ", Code("title")),
        Li(
            Span("Principle", cls="font-bold"),
            " — required fields: ",
            Code("name"),
            ", ",
            Code("statement"),
        ),
        Li(
            Span("UserEntry", cls="font-bold"),
            " — required field: ",
            Code("pipeline"),
            " (one of ",
            Code("none"),
            ", ",
            Code("teacher_review"),
            ", ",
            Code("llm_summary"),
            "). Audio pipelines use the audio-upload flow.",
        ),
    ]
    if is_teacher:
        items.append(
            Li(
                Span("Group", cls="font-bold"),
                " — required field: ",
                Code("name"),
                " (teachers only; uploader becomes owner)",
            )
        )
    return Div(
        H3("Supported Types", cls="text-lg font-semibold mb-2"),
        Ul(*items, cls="list-disc pl-6 mt-2"),
        P(
            "Each YAML file must include a ",
            Code("type"),
            " field (e.g., ",
            Code("type: Task"),
            "). ",
            A(
                "Download vault template",
                href="/static/templates/activity-vault-template.zip",
                cls="hover:underline text-primary",
                download=True,
            ),
            " for examples.",
            cls="text-muted-foreground mt-2",
        ),
        cls="mb-6",
    )


def _audience_section() -> Div:
    """Document the UserEntry ``audience:`` field."""
    return Div(
        H3("UserEntry Audience", cls="text-lg font-semibold mb-2"),
        P(
            "UserEntry files may declare who sees the submission via an ",
            Code("audience"),
            " field. Defaults to ",
            Code("teachers"),
            " when omitted.",
            cls="text-muted-foreground mb-2",
        ),
        Ul(
            Li(
                Code("teachers"),
                " — shares with every group you belong to as a student (default).",
            ),
            Li(Code("group:<group_uid>"), " — shares with one specific group."),
            Li(Code("public"), " — publishes to your portfolio."),
            Li(Code("private"), " — keeps the entry unshared."),
            cls="list-disc pl-6 mt-2",
        ),
        cls="mb-6",
    )


def _upload_form() -> Form:
    """HTMX-powered file upload form."""
    return Form(
        Div(
            Div(
                P(
                    "Select one or more YAML files to upload",
                    cls="text-center text-muted-foreground mb-2",
                ),
                Input(
                    type="file",
                    name="files",
                    accept=".yaml,.yml",
                    multiple=True,
                    cls="w-full",
                ),
                P(
                    "Accepted formats: .yaml, .yml",
                    cls="text-center text-xs text-muted-foreground mt-2",
                ),
                cls="p-6 bg-muted rounded border border-border",
            ),
            cls="mb-6",
        ),
        Div(
            Button(
                "Upload & Ingest",
                type="submit",
                variant=ButtonT.primary,
            ),
            Span(
                "",
                id="upload-spinner",
                cls="htmx-indicator ml-2",
                **{"uk-spinner": "ratio: 0.6"},
            ),
            cls="flex items-center",
        ),
        hx_post="/upload/files",
        hx_target="#upload-results",
        hx_swap="innerHTML",
        hx_encoding="multipart/form-data",
        hx_indicator="#upload-spinner",
    )


def _results_area() -> Div:
    """Placeholder div for HTMX results."""
    return Div(id="upload-results")


def create_upload_ui_routes(
    app: "FastHTMLApp",
    rt: "RouteDecorator",
    upload_service: "UserUploadService | None",
    user_service: Any = None,
) -> list[Any]:
    """Create user-facing upload UI routes."""

    routes: list[Any] = []

    @rt("/upload")
    async def upload_page(request: Request) -> Any:
        """Render the upload page."""
        require_authenticated_user(request)

        is_teacher = False
        if user_service is not None:
            resolved_role = await get_user_role(request, user_service)
            if resolved_role is not None:
                is_teacher = resolved_role.has_permission(UserRole.TEACHER)

        content = Div(
            PageHeader(
                "Upload Activity Data",
                subtitle="Bulk upload YAML files for Tasks, Goals, Habits, Events, Choices, and Principles.",
            ),
            _supported_types_section(is_teacher=is_teacher),
            _audience_section(),
            _upload_form(),
            _results_area(),
            cls="max-w-3xl mx-auto px-4",
        )

        return await render_submissions_sidebar_page(
            content=content,
            active="upload",
            request=request,
        )

    @rt("/upload/files", methods=["POST"])
    async def upload_files_htmx(request: Request) -> Any:
        """HTMX endpoint: upload YAML files and return HTML results fragment."""
        try:
            user_uid = require_authenticated_user(request)

            if not upload_service:
                return UploadError("Upload service unavailable")

            form = await request.form()
            raw_files = form.getlist("files")

            if not raw_files:
                return UploadError("No files selected. Choose .yaml or .yml files to upload.")

            if len(raw_files) > MAX_FILES_PER_REQUEST:
                return UploadError(
                    f"Too many files: {len(raw_files)} (max {MAX_FILES_PER_REQUEST})"
                )

            # Read UploadFile objects into (filename, bytes) pairs
            file_pairs: list[tuple[str, bytes]] = []
            for raw_file in raw_files:
                if not isinstance(raw_file, UploadFile):
                    continue
                content = await raw_file.read()
                filename = raw_file.filename or "unknown.yaml"
                file_pairs.append((filename, content))

            if not file_pairs:
                return UploadError("No valid files found in upload")

            user_role = UserRole.REGISTERED
            if user_service is not None:
                resolved_role = await get_user_role(request, user_service)
                if resolved_role is not None:
                    user_role = resolved_role

            result = await upload_service.upload_and_ingest(
                user_uid, file_pairs, user_role=user_role
            )

            if result.is_error:
                return UploadError(str(result.expect_error()))

            return UploadResultsSummary(result.value)

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error("Upload failed: %s", e, exc_info=True)
            return UploadError(f"Upload failed: {e}")

    routes.extend([upload_page, upload_files_htmx])

    logger.info(f"Upload UI routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_upload_ui_routes"]
