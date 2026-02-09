"""
Reports UI Routes
=====================

File submission with sidebar navigation (Submit / Browse / Your Reports).
Regular users upload files here to share with teachers, peers, or mentors.
Processor type is auto-set to HUMAN — AI processing lives in Report Projects
(role-gated to TEACHER+).

Layout: Unified sidebar (Tailwind + Alpine) with 3 nav items.
Desktop: collapsible sidebar. Mobile: horizontal tabs.
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
from core.models.enums.report_enums import ProcessorType, ReportType
from core.ui.daisy_components import Button, ButtonT
from core.utils.logging import get_logger
from ui.patterns.page_header import PageHeader
from ui.patterns.sidebar import SidebarItem, SidebarPage

logger = get_logger("skuel.routes.reports.ui")


# ============================================================================
# HTMX FRAGMENT RENDERING FUNCTIONS
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
            H4("File Uploaded Successfully!", cls="mb-0"),
            P(f"Report ID: {report_uid}", cls="mb-0") if report_uid else None,
            P(f"Status: {status}", cls="mb-0"),
            cls="alert alert-success",
        ),
        id="upload-status",
    )


def _get_report_identifier(report: Any) -> str:
    """Extract the identifier from report metadata, falling back to report_type."""
    metadata = getattr(report, "metadata", None)
    if isinstance(metadata, dict):
        identifier = metadata.get("identifier")
        if identifier:
            return str(identifier)
    return getattr(report, "report_type", "unknown")


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


def _render_report_card(report: Any, is_pinned: bool = False) -> Any:
    """
    Render a single report card.

    Args:
        report: Report entity
        is_pinned: Whether this report is pinned
    """
    from components.shared.pin_button import PinButton

    file_size_mb = (report.file_size / 1024 / 1024) if hasattr(report, "file_size") else 0
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
                    PinButton(entity_uid=report.uid, is_pinned=is_pinned, size="xs"),
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
            P("No reports found.", cls="text-center text-base-content/60"),
            id="reports-grid-container",
        )

    return Div(
        *[_render_report_card(a) for a in reports],
        id="reports-grid-container",
    )


def _render_report_detail(report: Any) -> Any:
    """Render report detail info as HTML fragment."""
    file_size_mb = (report.file_size / 1024 / 1024) if hasattr(report, "file_size") else 0
    processing_duration = getattr(report, "processing_duration_seconds", None)
    created_at = getattr(report, "created_at", None)
    identifier = _get_report_identifier(report)

    return Div(
        Div(
            Div(
                P("Filename", cls="text-xs text-base-content/60 mb-0"),
                P(report.original_filename, cls="mb-0 font-bold"),
            ),
            Div(
                P("Identifier", cls="text-xs text-base-content/60 mb-0"),
                P(identifier, cls="mb-0 font-semibold"),
            ),
            Div(
                P("Status", cls="text-xs text-base-content/60 mb-0"),
                P(
                    Span(
                        report.status,
                        cls=f"badge {_get_status_badge_class(report.status)}",
                    ),
                    cls="mb-0",
                ),
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
        id="report-info",
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


def _render_category_selector(report: Any) -> Any:
    """Render category selector for report."""
    current_category = (
        getattr(report.metadata, "category", None) if hasattr(report, "metadata") else None
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
            hx_post=f"/api/reports/categorize?report_uid={report.uid}&user_uid={report.user_uid}",
            hx_trigger="change",
            hx_target=f"#category-display-{report.uid}",
            hx_swap="outerHTML",
            hx_vals="js:{category: event.target.value}",
        ),
        id=f"category-selector-{report.uid}",
        cls="form-control",
    )


def _render_category_display(report: Any) -> Any:
    """Render category display with edit button."""
    current_category = (
        getattr(report.metadata, "category", "none") if hasattr(report, "metadata") else "none"
    )

    return Div(
        Span(f"Category: {current_category.title()}", cls="badge badge-primary"),
        Button(
            "Change",
            cls="btn btn-xs btn-ghost ml-2",
            hx_get=f"/reports/{report.uid}/category-selector",
            hx_target=f"#category-display-{report.uid}",
            hx_swap="outerHTML",
        ),
        id=f"category-display-{report.uid}",
    )


def _render_tags_manager(report: Any) -> Any:
    """Render tags manager for report."""
    tags = getattr(report.metadata, "tags", []) if hasattr(report, "metadata") else []

    tag_elements = [
        Span(
            tag,
            Button(
                "\u00d7",
                cls="btn btn-xs btn-ghost ml-1",
                hx_post=f"/api/reports/tags/remove?report_uid={report.uid}&user_uid={report.user_uid}",
                hx_vals=f'js:{{tags: ["{tag}"]}}',
                hx_target=f"#tags-manager-{report.uid}",
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
            hx_post=f"/api/reports/tags/add?report_uid={report.uid}&user_uid={report.user_uid}",
            hx_vals="js:{tags: [document.querySelector('[name=\"new_tag\"]').value]}",
            hx_target=f"#tags-manager-{report.uid}",
            hx_swap="outerHTML",
        ),
        id=f"tags-manager-{report.uid}",
        cls="p-4 bg-base-200 rounded-lg",
    )


def _render_status_buttons(report: Any) -> Any:
    """Render status workflow buttons (publish/archive/draft)."""
    current_status = report.status

    return Div(
        Div(
            Button(
                "Publish",
                cls="btn btn-success btn-sm",
                hx_post=f"/api/reports/publish?report_uid={report.uid}&user_uid={report.user_uid}",
                hx_target=f"#status-buttons-{report.uid}",
                hx_swap="outerHTML",
                disabled=(current_status == "published"),
            ),
            Button(
                "Archive",
                cls="btn btn-warning btn-sm ml-2",
                hx_post=f"/api/reports/archive?report_uid={report.uid}&user_uid={report.user_uid}",
                hx_target=f"#status-buttons-{report.uid}",
                hx_swap="outerHTML",
                disabled=(current_status == "archived"),
            ),
            Button(
                "Mark as Draft",
                cls="btn btn-ghost btn-sm ml-2",
                hx_post=f"/api/reports/draft?report_uid={report.uid}&user_uid={report.user_uid}",
                hx_target=f"#status-buttons-{report.uid}",
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
        id=f"status-buttons-{report.uid}",
        cls="p-4 bg-base-200 rounded-lg",
    )


# ============================================================================
# TYPED QUERY PARAMETERS
# ============================================================================


@dataclass
class ReportFilters:
    """Typed filters for report list queries."""

    report_type: str
    status: str


def parse_report_filters(request: Request) -> ReportFilters:
    """
    Extract report filter parameters from request query params.

    Args:
        request: Starlette request object

    Returns:
        Typed ReportFilters with defaults applied
    """
    return ReportFilters(
        report_type=request.query_params.get("report_type", ""),
        status=request.query_params.get("status", ""),
    )


# ============================================================================
# SHARING UI COMPONENTS (Phase 1: Report Portfolio)
# ============================================================================


def _render_visibility_dropdown(report: Any) -> Any:
    """
    Render visibility level dropdown.

    Only shows for completed reports (quality control).
    Uses HTMX for instant updates.
    """
    current_visibility = getattr(report, "visibility", "private")
    is_shareable = getattr(report, "status", "") == "completed"

    if not is_shareable:
        return Div(
            Span("Private", cls="badge badge-ghost"),
            P(
                "Only completed reports can be shared",
                cls="text-xs text-base-content/60 mt-1 mb-0",
            ),
            cls="mb-4",
        )

    visibility_options = [
        ("private", "Private", "Only you can see"),
        ("shared", "Shared", "Specific users only"),
        ("public", "Public", "Portfolio showcase"),
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
            hx_post="/api/reports/set-visibility",
            hx_trigger="change",
            hx_vals=f"js:{{report_uid: '{report.uid}', visibility: event.target.value}}",
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


def _render_share_modal(report_uid: str) -> Any:
    """
    Render modal for sharing report with a user.

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
                            "\u2715",
                            cls="btn btn-sm btn-circle btn-ghost absolute right-2 top-2",
                            **{"@click": "shareModal = false"},
                        ),
                        method="dialog",
                    ),
                    # Modal content
                    H3("Share Report", cls="font-bold text-lg mb-4"),
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
                        hx_post="/api/reports/share",
                        hx_vals=f"js:{{report_uid: '{report_uid}', recipient_uid: document.querySelector('input[name=recipient_uid]').value, role: document.querySelector('select[name=role]').value}}",
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
            "Share with User",
            cls="btn btn-primary btn-sm",
            **{"@click": "shareModal = true"},
        ),
    )


