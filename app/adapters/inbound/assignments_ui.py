"""
Assignments UI Routes
=====================

Clean dashboard for file submission and processing pipeline.
Uses HTMX for dynamic updates (JavaScript-minimal approach).

Phase 1 Implementation:
- File upload form (audio, text, future: PDF, images, video)
- Assignments grid with status badges
- Filter by type and status
- View processed content
- Download original and processed files

Future Enhancements:
- Drag-and-drop file upload
- Real-time status updates (WebSocket)
- Batch operations
- Manual review queue interface
"""

from typing import Any

from fasthtml.common import (
    H1,
    H3,
    H4,
    A,
    Container,
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

from core.ui.daisy_components import Button, ButtonT
from starlette.datastructures import UploadFile
from starlette.requests import Request

from core.auth import require_authenticated_user
from core.utils.logging import get_logger
from ui.layouts.navbar import create_navbar_for_request

logger = get_logger("skuel.routes.assignments.ui")


# ============================================================================
# HTMX FRAGMENT RENDERING FUNCTIONS
# ============================================================================


def _render_upload_status(
    status: str,
    message: str,
    assignment_uid: str | None = None,
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
            H4("File Uploaded Successfully!", cls="mb-0"),
            P(f"Assignment ID: {assignment_uid}", cls="mb-0") if assignment_uid else None,
            P(f"Status: {status}", cls="mb-0"),
            cls="alert alert-success",
        ),
        id="upload-status",
    )


def _get_status_badge_class(status: str) -> str:
    """Get DaisyUI badge class for assignment status."""
    classes = {
        "submitted": "badge-warning",
        "queued": "badge-warning",
        "processing": "badge-info",
        "completed": "badge-success",
        "failed": "badge-error",
        "manual_review": "badge-ghost",
    }
    return classes.get(status, "badge-ghost")


