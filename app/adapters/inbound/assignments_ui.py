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

from dataclasses import dataclass
from typing import Any

from fasthtml.common import (
    H1,
    H3,
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

from core.auth import require_authenticated_user
from core.ui.daisy_components import Button, ButtonT
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage

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


def _render_assignment_card(assignment: Any, is_pinned: bool = False) -> Any:
    """
    Render a single assignment card.

    Args:
        assignment: Assignment entity
        is_pinned: Whether this assignment is pinned
    """
    from components.shared.pin_button import PinButton

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
                    PinButton(entity_uid=assignment.uid, is_pinned=is_pinned, size="xs"),
                    A(
                        "View",
                        href=f"/assignments/{assignment.uid}",
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
                P("Filename", cls="text-xs text-base-content/60 mb-0"),
                P(assignment.original_filename, cls="mb-0 font-bold"),
            ),
            Div(
                P("Status", cls="text-xs text-base-content/60 mb-0"),
                P(
                    Span(
                        assignment.status,
                        cls=f"badge {_get_status_badge_class(assignment.status)}",
                    ),
                    cls="mb-0",
                ),
            ),
            Div(
                P("Type", cls="text-xs text-base-content/60 mb-0"),
                P(assignment.assignment_type, cls="mb-0"),
            ),
            Div(
                P("File Size", cls="text-xs text-base-content/60 mb-0"),
                P(f"{file_size_mb:.2f} MB", cls="mb-0"),
            ),
            Div(
                P("Processing Duration", cls="text-xs text-base-content/60 mb-0"),
                P(f"{processing_duration or 'N/A'} seconds", cls="mb-0"),
            ),
            Div(
                P("Created", cls="text-xs text-base-content/60 mb-0"),
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


def _render_category_selector(assignment: Any) -> Any:
    """Render category selector for assignment."""
    current_category = (
        getattr(assignment.metadata, "category", None) if hasattr(assignment, "metadata") else None
    )
    categories = ["daily", "weekly", "reflection", "work", "personal", "other"]

    return Div(
        Label("Category:", cls="label"),
        Select(
            *[
                Option(cat.title(), value=cat, selected=(cat == current_category))
                for cat in categories
            ],
            cls="select select-bordered w-full",
            hx_post=f"/api/assignments/categorize?assignment_uid={assignment.uid}&user_uid={assignment.user_uid}",
            hx_trigger="change",
            hx_target=f"#category-display-{assignment.uid}",
            hx_swap="outerHTML",
            hx_vals="js:{category: event.target.value}",
        ),
        id=f"category-selector-{assignment.uid}",
        cls="form-control",
    )


def _render_category_display(assignment: Any) -> Any:
    """Render category display with edit button."""
    current_category = (
        getattr(assignment.metadata, "category", "none")
        if hasattr(assignment, "metadata")
        else "none"
    )

    return Div(
        Span(f"Category: {current_category.title()}", cls="badge badge-primary"),
        Button(
            "Change",
            cls="btn btn-xs btn-ghost ml-2",
            hx_get=f"/assignments/{assignment.uid}/category-selector",
            hx_target=f"#category-display-{assignment.uid}",
            hx_swap="outerHTML",
        ),
        id=f"category-display-{assignment.uid}",
    )


def _render_tags_manager(assignment: Any) -> Any:
    """Render tags manager for assignment."""
    tags = getattr(assignment.metadata, "tags", []) if hasattr(assignment, "metadata") else []

    tag_elements = [
        Span(
            tag,
            Button(
                "×",
                cls="btn btn-xs btn-ghost ml-1",
                hx_post=f"/api/assignments/tags/remove?assignment_uid={assignment.uid}&user_uid={assignment.user_uid}",
                hx_vals=f'js:{{tags: ["{tag}"]}}',
                hx_target=f"#tags-manager-{assignment.uid}",
                hx_swap="outerHTML",
            ),
            cls="badge badge-secondary mr-2 mb-2",
        )
        for tag in tags
    ]

    return Div(
        Div(*tag_elements, cls="flex flex-wrap")
        if tags
        else Div("No tags", cls="text-sm text-base-content/60"),
        Form(
            Input(
                type="text",
                name="new_tag",
                placeholder="Add tag...",
                cls="input input-bordered input-sm w-full max-w-xs",
            ),
            Button("Add Tag", type="submit", cls="btn btn-primary btn-sm ml-2"),
            cls="flex items-center mt-2",
            hx_post=f"/api/assignments/tags/add?assignment_uid={assignment.uid}&user_uid={assignment.user_uid}",
            hx_vals="js:{tags: [document.querySelector('[name=\"new_tag\"]').value]}",
            hx_target=f"#tags-manager-{assignment.uid}",
            hx_swap="outerHTML",
        ),
        id=f"tags-manager-{assignment.uid}",
        cls="p-4 bg-base-200 rounded-lg",
    )


def _render_status_buttons(assignment: Any) -> Any:
    """Render status workflow buttons (publish/archive/draft)."""
    current_status = assignment.status

    return Div(
        Div(
            Button(
                "📤 Publish",
                cls="btn btn-success btn-sm",
                hx_post=f"/api/assignments/publish?assignment_uid={assignment.uid}&user_uid={assignment.user_uid}",
                hx_target=f"#status-buttons-{assignment.uid}",
                hx_swap="outerHTML",
                disabled=(current_status == "published"),
            ),
            Button(
                "📁 Archive",
                cls="btn btn-warning btn-sm ml-2",
                hx_post=f"/api/assignments/archive?assignment_uid={assignment.uid}&user_uid={assignment.user_uid}",
                hx_target=f"#status-buttons-{assignment.uid}",
                hx_swap="outerHTML",
                disabled=(current_status == "archived"),
            ),
            Button(
                "📝 Mark as Draft",
                cls="btn btn-ghost btn-sm ml-2",
                hx_post=f"/api/assignments/draft?assignment_uid={assignment.uid}&user_uid={assignment.user_uid}",
                hx_target=f"#status-buttons-{assignment.uid}",
                hx_swap="outerHTML",
                disabled=(current_status == "draft"),
            ),
            cls="flex gap-2",
        ),
        Div(
            Span(
                f"Current status: {current_status}", cls="text-xs text-base-content/60 mt-2 block"
            ),
        ),
        id=f"status-buttons-{assignment.uid}",
        cls="p-4 bg-base-200 rounded-lg",
    )


# ============================================================================
# TYPED QUERY PARAMETERS
# ============================================================================


@dataclass
class AssignmentFilters:
    """Typed filters for assignment list queries."""

    assignment_type: str
    status: str


def parse_assignment_filters(request: Request) -> AssignmentFilters:
    """
    Extract assignment filter parameters from request query params.

    Args:
        request: Starlette request object

    Returns:
        Typed AssignmentFilters with defaults applied
    """
    return AssignmentFilters(
        assignment_type=request.query_params.get("assignment_type", ""),
        status=request.query_params.get("status", ""),
    )


# ============================================================================
# SHARING UI COMPONENTS (Phase 1: Assignment Portfolio)
# ============================================================================


def _render_visibility_dropdown(assignment: Any) -> Any:
    """
    Render visibility level dropdown.

    Only shows for completed assignments (quality control).
    Uses HTMX for instant updates.
    """
    current_visibility = getattr(assignment, "visibility", "private")
    is_shareable = getattr(assignment, "status", "") == "completed"

    if not is_shareable:
        return Div(
            Span("🔒 Private", cls="badge badge-ghost"),
            P(
                "Only completed assignments can be shared",
                cls="text-xs text-base-content/60 mt-1 mb-0",
            ),
            cls="mb-4",
        )

    visibility_options = [
        ("private", "🔒 Private", "Only you can see"),
        ("shared", "👥 Shared", "Specific users only"),
        ("public", "🌐 Public", "Portfolio showcase"),
    ]

    return Div(
        Label("Visibility:", cls="label label-text font-bold"),
        Select(
            *[
                Option(
                    label,
                    value=val,
                    selected=(val == current_visibility),
                )
                for val, label, _desc in visibility_options
            ],
            name="visibility",
            cls="select select-bordered w-full",
            hx_post="/api/assignments/set-visibility",
            hx_trigger="change",
            hx_vals=f"js:{{assignment_uid: '{assignment.uid}', visibility: event.target.value}}",
            hx_target="#visibility-status",
            hx_swap="innerHTML",
        ),
        Div(
            P(
                next(
                    (desc for val, _lbl, desc in visibility_options if val == current_visibility),
                    "",
                ),
                cls="text-xs text-base-content/60 mb-0",
            ),
            id="visibility-status",
            cls="mt-1",
        ),
        cls="form-control mb-4",
    )


def _render_share_modal(assignment_uid: str) -> Any:
    """
    Render modal for sharing assignment with a user.

    Uses Alpine.js for modal state management.
    HTMX for form submission.
    """
    return Div(
        # Modal structure (DaisyUI modal with Alpine.js x-show)
        Div(
            Div(
                # Modal box
                Div(
                    # Close button
                    Form(
                        Button(
                            "✕",
                            cls="btn btn-sm btn-circle btn-ghost absolute right-2 top-2",
                            **{"@click": "shareModal = false"},
                        ),
                        method="dialog",
                    ),
                    # Modal content
                    H3("Share Assignment", cls="font-bold text-lg mb-4"),
                    # Share form
                    Form(
                        Div(
                            Label("User UID:", cls="label label-text"),
                            Input(
                                type="text",
                                name="recipient_uid",
                                placeholder="user_teacher",
                                cls="input input-bordered w-full",
                                required=True,
                            ),
                            cls="form-control mb-3",
                        ),
                        Div(
                            Label("Role:", cls="label label-text"),
                            Select(
                                Option("Viewer", value="viewer", selected=True),
                                Option("Teacher", value="teacher"),
                                Option("Peer", value="peer"),
                                Option("Mentor", value="mentor"),
                                name="role",
                                cls="select select-bordered w-full",
                            ),
                            cls="form-control mb-4",
                        ),
                        Div(
                            Button(
                                "Cancel",
                                type="button",
                                cls="btn btn-ghost",
                                **{"@click": "shareModal = false"},
                            ),
                            Button(
                                "Share",
                                type="submit",
                                cls="btn btn-primary",
                            ),
                            cls="flex gap-2 justify-end",
                        ),
                        hx_post="/api/assignments/share",
                        hx_vals=f"js:{{assignment_uid: '{assignment_uid}', recipient_uid: document.querySelector('input[name=recipient_uid]').value, role: document.querySelector('select[name=role]').value}}",
                        hx_target="#shared-users-list",
                        hx_swap="innerHTML",
                        **{
                            "@submit.prevent": "$el.dispatchEvent(new Event('htmx:trigger')); shareModal = false"
                        },
                    ),
                    cls="modal-box",
                ),
                cls="modal-backdrop",
                **{"@click": "shareModal = false"},
            ),
            cls="modal",
            **{"x-show": "shareModal", "x-cloak": ""},
        ),
        # Open modal button
        Button(
            "👥 Share with User",
            cls="btn btn-primary btn-sm",
            **{"@click": "shareModal = true"},
        ),
    )


def _render_shared_users_list(assignment_uid: str) -> Any:
    """
    Render list of users assignment is shared with.

    Loaded dynamically via HTMX on page load.
    """
    return Div(
        H4("Shared With", cls="font-bold mb-2"),
        Div(
            P("Loading shared users...", cls="text-base-content/60 text-sm"),
            id="shared-users-list",
            hx_get=f"/assignments/{assignment_uid}/shared-users",
            hx_trigger="load",
            hx_swap="innerHTML",
        ),
        cls="mt-4",
    )


def _render_sharing_section(assignment: Any) -> Any:
    """
    Render complete sharing section for assignment detail page.

    Includes:
    - Visibility dropdown
    - Share button (opens modal)
    - Shared users list

    Only shown for assignment owner.
    """
    return Div(
        H4("Sharing & Visibility", cls="font-bold text-lg mb-4"),
        Div(
            # Visibility controls
            _render_visibility_dropdown(assignment),
            # Share modal and button
            Div(
                _render_share_modal(assignment.uid),
                cls="mb-4",
            ),
            # Shared users list
            _render_shared_users_list(assignment.uid),
            cls="space-y-2",
        ),
        id="sharing-section",
        cls="card bg-base-200 p-4 rounded-lg mt-6",
        **{
            "x-data": "{ shareModal: false }",  # Alpine.js data for modal state
        },
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
                    # Knowledge Units selector (MVP - Phase C)
                    Div(
                        Label("Knowledge Units Applied (Optional)", cls="label"),
                        P(
                            "Link this assignment to Knowledge Units you're demonstrating",
                            cls="text-sm text-base-content/60 mb-2",
                        ),
                        Input(
                            type="text",
                            name="ku_selector_display",
                            placeholder="Search for Knowledge Units...",
                            cls="input input-bordered w-full",
                            **{
                                "hx-get": "/api/search/unified?type=ku",
                                "hx-trigger": "keyup changed delay:300ms",
                                "hx-target": "#ku-results",
                                "hx-include": "this",
                            },
                        ),
                        # Selected KUs display
                        Div(id="ku-selected", cls="flex flex-wrap gap-2 mt-2"),
                        # Search results dropdown
                        Div(id="ku-results", cls="mt-2"),
                        # Hidden input for form submission (comma-separated UIDs)
                        Input(
                            type="hidden",
                            name="applies_knowledge_uids",
                            id="ku-uids-input",
                            value="",
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

        # Main page content
        content = Div(
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
            # HTMX event handlers for UX polish (not core functionality)
            Script(
                NotStr("""
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
                        form.reset();
                        const btn = form.querySelector('button[type="submit"]');
                        if (btn) {
                            btn.disabled = false;
                            btn.textContent = 'Upload & Submit';
                        }
                        htmx.trigger('#assignments-grid-container', 'load');
                    }
                });
            """)
            ),
        )

        return await BasePage(
            content,
            title="Assignments",
            request=request,
            active_page="assignments",
        )

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
        - Sharing controls (visibility, share button, shared users)
        """
        user_uid = require_authenticated_user(request)  # Enforce authentication

        # Fetch assignment to determine if user is owner (for sharing controls)
        # Note: In production, this would use get_with_access_check()
        assignment_result = await _assignment_service.get_assignment(uid)
        is_owner = False
        if not assignment_result.is_error and assignment_result.value is not None:
            is_owner = assignment_result.value.user_uid == user_uid

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
                # Sharing section (only for owner)
                (
                    _render_sharing_section(assignment)
                    if is_owner and not assignment_result.is_error
                    else None
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

        content = Div(
            Div(
                H1("Assignment Details", cls="text-3xl font-bold"),
                P(f"UID: {uid}", cls="text-lg text-base-content/60"),
                cls="text-center mb-8",
            ),
            detail_card,
        )

        return await BasePage(
            content,
            title="Assignment Details",
            request=request,
            active_page="assignments",
        )

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

            # Parse typed filter parameters
            filters = parse_assignment_filters(request)

            # Build filter kwargs
            kwargs = {"user_uid": user_uid, "limit": 50}
            if filters.assignment_type:
                kwargs["assignment_type"] = filters.assignment_type
            if filters.status:
                kwargs["status"] = filters.status

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

    # ========================================================================
    # CONTENT MANAGEMENT UI ROUTES
    # ========================================================================

    @rt("/assignments/{uid}/category-selector")
    async def get_category_selector(request: Request, uid: str) -> Any:
        """HTMX endpoint for category selector."""
        try:
            result = await _assignment_service.get_assignment(uid)
            if result.is_error:
                return Div("Assignment not found", cls="text-error")

            assignment = result.value
            return _render_category_selector(assignment)

        except Exception as e:
            logger.error(f"Error loading category selector: {e}", exc_info=True)
            return Div("Error loading category selector", cls="text-error")

    @rt("/assignments/{uid}/tags-manager")
    async def get_tags_manager(request: Request, uid: str) -> Any:
        """HTMX endpoint for tags manager."""
        try:
            result = await _assignment_service.get_assignment(uid)
            if result.is_error:
                return Div("Assignment not found", cls="text-error")

            assignment = result.value
            return _render_tags_manager(assignment)

        except Exception as e:
            logger.error(f"Error loading tags manager: {e}", exc_info=True)
            return Div("Error loading tags manager", cls="text-error")

    @rt("/assignments/{uid}/shared-users")
    async def get_shared_users_ui(request: Request, uid: str) -> Any:
        """
        HTMX endpoint for rendering shared users list.

        Returns HTML fragment showing users the assignment is shared with.
        """
        try:
            _user_uid = require_authenticated_user(request)

            # Note: This would ideally use the sharing service
            # For now, return placeholder UI that will be populated via API
            return Div(
                P(
                    "Shared users list will appear here after sharing",
                    cls="text-sm text-base-content/60",
                ),
                Span("No users yet", cls="badge badge-ghost"),
                id="shared-users-content",
            )

        except Exception as e:
            logger.error(f"Error loading shared users: {e}", exc_info=True)
            return Div("Error loading shared users", cls="text-error text-sm")

    logger.info("Assignments UI routes created successfully")

    return [
        assignments_dashboard,
        assignment_detail,
        upload_assignment,
        get_assignments_grid,
        get_assignment_info,
        get_assignment_content,
        get_category_selector,
        get_tags_manager,
        get_shared_users_ui,
    ]