def _render_shared_users_list(report_uid: str) -> Any:
    """
    Render list of users report is shared with.

    Loaded dynamically via HTMX on page load.
    """
    return Div(
        H4("Shared With", cls="font-bold mb-2"),
        Div(
            P("Loading shared users...", cls="text-base-content/60 text-sm"),
            id="shared-users-list",
            hx_get=f"/reports/{report_uid}/shared-users",
            hx_trigger="load",
            hx_swap="innerHTML",
        ),
        cls="mt-4",
    )


def _render_sharing_section(report: Any) -> Any:
    """
    Render complete sharing section for report detail page.

    Includes:
    - Visibility dropdown
    - Share button (opens modal)
    - Shared users list

    Only shown for report owner.
    """
    return Div(
        H4("Sharing & Visibility", cls="font-bold text-lg mb-4"),
        Div(
            # Visibility controls
            _render_visibility_dropdown(report),
            # Share modal and button
            Div(
                _render_share_modal(report.uid),
                cls="mb-4",
            ),
            # Shared users list
            _render_shared_users_list(report.uid),
            cls="space-y-2",
        ),
        id="sharing-section",
        cls="card bg-base-200 p-4 rounded-lg mt-6",
        **{
            "x-data": "{ shareModal: false }",  # Alpine.js data for modal state
        },
    )


