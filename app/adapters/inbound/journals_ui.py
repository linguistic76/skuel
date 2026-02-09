"""
Journals UI Routes — Admin-Only AI Submission
================================================

Admin uploads files here to be processed by AI according to ReportProject
instructions. Distinct from /reports which sends files to human review.

Processor type is auto-set to LLM — human review lives at /reports.

Layout: Unified sidebar (Tailwind + Alpine) with 2 nav items.
Desktop: collapsible sidebar. Mobile: horizontal tabs.
"""

import tempfile
from pathlib import Path
from typing import Any

from fasthtml.common import (
    H4,
    A,
    Div,
    Form,
    Input,
    Label,
    NotStr,
    Option,
    P,
    Script,
    Select,
    Span,
)
from starlette.datastructures import UploadFile
from starlette.requests import Request

from core.auth import require_admin, require_authenticated_user
from core.models.enums.report_enums import ProcessorType, ReportType
from core.ui.daisy_components import Button, ButtonT
from core.utils.logging import get_logger
from ui.patterns.page_header import PageHeader
from ui.patterns.sidebar import SidebarItem, SidebarPage

logger = get_logger("skuel.routes.journals.ui")


# ============================================================================
# DEFAULT INSTRUCTIONS
# ============================================================================

DEFAULT_INSTRUCTIONS = """# General Processing Instructions

## Purpose
Transform raw content into a well-formatted, readable document.

## Formatting Rules
1. **Structure**: Organize into coherent paragraphs
2. **Flow**: Remove verbal fillers ("um", "uh", "like")
3. **Clarity**: Improve sentence structure while preserving meaning
4. **Themes**: Identify main themes and group related content
5. **Action Items**: Extract concrete action items mentioned
6. **Title**: Generate concise, descriptive title

## Context Integration
- Reference active goals, tasks, habits when relevant
- Link to recent journal themes for continuity
- Identify learning opportunities from current paths

## Output Format
- Title (concise, descriptive)
- Summary (2-3 sentences)
- Main content (well-formatted paragraphs)
- Key themes (bullet list)
- Action items (if any)

Preserve the author's voice and authenticity while improving readability.
"""


# ============================================================================
# HTMX FRAGMENT RENDERING
# ============================================================================


def _render_upload_status(
    status: str,
    message: str,
    report_uid: str | None = None,
    is_error: bool = False,
) -> Any:
    """Render upload status as HTML fragment for HTMX swap."""
    if is_error:
        return Div(
            Div(
                H4("Upload Failed", cls="mb-0"),
                P(message, cls="mb-0"),
                cls="alert alert-error",
            ),
            id="upload-status",
        )

    return Div(
        Div(
            H4("Submitted to AI", cls="mb-0"),
            P(f"Report ID: {report_uid}", cls="mb-0") if report_uid else None,
            P(f"Status: {status}", cls="mb-0"),
            A(
                "View Report",
                href=f"/reports/{report_uid}",
                cls="btn btn-sm btn-ghost mt-2",
            )
            if report_uid
            else None,
            cls="alert alert-success",
        ),
        id="upload-status",
    )


def _get_status_badge_class(status: str) -> str:
    """Get DaisyUI badge class for report status."""
    classes = {
        "submitted": "badge-warning",
        "queued": "badge-warning",
        "processing": "badge-info",
        "completed": "badge-success",
        "failed": "badge-error",
        "manual_review": "badge-ghost",
    }
    return classes.get(status, "badge-ghost")


def _get_report_identifier(report: Any) -> str:
    """Extract the identifier from report metadata."""
    metadata = getattr(report, "metadata", None)
    if isinstance(metadata, dict):
        identifier = metadata.get("identifier")
        if identifier:
            return str(identifier)
    return getattr(report, "report_type", "unknown")


