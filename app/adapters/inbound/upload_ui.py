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
    Button,
    Code,
    Div,
    Form,
    Input,
    Li,
    P,
    Span,
    Ul,
)
from starlette.datastructures import UploadFile
from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from core.services.ingestion.user_upload_service import MAX_FILES_PER_REQUEST
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.patterns import PageHeader
from ui.patterns.upload_results import UploadError, UploadResultsSummary

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
    from core.services.ingestion.user_upload_service import UserUploadService

logger = get_logger("skuel.routes.upload")


def _supported_types_section() -> Div:
    """Inline documentation about supported YAML types."""
    return Div(
        H3("Supported Types", cls="uk-h4 uk-margin-small-bottom"),
        Ul(
            Li(
                Span("Task", cls="uk-text-bold"),
                " — required field: ",
                Code("title"),
            ),
            Li(
                Span("Goal", cls="uk-text-bold"),
                " — required field: ",
                Code("title"),
            ),
            Li(
                Span("Habit", cls="uk-text-bold"),
                " — required field: ",
                Code("title"),
            ),
            Li(
                Span("Event", cls="uk-text-bold"),
                " — required field: ",
                Code("title"),
            ),
            Li(
                Span("Choice", cls="uk-text-bold"),
                " — required field: ",
                Code("title"),
            ),
            Li(
                Span("Principle", cls="uk-text-bold"),
                " — required fields: ",
                Code("name"),
                ", ",
                Code("statement"),
            ),
            cls="uk-list uk-list-disc uk-margin-small-top",
        ),
        P(
            "Each YAML file must include a ",
            Code("type"),
            " field (e.g., ",
            Code("type: Task"),
            "). ",
            A(
                "Download vault template",
                href="/static/templates/activity-vault-template.zip",
                cls="uk-link",
                download=True,
            ),
            " for examples.",
            cls="uk-text-muted uk-margin-small-top",
        ),
        cls="uk-margin-medium-bottom",
    )


def _upload_form() -> Form:
    """HTMX-powered file upload form."""
    return Form(
        Div(
            Div(
                P(
                    "Drag and drop YAML files here, or click to browse",
                    cls="uk-text-center uk-text-muted uk-margin-small-bottom",
                ),
                Input(
                    type="file",
                    name="files",
                    accept=".yaml,.yml",
                    multiple=True,
                    cls="uk-width-1-1",
                ),
                cls="uk-padding uk-background-muted uk-border-rounded",
                style="border: 2px dashed var(--color-border); cursor: pointer;",
            ),
            cls="uk-margin-medium-bottom",
        ),
        Div(
            Button(
                "Upload & Ingest",
                type="submit",
                cls="uk-button uk-button-primary",
            ),
            Span(
                "",
                id="upload-spinner",
                cls="htmx-indicator uk-margin-small-left",
                **{"uk-spinner": "ratio: 0.6"},
            ),
            cls="uk-flex uk-flex-middle",
        ),
        **{
            "hx-post": "/upload/files",
            "hx-target": "#upload-results",
            "hx-swap": "innerHTML",
            "hx-encoding": "multipart/form-data",
            "hx-indicator": "#upload-spinner",
        },
    )


def _results_area() -> Div:
    """Placeholder div for HTMX results."""
    return Div(id="upload-results")


def create_upload_ui_routes(
    app: "FastHTMLApp",
    rt: "RouteDecorator",
    upload_service: "UserUploadService | None",
    user_service: Any = None,
) -> "RouteList":
    """Create user-facing upload UI routes."""

    routes: list[Any] = []

    @rt("/upload")
    async def upload_page(request: Request) -> Any:
        """Render the upload page."""
        require_authenticated_user(request)

        content = Div(
            PageHeader(
                "Upload Activity Data",
                subtitle="Bulk upload YAML files for Tasks, Goals, Habits, Events, Choices, and Principles.",
            ),
            _supported_types_section(),
            _upload_form(),
            _results_area(),
            cls="uk-container uk-container-small",
        )

        return await BasePage(
            content,
            title="Upload Activity Data",
            request=request,
            active_page="upload",
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

            result = await upload_service.upload_and_ingest(user_uid, file_pairs)

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