# ============================================================================
# SIDEBAR NAVIGATION
# ============================================================================

REPORTS_SIDEBAR_ITEMS = [
    SidebarItem("Submit", "/reports/submit", "submit", icon="📤"),
    SidebarItem("Browse", "/reports/browse", "browse", icon="📂"),
    SidebarItem("Your Reports", "/reports/yours", "yours", icon="📋"),
]


# ============================================================================
# CONTENT FRAGMENTS (extracted from former monolithic dashboard)
# ============================================================================


def _render_upload_form() -> Any:
    """Render the file upload form card."""
    return Div(
        Div(
            Form(
                # Identifier input (loose KU reference)
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
                # Submit button
                Div(
                    Button(
                        "Submit for Review",
                        variant=ButtonT.primary,
                        type="submit",
                    ),
                    cls="text-center",
                ),
                # Upload status (HTMX target)
                Div(id="upload-status", cls="mt-4 text-center"),
                # HTMX attributes for form submission
                **{
                    "hx-post": "/reports/upload",
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
                    btn.textContent = 'Uploading...';
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
                    btn.textContent = 'Submit for Review';
                }
                htmx.trigger('#reports-grid-container', 'load');
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
                        Option("Manual Review", value="manual_review"),
                        name="status",
                        cls="select select-bordered w-full",
                    ),
                    cls="mb-2",
                ),
                **{
                    "hx-get": "/reports/grid",
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
        P("Loading reports...", cls="text-center text-base-content/60"),
        id="reports-grid-container",
        cls="mt-4",
        **{
            "hx-get": "/reports/grid",
            "hx-trigger": "load",
            "hx-swap": "outerHTML",
        },
    )


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_reports_ui_routes(_app, rt, _report_service, _processing_service):
    """
    Create all report UI routes.

    Args:
        app: FastHTML application instance
        rt: Router instance
        report_service: ReportSubmissionService
        processing_service: ReportProcessorService
    """

    logger.info("Creating Reports UI routes")

    # ========================================================================
    # SIDEBAR PAGES
    # ========================================================================

    @rt("/reports")
    async def reports_landing(request: Request) -> Any:
        """Reports landing — defaults to Submit page."""
        return await _render_submit_page(request)

    @rt("/reports/submit")
    async def reports_submit_page(request: Request) -> Any:
        """Submit page: upload form."""
        return await _render_submit_page(request)

    async def _render_submit_page(request: Request) -> Any:
        require_authenticated_user(request)
        content = Div(
            PageHeader("Submit Report", subtitle="Upload a file linked to a Knowledge Unit"),
            _render_upload_form(),
            _upload_form_script(),
        )
        return await SidebarPage(
            content=content,
            items=REPORTS_SIDEBAR_ITEMS,
            active="submit",
            title="Reports",
            subtitle="Submit and manage files",
            storage_key="reports-sidebar",
            page_title="Submit Report",
            request=request,
            active_page="reports",
            title_href="/reports",
        )

    @rt("/reports/browse")
    async def reports_browse_page(request: Request) -> Any:
        """Browse page: filters + results grid."""
        require_authenticated_user(request)
        content = Div(
            PageHeader("Browse Reports", subtitle="Filter and find reports"),
            _render_filters_section(),
            _render_reports_grid_container(),
        )
        return await SidebarPage(
            content=content,
            items=REPORTS_SIDEBAR_ITEMS,
            active="browse",
            title="Reports",
            subtitle="Submit and manage files",
            storage_key="reports-sidebar",
            page_title="Browse Reports",
            request=request,
            active_page="reports",
            title_href="/reports",
        )

    @rt("/reports/yours")
    async def reports_yours_page(request: Request) -> Any:
        """Your Reports page: full listing without filters."""
        require_authenticated_user(request)
        content = Div(
            PageHeader("Your Reports", subtitle="View and manage your submitted files"),
            _render_reports_grid_container(),
        )
        return await SidebarPage(
            content=content,
            items=REPORTS_SIDEBAR_ITEMS,
            active="yours",
            title="Reports",
            subtitle="Submit and manage files",
            storage_key="reports-sidebar",
            page_title="Your Reports",
            request=request,
            active_page="reports",
            title_href="/reports",
        )

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/reports/upload")
    async def upload_report(request: Request) -> Any:
        """HTMX endpoint for report file upload (human review)."""
        try:
            form = await request.form()
            uploaded_file = form.get("file")
            identifier = (form.get("identifier") or "").strip()

            if not identifier:
                return _render_upload_status("error", "Identifier is required", is_error=True)

            if not uploaded_file or not isinstance(uploaded_file, UploadFile):
                return _render_upload_status("error", "No file provided", is_error=True)

            user_uid = require_authenticated_user(request)
            file_content = await uploaded_file.read()
            filename = uploaded_file.filename or "unknown"

            logger.info(
                f"Report upload: {filename} ({len(file_content)} bytes, identifier={identifier})"
            )

            # Submit for human review — processor_type always HUMAN for regular users
            result = await _report_service.submit_file(
                file_content=file_content,
                original_filename=filename,
                user_uid=user_uid,
                report_type=ReportType.ASSIGNMENT,
                processor_type=ProcessorType.HUMAN,
                metadata={"identifier": identifier},
            )

            if result.is_error:
                return _render_upload_status("error", str(result.error), is_error=True)

            report = result.value
            return _render_upload_status(
                status=report.status,
                message="File uploaded successfully",
                report_uid=report.uid,
            )

        except Exception as e:
            logger.error(f"Error uploading report: {e}", exc_info=True)
            return _render_upload_status("error", f"Upload failed: {e}", is_error=True)

    @rt("/reports/grid")
    async def get_reports_grid(request: Request) -> Any:
        """HTMX endpoint for loading reports grid with filters."""
        try:
            user_uid = require_authenticated_user(request)  # Enforce authentication

            # Parse typed filter parameters
            filters = parse_report_filters(request)

            # Build filter kwargs
            kwargs = {"user_uid": user_uid, "limit": 50}
            if filters.report_type:
                kwargs["report_type"] = filters.report_type
            if filters.status:
                kwargs["status"] = filters.status

            result = await _report_service.list_reports(**kwargs)

            if result.is_error:
                return Div(
                    P("Failed to load reports", cls="text-center text-error"),
                    id="reports-grid-container",
                )

            reports = result.value or []
            return _render_reports_grid(reports)

        except Exception as e:
            logger.error(f"Error loading reports: {e}", exc_info=True)
            return Div(
                P(f"Error: {e}", cls="text-center text-error"),
                id="reports-grid-container",
            )

    @rt("/reports/{uid}/info")
    async def get_report_info(request: Request, uid: str) -> Any:
        """HTMX endpoint for loading report detail info."""
        try:
            result = await _report_service.get_report(uid)

            if result.is_error:
                return Div(
                    Div(
                        P(f"Failed to load report: {result.error}"),
                        cls="alert alert-error",
                    ),
                    id="report-info",
                )

            report = result.value
            if not report:
                return Div(
                    Div(
                        P(f"Report {uid} not found"),
                        cls="alert alert-warning",
                    ),
                    id="report-info",
                )
            return _render_report_detail(report)

        except Exception as e:
            logger.error(f"Error loading report info: {e}", exc_info=True)
            return Div(
                Div(
                    P(f"Error: {e}"),
                    cls="alert alert-error",
                ),
                id="report-info",
            )

    @rt("/reports/{uid}/content")
    async def get_report_content(request: Request, uid: str) -> Any:
        """HTMX endpoint for loading report processed content."""
        try:
            result = await _report_service.get_report(uid)

            if result.is_error or not result.value:
                return _render_processed_content(None, False)

            report = result.value
            content = report.processed_content if report else None
            return _render_processed_content(content, bool(content))

        except Exception as e:
            logger.error(f"Error loading report content: {e}", exc_info=True)
            return _render_processed_content(None, False)

    # ========================================================================
    # CONTENT MANAGEMENT UI ROUTES
    # ========================================================================

    @rt("/reports/{uid}/category-selector")
    async def get_category_selector(request: Request, uid: str) -> Any:
        """HTMX endpoint for category selector."""
        try:
            result = await _report_service.get_report(uid)
            if result.is_error:
                return Div("Report not found", cls="text-error")

            report = result.value
            return _render_category_selector(report)

        except Exception as e:
            logger.error(f"Error loading category selector: {e}", exc_info=True)
            return Div("Error loading category selector", cls="text-error")

    @rt("/reports/{uid}/tags-manager")
    async def get_tags_manager(request: Request, uid: str) -> Any:
        """HTMX endpoint for tags manager."""
        try:
            result = await _report_service.get_report(uid)
            if result.is_error:
                return Div("Report not found", cls="text-error")

            report = result.value
            return _render_tags_manager(report)

        except Exception as e:
            logger.error(f"Error loading tags manager: {e}", exc_info=True)
            return Div("Error loading tags manager", cls="text-error")

    @rt("/reports/{uid}/shared-users")
    async def get_shared_users_ui(request: Request, uid: str) -> Any:
        """
        HTMX endpoint for rendering shared users list.

        Returns HTML fragment showing users the report is shared with.
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

    # ========================================================================
    # REPORT DETAIL VIEW - HTMX-powered
    # ========================================================================
    # IMPORTANT: This route MUST be defined LAST because /reports/{uid}
    # is a catch-all pattern that would match specific routes like
    # /reports/grid, /reports/upload, etc.
    # ========================================================================

    @rt("/reports/{uid}")
    async def report_detail(request: Request, uid: str) -> Any:
        """
        Report detail view.

        Shows:
        - Report metadata (loaded via HTMX)
        - Processing status and duration
        - Processed content (formatted)
        - Download links for original and processed files
        - Sharing controls (visibility, share button, shared users)
        """
        user_uid = require_authenticated_user(request)  # Enforce authentication

        # Fetch report to determine if user is owner (for sharing controls)
        # Note: In production, this would use get_with_access_check()
        report_result = await _report_service.get_report(uid)
        is_owner = False
        if not report_result.is_error and report_result.value is not None:
            is_owner = report_result.value.user_uid == user_uid

        # Detail view card with HTMX loading
        detail_card = Div(
            Div(
                H3("Report Details", cls="card-title"),
                # Report info container (loaded via HTMX)
                Div(
                    P("Loading report details...", cls="text-center text-base-content/60"),
                    id="report-info",
                    cls="mb-4",
                    **{
                        "hx-get": f"/reports/{uid}/info",
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
                            "hx-get": f"/reports/{uid}/content",
                            "hx-trigger": "load",
                            "hx-swap": "outerHTML",
                        },
                    ),
                    id="content-section",
                    cls="mb-4",
                ),
                # Sharing section (only for owner)
                (
                    _render_sharing_section(report_result.value)
                    if is_owner and not report_result.is_error
                    else None
                ),
                # Action buttons - use proper link instead of onclick
                Div(
                    A(
                        "\u2190 Back to Reports",
                        href="/reports",
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
                H1("Report Details", cls="text-3xl font-bold"),
                P(f"UID: {uid}", cls="text-lg text-base-content/60"),
                cls="text-center mb-8",
            ),
            detail_card,
        )

        return await BasePage(
            content,
            title="Report Details",
            request=request,
            active_page="reports",
        )

    logger.info("Reports UI routes created successfully")

    # Route order matters! Specific routes must come BEFORE parameterized routes.
    # Otherwise /reports/grid would match /reports/{uid} with uid="grid"
    return [
        reports_landing,  # /reports (exact)
        reports_submit_page,  # /reports/submit (specific)
        reports_browse_page,  # /reports/browse (specific)
        reports_yours_page,  # /reports/yours (specific)
        upload_report,  # /reports/upload (specific, HTMX POST)
        get_reports_grid,  # /reports/grid (specific, HTMX GET)
        get_report_info,  # /reports/{uid}/info (pattern + suffix)
        get_report_content,  # /reports/{uid}/content (pattern + suffix)
        get_category_selector,  # /reports/{uid}/category-selector (pattern + suffix)
        get_tags_manager,  # /reports/{uid}/tags-manager (pattern + suffix)
        get_shared_users_ui,  # /reports/{uid}/shared-users (pattern + suffix)
        report_detail,  # /reports/{uid} (catch-all - MUST BE LAST)
    ]