def _render_report_card(report: Any) -> Any:
    """Render a single report card for the AI reports grid."""
    file_size_mb = (report.file_size / 1024 / 1024) if getattr(report, "file_size", 0) else 0
    identifier = _get_report_identifier(report)
    return Div(
        Div(
            Div(
                Div(
                    H4(report.original_filename, cls="mb-0 font-semibold"),
                    P(
                        f"{identifier} \u2022 {file_size_mb:.2f} MB",
                        cls="text-sm text-base-content/60 mb-0",
                    ),
                    cls="flex-1",
                ),
                Div(
                    Span(
                        report.status,
                        cls=f"badge {_get_status_badge_class(report.status)}",
                    ),
                ),
                Div(
                    A(
                        "View",
                        href=f"/reports/{report.uid}",
                        cls="btn btn-sm btn-ghost",
                    ),
                    cls="flex gap-2",
                ),
                cls="flex items-center gap-4",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )


def _render_reports_grid(reports: list[Any]) -> Any:
    """Render reports grid as HTML fragment for HTMX swap."""
    if not reports:
        return Div(
            P("No AI-processed reports found.", cls="text-center text-base-content/60"),
            id="reports-grid-container",
        )

    return Div(
        *[_render_report_card(r) for r in reports],
        id="reports-grid-container",
    )


# ============================================================================
# SIDEBAR NAVIGATION
# ============================================================================

JOURNALS_SIDEBAR_ITEMS = [
    SidebarItem("Submit", "/journals/submit", "submit", icon="📤"),
    SidebarItem("AI Reports", "/journals/browse", "browse", icon="📄"),
]


# ============================================================================
# CONTENT FRAGMENTS
# ============================================================================


def _render_upload_form(projects: list[Any]) -> Any:
    """Render the file upload form with instructions selector.

    Three instruction modes:
    - Default: built-in general processing instructions
    - Existing project: user-created instruction sets (stored as ReportProjects in Neo4j)
    - Upload new: create a new instruction set from a .md file
    """
    project_options = [
        Option("Default — General Processing", value="__default__", selected=True),
    ]
    project_options.extend(Option(p.name, value=p.uid) for p in projects)
    project_options.append(
        Option("Upload New Instructions...", value="__upload__"),
    )

    return Div(
        Div(
            Div(
                Form(
                    # Instructions selector with Alpine.js toggle
                    Div(
                        Label("Instructions", cls="label"),
                        Select(
                            *project_options,
                            name="project_uid",
                            cls="select select-bordered w-full",
                            required=True,
                            **{"x-on:change": "showUpload = $event.target.value === '__upload__'"},
                        ),
                        P(
                            "Choose which instructions to process the file against. ",
                            "Instruction sets are stored as ",
                            A(
                                "Report Projects",
                                href="/ui/report-projects",
                                cls="link link-primary",
                            ),
                            " in Neo4j.",
                            cls="text-xs text-base-content/60 mt-1",
                        ),
                        # Instructions file upload (shown when "Upload New" selected)
                        Div(
                            Label("Instructions File (.md)", cls="label"),
                            Input(
                                type="file",
                                name="instructions_file",
                                accept=".md,text/markdown,text/plain",
                                cls="file-input file-input-bordered w-full",
                            ),
                            P(
                                "Upload a markdown file with instructions. A new Report Project will be created from it.",
                                cls="text-xs text-base-content/60 mt-1",
                            ),
                            cls="mt-3",
                            **{"x-show": "showUpload", "x-cloak": True},
                        ),
                        cls="mb-4",
                    ),
                    # Identifier input
                    Div(
                        Label("Identifier", cls="label"),
                        Input(
                            type="text",
                            name="identifier",
                            placeholder="e.g. meditation-basics, yoga-101",
                            cls="input input-bordered w-full",
                            required=True,
                        ),
                        P(
                            "A short label linking this submission to a Knowledge Unit",
                            cls="text-xs text-base-content/60 mt-1",
                        ),
                        cls="mb-4",
                    ),
                    # File input
                    Div(
                        Label(
                            Div(
                                P("Select File", cls="text-center mb-0"),
                                P(
                                    "Click to browse (audio, text, PDF, images, video)",
                                    cls="text-sm text-base-content/60 text-center mt-0",
                                ),
                                cls="p-4 text-center bg-base-200 rounded-lg cursor-pointer border-2 border-dashed border-base-300",
                            ),
                            Input(
                                type="file",
                                name="file",
                                accept="audio/*,text/*,.pdf,.doc,.docx,image/*,video/*",
                                cls="hidden",
                                required=True,
                            ),
                            cls="w-full cursor-pointer",
                        ),
                        cls="mb-4",
                    ),
                    # Submit button
                    Div(
                        Button(
                            "Submit to AI",
                            variant=ButtonT.primary,
                            type="submit",
                        ),
                        cls="text-center",
                    ),
                    # Upload status (HTMX target)
                    Div(id="upload-status", cls="mt-4 text-center"),
                    # HTMX attributes
                    **{
                        "hx-post": "/journals/upload",
                        "hx-target": "#upload-status",
                        "hx-swap": "outerHTML",
                        "hx-encoding": "multipart/form-data",
                    },
                    id="upload-form",
                    **{"x-data": "{ showUpload: false }"},
                ),
                cls="card-body",
            ),
            cls="card bg-base-100 shadow-sm hover:shadow-md transition-shadow",
        ),
    )


def _upload_form_script() -> Any:
    """HTMX event handlers for upload form UX polish."""
    return Script(
        NotStr("""
        document.body.addEventListener('htmx:beforeRequest', function(evt) {
            var form = evt.detail.elt;
            if (form.id === 'upload-form') {
                var btn = form.querySelector('button[type="submit"]');
                if (btn) {
                    btn.disabled = true;
                    btn.textContent = 'Processing...';
                }
            }
        });

        document.body.addEventListener('htmx:afterRequest', function(evt) {
            var form = evt.detail.elt;
            if (form.id === 'upload-form') {
                form.reset();
                var btn = form.querySelector('button[type="submit"]');
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = 'Submit to AI';
                }
            }
        });
    """)
    )


def _render_filters_section() -> Any:
    """Render the status filter controls card."""
    return Div(
        Div(
            Form(
                Div(
                    Label("Status", cls="label"),
                    Select(
                        Option("All Status", value="", selected=True),
                        Option("Submitted", value="submitted"),
                        Option("Queued", value="queued"),
                        Option("Processing", value="processing"),
                        Option("Completed", value="completed"),
                        Option("Failed", value="failed"),
                        name="status",
                        cls="select select-bordered w-full",
                    ),
                    cls="mb-2",
                ),
                **{
                    "hx-get": "/journals/grid",
                    "hx-target": "#reports-grid-container",
                    "hx-swap": "outerHTML",
                    "hx-trigger": "change from:select",
                },
                id="filter-form",
            ),
            cls="card-body",
        ),
        cls="card bg-base-100 shadow-sm mb-6",
    )


def _render_reports_grid_container() -> Any:
    """Render the HTMX-loading reports grid container."""
    return Div(
        P("Loading AI reports...", cls="text-center text-base-content/60"),
        id="reports-grid-container",
        cls="mt-4",
        **{
            "hx-get": "/journals/grid",
            "hx-trigger": "load",
            "hx-swap": "outerHTML",
        },
    )


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_journals_ui_routes(
    _app,
    rt,
    report_service,
    processing_service,
    report_projects_service,
    user_service=None,
):
    """
    Create journal UI routes (admin-only AI submission).

    Args:
        _app: FastHTML application instance
        rt: Router instance
        report_service: ReportSubmissionService
        processing_service: ReportsProcessingService
        report_projects_service: ReportProjectService
        user_service: UserService for admin role checks
    """

    logger.info("Creating Journals UI routes (admin-only)")

    def get_user_service():
        """Get user service for admin role checks."""
        return user_service

    # ========================================================================
    # SIDEBAR PAGES
    # ========================================================================

    @rt("/journals")
    @require_admin(get_user_service)
    async def journals_landing(request: Request, current_user: Any = None) -> Any:
        """Journals landing — defaults to Submit page."""
        return await _render_submit_page(request)

    @rt("/journals/submit")
    @require_admin(get_user_service)
    async def journals_submit_page(request: Request, current_user: Any = None) -> Any:
        """Submit page: upload form with ReportProject selector."""
        return await _render_submit_page(request)

    async def _render_submit_page(request: Request) -> Any:
        user_uid = require_authenticated_user(request)

        # Fetch available ReportProjects for the dropdown
        projects = []
        projects_result = await report_projects_service.list_user_projects(user_uid)
        if not projects_result.is_error and projects_result.value:
            projects = projects_result.value

        content = Div(
            PageHeader(
                "Submit to AI",
                subtitle="Upload a file to be processed by AI using a Report Project's instructions",
            ),
            _render_upload_form(projects),
            _upload_form_script(),
        )
        return await SidebarPage(
            content=content,
            items=JOURNALS_SIDEBAR_ITEMS,
            active="submit",
            title="Journals",
            subtitle="Submit files to AI processing",
            storage_key="journals-sidebar",
            page_title="Submit to AI",
            request=request,
            active_page="journals",
            title_href="/journals",
        )

    @rt("/journals/browse")
    @require_admin(get_user_service)
    async def journals_browse_page(request: Request, current_user: Any = None) -> Any:
        """Browse page: AI-processed reports with filters."""
        user_uid = require_authenticated_user(request)

        # Check if any projects exist for info guidance
        has_projects = False
        projects_result = await report_projects_service.list_user_projects(user_uid)
        if not projects_result.is_error and projects_result.value:
            has_projects = bool(projects_result.value)

        no_projects_info = None
        if not has_projects:
            no_projects_info = Div(
                Div(
                    P(
                        "No custom instruction sets created yet. ",
                        A(
                            "Create Report Projects",
                            href="/ui/report-projects",
                            cls="link link-primary",
                        ),
                        " to customize AI processing. Default instructions are always available on the ",
                        A("Submit", href="/journals/submit", cls="link link-primary"),
                        " page.",
                        cls="mb-0",
                    ),
                    cls="alert alert-info mb-4",
                ),
            )

        content = Div(
            PageHeader("AI Reports", subtitle="Browse reports processed by AI"),
            no_projects_info,
            _render_filters_section(),
            _render_reports_grid_container(),
        )
        return await SidebarPage(
            content=content,
            items=JOURNALS_SIDEBAR_ITEMS,
            active="browse",
            title="Journals",
            subtitle="Submit files to AI processing",
            storage_key="journals-sidebar",
            page_title="AI Reports",
            request=request,
            active_page="journals",
            title_href="/journals",
        )

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/journals/upload")
    @require_admin(get_user_service)
    async def upload_journal(request: Request, current_user: Any = None) -> Any:
        """HTMX endpoint for file upload with AI processing.

        Three instruction modes based on project_uid value:
        - __default__: Use built-in DEFAULT_INSTRUCTIONS
        - __upload__: Read instructions from uploaded .md file, create new project
        - Any other value: Fetch existing ReportProject by UID
        """
        try:
            form = await request.form()
            uploaded_file = form.get("file")
            identifier = (form.get("identifier") or "").strip()
            project_uid = (form.get("project_uid") or "").strip()

            if not identifier:
                return _render_upload_status("error", "Identifier is required", is_error=True)

            if not project_uid:
                return _render_upload_status("error", "Please select instructions", is_error=True)

            if not uploaded_file or not isinstance(uploaded_file, UploadFile):
                return _render_upload_status("error", "No file provided", is_error=True)

            user_uid = require_authenticated_user(request)
            file_content = await uploaded_file.read()
            filename = uploaded_file.filename or "unknown"

            # Resolve instructions based on selected mode
            instructions_text = None
            resolved_project_uid = project_uid

            if project_uid == "__default__":
                instructions_text = DEFAULT_INSTRUCTIONS
                resolved_project_uid = "__default__"
                logger.info(
                    f"Journal upload: {filename} ({len(file_content)} bytes, "
                    f"identifier={identifier}, instructions=default)"
                )

            elif project_uid == "__upload__":
                instructions_file = form.get("instructions_file")
                if not instructions_file or not isinstance(instructions_file, UploadFile):
                    return _render_upload_status(
                        "error",
                        "Instructions file is required when uploading new instructions",
                        is_error=True,
                    )
                instructions_content = await instructions_file.read()
                instructions_filename = instructions_file.filename or "instructions.md"

                # Save to temp file and create project via service
                with tempfile.NamedTemporaryFile(
                    mode="wb", suffix=".md", delete=False, dir="/tmp"
                ) as tmp:
                    tmp.write(instructions_content)
                    tmp_path = tmp.name

                try:
                    # Rename temp file to preserve original filename for name extraction
                    named_path = Path(tmp_path).parent / instructions_filename
                    Path(tmp_path).rename(named_path)

                    project_result = await report_projects_service.load_project_from_file(
                        file_path=str(named_path), user_uid=user_uid
                    )
                    # Clean up temp file
                    named_path.unlink(missing_ok=True)
                except Exception:
                    Path(tmp_path).unlink(missing_ok=True)
                    raise

                if project_result.is_error or not project_result.value:
                    error_msg = "Failed to create project from instructions file"
                    if project_result.error:
                        error_msg = f"{error_msg}: {project_result.error.message}"
                    return _render_upload_status("error", error_msg, is_error=True)

                project = project_result.value
                instructions_text = project.instructions
                resolved_project_uid = project.uid
                logger.info(
                    f"Journal upload: {filename} ({len(file_content)} bytes, "
                    f"identifier={identifier}, new project={project.name})"
                )

            else:
                # Existing project — fetch by UID
                project_result = await report_projects_service.get_project(project_uid)
                if project_result.is_error or not project_result.value:
                    return _render_upload_status(
                        "error", "Selected instructions not found", is_error=True
                    )
                project = project_result.value
                instructions_text = project.instructions
                logger.info(
                    f"Journal upload: {filename} ({len(file_content)} bytes, "
                    f"identifier={identifier}, project={project.name})"
                )

            # Submit file with LLM processor type
            result = await report_service.submit_file(
                file_content=file_content,
                original_filename=filename,
                user_uid=user_uid,
                report_type=ReportType.JOURNAL,
                processor_type=ProcessorType.LLM,
                metadata={"identifier": identifier, "project_uid": resolved_project_uid},
            )

            if result.is_error:
                return _render_upload_status("error", str(result.error), is_error=True)

            report = result.value

            # Auto-trigger AI processing with resolved instructions
            process_result = await processing_service.process_report(
                report.uid, instructions={"instructions": instructions_text}
            )

            if process_result.is_error:
                error_msg = "File uploaded but AI processing failed"
                if process_result.error:
                    error_msg = f"{error_msg}: {process_result.error.user_message or process_result.error.message}"
                logger.warning(f"AI processing failed for {report.uid}: {error_msg}")
                return _render_upload_status(
                    status="submitted",
                    message=f"File uploaded. AI processing pending — {error_msg}",
                    report_uid=report.uid,
                )

            processed_report = process_result.value
            return _render_upload_status(
                status=processed_report.status if processed_report else "completed",
                message="File uploaded and processed by AI",
                report_uid=report.uid,
            )

        except Exception as e:
            logger.error(f"Error uploading journal: {e}", exc_info=True)
            return _render_upload_status("error", f"Upload failed: {e}", is_error=True)

    @rt("/journals/grid")
    @require_admin(get_user_service)
    async def get_journals_grid(request: Request, current_user: Any = None) -> Any:
        """HTMX endpoint for loading AI-processed reports grid."""
        try:
            user_uid = require_authenticated_user(request)
            status = request.query_params.get("status", "")

            kwargs: dict[str, Any] = {"user_uid": user_uid, "limit": 50}
            if status:
                kwargs["status"] = status

            result = await report_service.list_reports(**kwargs)

            if result.is_error:
                return Div(
                    P("Failed to load reports", cls="text-center text-error"),
                    id="reports-grid-container",
                )

            reports = result.value or []
            # Filter to LLM-processed reports
            ai_reports = [
                r
                for r in reports
                if getattr(r, "processor_type", None) in ("llm", "LLM", ProcessorType.LLM)
            ]
            return _render_reports_grid(ai_reports)

        except Exception as e:
            logger.error(f"Error loading AI reports: {e}", exc_info=True)
            return Div(
                P(f"Error: {e}", cls="text-center text-error"),
                id="reports-grid-container",
            )

    logger.info("Journals UI routes created successfully")

    return [
        journals_landing,
        journals_submit_page,
        journals_browse_page,
        upload_journal,
        get_journals_grid,
    ]