def _render_assignment_card(assignment: Any) -> Any:
    """Render a single assignment card."""
    file_size_mb = (assignment.file_size / 1024 / 1024) if hasattr(assignment, "file_size") else 0
    return Div(
        Div(
            Div(
                Div(
                    H4(assignment.original_filename, cls="mb-0 font-semibold"),
                    P(
                        f"{assignment.assignment_type} • {file_size_mb:.2f} MB",
                        cls="text-sm text-base-content/60 mb-0",
                    ),
                    cls="flex-1",
                ),
                Div(
                    Span(
                        assignment.status,
                        cls=f"badge {_get_status_badge_class(assignment.status)}",
                    ),
                ),
                Div(
                    A(
                        "View",
                        href=f"/assignments/{assignment.uid}",
                        cls="btn btn-sm btn-ghost",
                    ),
                ),
                cls="flex items-center gap-4",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )


def _render_assignments_grid(assignments: list[Any]) -> Any:
    """Render assignments grid as HTML fragment for HTMX swap."""
    if not assignments:
        return Div(
            P("No assignments found.", cls="text-center text-base-content/60"),
            id="assignments-grid-container",
        )

    return Div(
        *[_render_assignment_card(a) for a in assignments],
        id="assignments-grid-container",
    )


def _render_assignment_detail(assignment: Any) -> Any:
    """Render assignment detail info as HTML fragment."""
    file_size_mb = (assignment.file_size / 1024 / 1024) if hasattr(assignment, "file_size") else 0
    processing_duration = getattr(assignment, "processing_duration_seconds", None)
    created_at = getattr(assignment, "created_at", None)

    return Div(
        Div(
            Div(
                P("Filename", cls="text-xs text-base-content/50 mb-0"),
                P(assignment.original_filename, cls="mb-0 font-bold"),
            ),
            Div(
                P("Status", cls="text-xs text-base-content/50 mb-0"),
                P(
                    Span(
                        assignment.status,
                        cls=f"badge {_get_status_badge_class(assignment.status)}",
                    ),
                    cls="mb-0",
                ),
            ),
            Div(
                P("Type", cls="text-xs text-base-content/50 mb-0"),
                P(assignment.assignment_type, cls="mb-0"),
            ),
            Div(
                P("File Size", cls="text-xs text-base-content/50 mb-0"),
                P(f"{file_size_mb:.2f} MB", cls="mb-0"),
            ),
            Div(
                P("Processing Duration", cls="text-xs text-base-content/50 mb-0"),
                P(f"{processing_duration or 'N/A'} seconds", cls="mb-0"),
            ),
            Div(
                P("Created", cls="text-xs text-base-content/50 mb-0"),
                P(str(created_at) if created_at else "N/A", cls="mb-0"),
            ),
            cls="grid grid-cols-1 md:grid-cols-2 gap-4",
        ),
        id="assignment-info",
    )


def _render_processed_content(content: str | None, has_content: bool) -> Any:
    """Render processed content as HTML fragment."""
    if not has_content or not content:
        return Div(
            P("No processed content available.", cls="text-base-content/60"),
            id="processed-content",
            cls="p-4 bg-base-200 rounded-lg",
        )

    return Div(
        Div(content, cls="text-sm", style="white-space: pre-wrap"),
        id="processed-content",
        cls="p-4 bg-base-200 rounded-lg",
        style="max-height: 600px; overflow-y: auto;",
    )


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_assignments_ui_routes(_app, rt, _assignment_service, _processing_service):
    """
    Create all assignment UI routes.

    Args:
        app: FastHTML application instance
        rt: Router instance
        assignment_service: AssignmentSubmissionService
        processing_service: AssignmentProcessorService
    """

    logger.info("Creating Assignments UI routes")

    # ========================================================================
    # MAIN DASHBOARD
    # ========================================================================

    @rt("/assignments")
    async def assignments_dashboard(request: Request) -> Any:
        """
        Main assignments dashboard.

        Layout:
        - File upload form (top)
        - Filters (type, status)
        - Assignments grid (main content)
        - Statistics sidebar (optional)
        """
        require_authenticated_user(request)  # Enforce authentication

        # File upload form - HTMX-powered
        upload_form = Div(
            Div(
                H3("Upload File", cls="card-title"),
                P(
                    "Submit files for processing (audio, text, PDF, images, video)",
                    cls="text-base-content/60",
                ),
                Form(
                    # File input with label styling
                    Div(
                        Label(
                            Div(
                                P("Select File", cls="text-center mb-0"),
                                P(
                                    "Click to browse for files (audio, text, PDF, images, video)",
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
                    # Assignment type selector
                    Div(
                        Label("Assignment Type", cls="label"),
                        Select(
                            Option("Transcript", value="transcript", selected=True),
                            Option("Report", value="report"),
                            Option("Image Analysis", value="image_analysis"),
                            Option("Video Summary", value="video_summary"),
                            name="assignment_type",
                            cls="select select-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Processor type selector
                    Div(
                        Label("Processor", cls="label"),
                        Select(
                            Option("Automatic", value="automatic", selected=True),
                            Option("LLM (AI Processing)", value="llm"),
                            Option("Human Review", value="human"),
                            Option("Hybrid (AI + Human)", value="hybrid"),
                            name="processor_type",
                            cls="select select-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Auto-process checkbox
                    Div(
                        Label(
                            Input(
                                type="checkbox",
                                name="auto_process",
                                cls="checkbox checkbox-primary mr-2",
                                checked=True,
                            ),
                            Span("Automatically process after upload"),
                            cls="flex items-center cursor-pointer",
                        ),
                        cls="mb-4",
                    ),
                    # Upload button
                    Div(
                        Button(
                            "Upload & Submit",
                            variant=ButtonT.primary,
                            type="submit",
                        ),
                        cls="text-center",
                    ),
                    # Upload status (HTMX target)
                    Div(id="upload-status", cls="mt-4 text-center"),
                    # HTMX attributes for form submission
                    **{
                        "hx-post": "/assignments/upload",
                        "hx-target": "#upload-status",
                        "hx-swap": "outerHTML",
                        "hx-encoding": "multipart/form-data",
                    },
                    id="upload-form",
                ),
                cls="card-body",
            ),
            cls="card bg-base-100 shadow-sm hover:shadow-md transition-shadow",
        )

        # Filters section - HTMX-powered
        filters = Div(
            Div(
                H3("Filters", cls="card-title"),
                Form(
                    # Type filter
                    Div(
                        Label("Type", cls="label"),
                        Select(
                            Option("All Types", value="", selected=True),
                            Option("Transcript", value="transcript"),
                            Option("Report", value="report"),
                            Option("Image Analysis", value="image_analysis"),
                            Option("Video Summary", value="video_summary"),
                            name="assignment_type",
                            cls="select select-bordered w-full",
                        ),
                        cls="mb-2",
                    ),
                    # Status filter
                    Div(
                        Label("Status", cls="label"),
                        Select(
                            Option("All Status", value="", selected=True),
                            Option("Submitted", value="submitted"),
                            Option("Queued", value="queued"),
                            Option("Processing", value="processing"),
                            Option("Completed", value="completed"),
                            Option("Failed", value="failed"),
                            Option("Manual Review", value="manual_review"),
                            name="status",
                            cls="select select-bordered w-full",
                        ),
                        cls="mb-2",
                    ),
                    # HTMX: trigger grid reload on any change
                    **{
                        "hx-get": "/assignments/grid",
                        "hx-target": "#assignments-grid-container",
                        "hx-swap": "outerHTML",
                        "hx-trigger": "change from:select",
                    },
                    id="filter-form",
                ),
                cls="card-body",
            ),
            cls="card bg-base-100 shadow-sm",
        )

        # Assignments grid - HTMX-powered
        assignments_grid = Div(
            Div(
                H3("Your Assignments", cls="card-title"),
                P("View and manage your submitted files", cls="text-base-content/60"),
                # Grid container (loaded via HTMX on page load)
                Div(
                    P("Loading assignments...", cls="text-center text-base-content/60"),
                    id="assignments-grid-container",
                    cls="mt-4",
                    **{
                        "hx-get": "/assignments/grid",
                        "hx-trigger": "load",
                        "hx-swap": "outerHTML",
                    },
                ),
                cls="card-body",
            ),
            cls="card bg-base-100 shadow-sm",
        )

        # Main dashboard layout
        dashboard = Container(
            Div(
                H1("Assignments", cls="text-3xl font-bold"),
                P(
                    "Upload and process files (audio, text, documents, images, videos)",
                    cls="text-lg text-base-content/60",
                ),
                cls="text-center mb-8",
            ),
            # Upload form (full width)
            Div(upload_form, cls="mb-8"),
            # Filters and assignments grid (side by side)
            Div(
                Div(filters, cls="w-full md:w-1/4"),
                Div(assignments_grid, cls="w-full md:w-3/4"),
                cls="flex flex-col md:flex-row gap-4",
            ),
            # Minimal JavaScript for UX enhancements only
            Script(
                NotStr("""
                // HTMX event handlers for UX polish (not core functionality)
                document.body.addEventListener('htmx:beforeRequest', function(evt) {
                    const form = evt.detail.elt;
                    if (form.id === 'upload-form') {
                        const btn = form.querySelector('button[type="submit"]');
                        if (btn) {
                            btn.disabled = true;
                            btn.textContent = 'Uploading...';
                        }
                    }
                });

                document.body.addEventListener('htmx:afterRequest', function(evt) {
                    const form = evt.detail.elt;
                    if (form.id === 'upload-form') {
                        // Reset form after successful upload
                        form.reset();
                        // Re-enable button
                        const btn = form.querySelector('button[type="submit"]');
                        if (btn) {
                            btn.disabled = false;
                            btn.textContent = 'Upload & Submit';
                        }
                        // Refresh assignments grid
                        htmx.trigger('#assignments-grid-container', 'load');
                    }
                });
            """)
            ),
            cls="container mx-auto mt-8 p-4",
        )

        # Create navbar
        navbar = create_navbar_for_request(request, active_page="assignments")

        return Div(navbar, dashboard)

    # ========================================================================
    # ASSIGNMENT DETAIL VIEW - HTMX-powered
    # ========================================================================

    @rt("/assignments/{uid}")
    async def assignment_detail(request: Request, uid: str) -> Any:
        """
        Assignment detail view.

        Shows:
        - Assignment metadata (loaded via HTMX)
        - Processing status and duration
        - Processed content (formatted)
        - Download links for original and processed files
        """
        require_authenticated_user(request)  # Enforce authentication
        # Detail view card with HTMX loading
        detail_card = Div(
            Div(
                H3("Assignment Details", cls="card-title"),
                # Assignment info container (loaded via HTMX)
                Div(
                    P("Loading assignment details...", cls="text-center text-base-content/60"),
                    id="assignment-info",
                    cls="mb-4",
                    **{
                        "hx-get": f"/assignments/{uid}/info",
                        "hx-trigger": "load",
                        "hx-swap": "outerHTML",
                    },
                ),
                # Processed content section (loaded via HTMX)
                Div(
                    H4("Processed Content", cls="mt-6 mb-4"),
                    Div(
                        P("Loading content...", cls="text-center text-base-content/60"),
                        id="processed-content",
                        cls="p-4 bg-base-200 rounded-lg",
                        style="max-height: 600px; overflow-y: auto;",
                        **{
                            "hx-get": f"/assignments/{uid}/content",
                            "hx-trigger": "load",
                            "hx-swap": "outerHTML",
                        },
                    ),
                    id="content-section",
                    cls="mb-4",
                ),
                # Action buttons - use proper link instead of onclick
                Div(
                    A(
                        "← Back to Assignments",
                        href="/assignments",
                        cls="btn btn-ghost",
                    ),
                    cls="mt-4",
                ),
                cls="card-body",
            ),
            cls="card bg-base-100 shadow-sm",
        )

        # Main detail layout
        detail_view = Container(
            Div(
                H1("Assignment Details", cls="text-3xl font-bold"),
                P(f"UID: {uid}", cls="text-lg text-base-content/60"),
                cls="text-center mb-8",
            ),
            detail_card,
            cls="container mx-auto mt-8 p-4",
        )

        navbar = create_navbar_for_request(request, active_page="assignments")
        return Div(navbar, detail_view)

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/assignments/upload")
    async def upload_assignment(request: Request) -> Any:
        """HTMX endpoint for assignment file upload."""
        try:
            form = await request.form()
            uploaded_file = form.get("file")
            assignment_type = form.get("assignment_type", "transcript")
            processor_type = form.get("processor_type", "automatic")
            auto_process = form.get("auto_process") == "on"

            if not uploaded_file or not isinstance(uploaded_file, UploadFile):
                return _render_upload_status("error", "No file provided", is_error=True)

            user_uid = require_authenticated_user(request)  # Enforce authentication
            file_content = await uploaded_file.read()
            filename = uploaded_file.filename or "unknown"

            logger.info(f"Assignment upload: {filename} ({len(file_content)} bytes)")

            # Submit the assignment
            result = await _assignment_service.submit_file(
                file_content=file_content,
                original_filename=filename,
                user_uid=user_uid,
                assignment_type=assignment_type,
                processor_type=processor_type,
                auto_process=auto_process,
            )

            if result.is_error:
                return _render_upload_status("error", str(result.error), is_error=True)

            assignment = result.value
            return _render_upload_status(
                status=assignment.status,
                message="File uploaded successfully",
                assignment_uid=assignment.uid,
            )

        except Exception as e:
            logger.error(f"Error uploading assignment: {e}", exc_info=True)
            return _render_upload_status("error", f"Upload failed: {e}", is_error=True)

    @rt("/assignments/grid")
    async def get_assignments_grid(request: Request) -> Any:
        """HTMX endpoint for loading assignments grid with filters."""
        try:
            user_uid = require_authenticated_user(request)  # Enforce authentication

            # Get filter parameters from query string
            assignment_type = request.query_params.get("assignment_type", "")
            status = request.query_params.get("status", "")

            # Build filter kwargs
            kwargs = {"user_uid": user_uid, "limit": 50}
            if assignment_type:
                kwargs["assignment_type"] = assignment_type
            if status:
                kwargs["status"] = status

            result = await _assignment_service.list_assignments(**kwargs)

            if result.is_error:
                return Div(
                    P("Failed to load assignments", cls="text-center text-error"),
                    id="assignments-grid-container",
                )

            assignments = result.value or []
            return _render_assignments_grid(assignments)

        except Exception as e:
            logger.error(f"Error loading assignments: {e}", exc_info=True)
            return Div(
                P(f"Error: {e}", cls="text-center text-error"),
                id="assignments-grid-container",
            )

    @rt("/assignments/{uid}/info")
    async def get_assignment_info(request: Request, uid: str) -> Any:
        """HTMX endpoint for loading assignment detail info."""
        try:
            result = await _assignment_service.get_assignment(uid)

            if result.is_error:
                return Div(
                    Div(
                        P(f"Failed to load assignment: {result.error}"),
                        cls="alert alert-error",
                    ),
                    id="assignment-info",
                )

            assignment = result.value
            return _render_assignment_detail(assignment)

        except Exception as e:
            logger.error(f"Error loading assignment info: {e}", exc_info=True)
            return Div(
                Div(
                    P(f"Error: {e}"),
                    cls="alert alert-error",
                ),
                id="assignment-info",
            )

    @rt("/assignments/{uid}/content")
    async def get_assignment_content(request: Request, uid: str) -> Any:
        """HTMX endpoint for loading assignment processed content."""
        try:
            result = await _assignment_service.get_assignment(uid)

            if result.is_error:
                return _render_processed_content(None, False)

            assignment = result.value
            content = assignment.processed_content if assignment else None
            return _render_processed_content(content, bool(content))

        except Exception as e:
            logger.error(f"Error loading assignment content: {e}", exc_info=True)
            return _render_processed_content(None, False)

    logger.info("Assignments UI routes created successfully")

    return [
        assignments_dashboard,
        assignment_detail,
        upload_assignment,
        get_assignments_grid,
        get_assignment_info,
        get_assignment_content,
    ]
