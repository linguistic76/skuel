"""
Submissions UI Routes
=====================

File submission with sidebar navigation (Submit / Browse / Your Submissions).
Regular users upload files here to share with teachers, peers, or mentors.
Processor type is auto-set to HUMAN — AI processing lives in Report Projects
(role-gated to TEACHER+).

Layout: Unified sidebar (Tailwind + Alpine) with 5 nav items.
Desktop: collapsible sidebar. Mobile: horizontal tabs.
"""

from dataclasses import dataclass
from datetime import date
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

from adapters.inbound.auth import require_authenticated_user
from core.models.enums.entity_enums import EntityType, ProcessorType
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonT
from ui.layouts.base_page import BasePage
from ui.patterns.page_header import PageHeader
from ui.patterns.sidebar import SidebarItem, SidebarPage

logger = get_logger("skuel.routes.submissions.ui")


# ============================================================================
# HTMX FRAGMENT RENDERING FUNCTIONS
# ============================================================================


def _render_upload_status(
    status: str,
    message: str,
    submission_uid: str | None = None,
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
            P(f"Submission ID: {submission_uid}", cls="mb-0") if submission_uid else None,
            P(f"Status: {status}", cls="mb-0"),
            cls="alert alert-success",
        ),
        id="upload-status",
    )


def _get_submission_identifier(submission: Any) -> str:
    """Extract the identifier from submission metadata, falling back to report_type."""
    metadata = getattr(submission, "metadata", None)
    if isinstance(metadata, dict):
        identifier = metadata.get("identifier")
        if identifier:
            return str(identifier)
    return getattr(submission, "report_type", "unknown")


def _get_status_badge_class(status: str) -> str:
    """Get DaisyUI badge class for submission status."""
    classes = {
        "submitted": "badge-warning",
        "queued": "badge-warning",
        "processing": "badge-info",
        "completed": "badge-success",
        "failed": "badge-error",
        "manual_review": "badge-ghost",
    }
    return classes.get(status, "badge-ghost")


def _render_submission_card(submission: Any, is_pinned: bool = False) -> Any:
    """
    Render a single submission card.

    Args:
        submission: Submission entity
        is_pinned: Whether this submission is pinned
    """
    from ui.patterns.pin_button import PinButton

    file_size_mb = (submission.file_size / 1024 / 1024) if submission.file_size else 0
    identifier = _get_submission_identifier(submission)
    return Div(
        Div(
            Div(
                Div(
                    H4(submission.original_filename, cls="mb-0 font-semibold"),
                    P(
                        f"{identifier} \u2022 {file_size_mb:.2f} MB",
                        cls="text-sm text-base-content/60 mb-0",
                    ),
                    cls="flex-1",
                ),
                Div(
                    Span(
                        submission.status,
                        cls=f"badge {_get_status_badge_class(submission.status)}",
                    ),
                ),
                Div(
                    PinButton(entity_uid=submission.uid, is_pinned=is_pinned, size="xs"),
                    A(
                        "View",
                        href=f"/submissions/{submission.uid}",
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


def _render_submissions_grid(submissions: list[Any]) -> Any:
    """Render submissions grid as HTML fragment for HTMX swap."""
    if not submissions:
        return Div(
            P("No submissions found.", cls="text-center text-base-content/60"),
            id="submissions-grid-container",
        )

    return Div(
        *[_render_submission_card(a) for a in submissions],
        id="submissions-grid-container",
    )


def _render_submission_detail(submission: Any) -> Any:
    """Render submission detail info as HTML fragment."""
    file_size_mb = (submission.file_size / 1024 / 1024) if submission.file_size else 0
    processing_duration = getattr(submission, "processing_duration_seconds", None)
    created_at = getattr(submission, "created_at", None)
    identifier = _get_submission_identifier(submission)

    return Div(
        Div(
            Div(
                P("Filename", cls="text-xs text-base-content/60 mb-0"),
                P(submission.original_filename, cls="mb-0 font-bold"),
            ),
            Div(
                P("Identifier", cls="text-xs text-base-content/60 mb-0"),
                P(identifier, cls="mb-0 font-semibold"),
            ),
            Div(
                P("Status", cls="text-xs text-base-content/60 mb-0"),
                P(
                    Span(
                        submission.status,
                        cls=f"badge {_get_status_badge_class(submission.status)}",
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
        id="submission-info",
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


def _render_category_selector(submission: Any) -> Any:
    """Render category selector for submission."""
    current_category = submission.metadata.get("category") if submission.metadata else None
    categories = ["daily", "weekly", "reflection", "work", "personal", "other"]

    return Div(
        Label("Category:", cls="label"),
        Select(
            *[
                Option(cat.title(), value=cat, selected=(cat == current_category))
                for cat in categories
            ],
            cls="select select-bordered w-full",
            hx_post=f"/api/submissions/categorize?submission_uid={submission.uid}&user_uid={submission.user_uid}",
            hx_trigger="change",
            hx_target=f"#category-display-{submission.uid}",
            hx_swap="outerHTML",
            hx_vals="js:{category: event.target.value}",
        ),
        id=f"category-selector-{submission.uid}",
        cls="form-control",
    )


def _render_category_display(submission: Any) -> Any:
    """Render category display with edit button."""
    current_category = (
        submission.metadata.get("category", "none") if submission.metadata else "none"
    )

    return Div(
        Span(f"Category: {current_category.title()}", cls="badge badge-primary"),
        Button(
            "Change",
            cls="btn btn-xs btn-ghost ml-2",
            hx_get=f"/submissions/{submission.uid}/category-selector",
            hx_target=f"#category-display-{submission.uid}",
            hx_swap="outerHTML",
        ),
        id=f"category-display-{submission.uid}",
    )


def _render_tags_manager(submission: Any) -> Any:
    """Render tags manager for submission."""
    tags = submission.metadata.get("tags", []) if submission.metadata else []

    tag_elements = [
        Span(
            tag,
            Button(
                "\u00d7",
                cls="btn btn-xs btn-ghost ml-1",
                hx_post=f"/api/submissions/tags/remove?submission_uid={submission.uid}&user_uid={submission.user_uid}",
                hx_vals=f'js:{{tags: ["{tag}"]}}',
                hx_target=f"#tags-manager-{submission.uid}",
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
            hx_post=f"/api/submissions/tags/add?submission_uid={submission.uid}&user_uid={submission.user_uid}",
            hx_vals="js:{tags: [document.querySelector('[name=\"new_tag\"]').value]}",
            hx_target=f"#tags-manager-{submission.uid}",
            hx_swap="outerHTML",
        ),
        id=f"tags-manager-{submission.uid}",
        cls="p-4 bg-base-200 rounded-lg",
    )


def _render_status_buttons(submission: Any) -> Any:
    """Render status workflow buttons (publish/archive/draft)."""
    current_status = submission.status

    return Div(
        Div(
            Button(
                "Publish",
                cls="btn btn-success btn-sm",
                hx_post=f"/api/submissions/publish?submission_uid={submission.uid}&user_uid={submission.user_uid}",
                hx_target=f"#status-buttons-{submission.uid}",
                hx_swap="outerHTML",
                disabled=(current_status == "published"),
            ),
            Button(
                "Archive",
                cls="btn btn-warning btn-sm ml-2",
                hx_post=f"/api/submissions/archive?submission_uid={submission.uid}&user_uid={submission.user_uid}",
                hx_target=f"#status-buttons-{submission.uid}",
                hx_swap="outerHTML",
                disabled=(current_status == "archived"),
            ),
            Button(
                "Mark as Draft",
                cls="btn btn-ghost btn-sm ml-2",
                hx_post=f"/api/submissions/draft?submission_uid={submission.uid}&user_uid={submission.user_uid}",
                hx_target=f"#status-buttons-{submission.uid}",
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
        id=f"status-buttons-{submission.uid}",
        cls="p-4 bg-base-200 rounded-lg",
    )


# ============================================================================
# TYPED QUERY PARAMETERS
# ============================================================================


@dataclass
class SubmissionFilters:
    """Typed filters for submission list queries."""

    report_type: str
    status: str


def parse_submission_filters(request: Request) -> SubmissionFilters:
    """
    Extract submission filter parameters from request query params.

    Args:
        request: Starlette request object

    Returns:
        Typed SubmissionFilters with defaults applied
    """
    return SubmissionFilters(
        report_type=request.query_params.get("report_type", ""),
        status=request.query_params.get("status", ""),
    )


# ============================================================================
# SHARING UI COMPONENTS
# ============================================================================


def _render_visibility_dropdown(submission: Any) -> Any:
    """
    Render visibility level dropdown.

    Only shows for completed reports (quality control).
    Uses HTMX for instant updates.
    """
    current_visibility = getattr(submission, "visibility", "private")
    is_shareable = getattr(submission, "status", "") == "completed"

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
            hx_post="/api/submissions/set-visibility",
            hx_trigger="change",
            hx_vals=f"js:{{report_uid: '{submission.uid}', visibility: event.target.value}}",
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
    Render modal for sharing submission with a user.

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
                        hx_post="/api/submissions/share",
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
    Render list of users submission is shared with.

    Loaded dynamically via HTMX on page load.
    """
    return Div(
        H4("Shared With", cls="font-bold mb-2"),
        Div(
            P("Loading shared users...", cls="text-base-content/60 text-sm"),
            id="shared-users-list",
            hx_get=f"/submissions/{report_uid}/shared-users",
            hx_trigger="load",
            hx_swap="innerHTML",
        ),
        cls="mt-4",
    )


def _render_sharing_section(submission: Any) -> Any:
    """
    Render complete sharing section for submission detail page.

    Includes:
    - Visibility dropdown
    - Share button (opens modal)
    - Shared users list

    Only shown for submission owner.
    """
    return Div(
        H4("Sharing & Visibility", cls="font-bold text-lg mb-4"),
        Div(
            # Visibility controls
            _render_visibility_dropdown(submission),
            # Share modal and button
            Div(
                _render_share_modal(submission.uid),
                cls="mb-4",
            ),
            # Shared users list
            _render_shared_users_list(submission.uid),
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

SUBMISSIONS_SIDEBAR_ITEMS = [
    SidebarItem("Assignments", "/submissions/assignments", "assignments", icon="📋"),
    SidebarItem("Submit", "/submissions/submit", "submit", icon="📤"),
    SidebarItem("Browse", "/submissions/browse", "browse", icon="📂"),
    SidebarItem("Your Submissions", "/submissions/yours", "yours", icon="📝"),
    SidebarItem("Feedback", "/submissions/feedback", "feedback", icon="💬"),
    SidebarItem("Progress", "/submissions/progress", "progress", icon="📊"),
]


# ============================================================================
# ASSIGNMENTS RENDERING
# ============================================================================


def _render_assignments_list(exercises: list[dict[str, Any]]) -> Any:
    """Render student's assigned exercises with submission status."""
    if not exercises:
        return Div(
            P(
                "No exercises assigned yet. You'll see exercises here when a teacher assigns them to your group.",
                cls="text-center text-base-content/60 py-8",
            ),
            cls="card bg-base-100 shadow-sm p-6",
        )

    cards = [_render_assignment_card(ex) for ex in exercises]
    return Div(*cards, cls="space-y-4")


def _render_assignment_card(ex: dict[str, Any]) -> Any:
    """Render a single exercise assignment card."""
    uid = ex.get("uid", "")
    title = ex.get("title", "Untitled Exercise")
    instructions = ex.get("instructions") or ""
    due_date_str = ex.get("due_date")
    group_name = ex.get("group_name", "")
    has_submission = ex.get("has_submission", False)

    # Status badge
    if has_submission:
        status_badge = Span("Submitted", cls="badge badge-success")
    elif due_date_str:
        try:
            due = date.fromisoformat(str(due_date_str))
            days_until = (due - date.today()).days
            if days_until < 0:
                status_badge = Span(f"Overdue ({-days_until}d)", cls="badge badge-error")
            elif days_until <= 3:
                status_badge = Span(f"Due in {days_until}d", cls="badge badge-warning")
            else:
                status_badge = Span(f"Due in {days_until}d", cls="badge badge-info")
        except (ValueError, TypeError):
            status_badge = Span("Pending", cls="badge badge-ghost")
    else:
        status_badge = Span("No deadline", cls="badge badge-ghost")

    # Instructions preview (truncated)
    instructions_preview = ""
    if instructions:
        preview_text = instructions[:200] + ("..." if len(instructions) > 200 else "")
        instructions_preview = P(preview_text, cls="text-sm text-base-content/70 mt-2")

    # Group name
    group_tag = Span(group_name, cls="badge badge-outline badge-sm") if group_name else ""

    # Due date display
    due_display = ""
    if due_date_str:
        due_display = Span(f"Due: {due_date_str}", cls="text-sm text-base-content/60")

    # Action button
    if has_submission:
        action = Span("Already submitted", cls="text-sm text-success")
    else:
        action = A(
            "Submit",
            href=f"/submissions/submit?exercise_uid={uid}",
            cls="btn btn-primary btn-sm",
        )

    return Div(
        Div(
            Div(
                Div(
                    H4(title, cls="card-title text-lg"),
                    status_badge,
                    cls="flex items-center gap-2 flex-wrap",
                ),
                Div(group_tag, due_display, cls="flex items-center gap-3 mt-1"),
                instructions_preview,
                cls="flex-1",
            ),
            Div(action, cls="flex items-center"),
            cls="flex justify-between gap-4",
        ),
        cls="card bg-base-100 shadow-sm p-4",
    )


# ============================================================================
# CONTENT FRAGMENTS (extracted from former monolithic dashboard)
# ============================================================================


def _render_upload_form(
    assigned_exercises: list[Any] | None = None,
    selected_exercise_uid: str | None = None,
) -> Any:
    """Render the file upload form card with optional exercise selector."""
    # Build exercise selector if exercises exist
    exercise_section: Any = ""
    if assigned_exercises:
        exercise_options = [Option("None — standalone submission", value="")]

        def _exercise_option(p: Any) -> Any:
            uid = p.uid
            label = getattr(p, "title", None) or getattr(p, "name", None) or uid
            return Option(label, value=uid, selected=(uid == selected_exercise_uid))

        exercise_options.extend(_exercise_option(p) for p in assigned_exercises)
        exercise_section = Div(
            Label("Exercise (optional)", cls="label"),
            Select(
                *exercise_options,
                name="fulfills_exercise_uid",
                cls="select select-bordered w-full",
            ),
            P(
                "Link this submission to a teacher exercise",
                cls="text-xs text-base-content/60 mt-1",
            ),
            cls="mb-4",
        )

    return Div(
        Div(
            Form(
                # Exercise selector (only if exercises exist)
                exercise_section,
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
                    "hx-post": "/submissions/upload",
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
                htmx.trigger('#submissions-grid-container', 'load');
            }
        });
    """)
    )


def _render_filters_section() -> Any:
    """Render the status and type filter controls card."""
    return Div(
        Div(
            Form(
                Div(
                    Div(
                        Label("Type", cls="label"),
                        Select(
                            Option("All Types", value="", selected=True),
                            Option("Submission", value="submission"),
                            Option("Transcript", value="transcript"),
                            Option("Journal", value="journal"),
                            Option("Progress Report", value="progress"),
                            Option("Assessment", value="assessment"),
                            name="report_type",
                            cls="select select-bordered w-full",
                        ),
                        cls="flex-1",
                    ),
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
                        cls="flex-1",
                    ),
                    cls="flex gap-4",
                ),
                **{
                    "hx-get": "/submissions/grid",
                    "hx-target": "#submissions-grid-container",
                    "hx-swap": "outerHTML",
                    "hx-trigger": "change from:select",
                },
                id="filter-form",
            ),
            cls="card-body",
        ),
        cls="card bg-base-100 shadow-sm mb-6",
    )


def _render_submissions_grid_container() -> Any:
    """Render the HTMX-loading reports grid container."""
    return Div(
        P("Loading reports...", cls="text-center text-base-content/60"),
        id="submissions-grid-container",
        cls="mt-4",
        **{
            "hx-get": "/submissions/grid",
            "hx-trigger": "load",
            "hx-swap": "outerHTML",
        },
    )


# ============================================================================
# STUDENT SUBMISSION HISTORY HELPERS
# ============================================================================


def _render_review_status_badge(status: str, feedback_count: int) -> Any:
    """Return a DaisyUI badge indicating the teacher review outcome."""
    if feedback_count > 0 and status == "completed":
        return Span("Reviewed", cls="badge badge-success badge-sm")
    if status == "revision_requested":
        return Span("Revision Needed", cls="badge badge-warning badge-sm")
    if feedback_count == 0 and status == "submitted":
        return Span("Awaiting Review", cls="badge badge-neutral badge-sm")
    return Span(status.replace("_", " ").title(), cls="badge badge-ghost badge-sm")


def _render_submission_history_row(item: dict) -> Any:
    """Render a single submission row with review status for the history list."""
    filename = item.get("original_filename") or item.get("title") or "Untitled"
    status = item.get("status") or "submitted"
    feedback_count = item.get("feedback_count") or 0
    uid = item.get("uid", "")

    created_raw = item.get("created_at")
    if created_raw:
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(str(created_raw))
            created_str = dt.strftime("%d %b %Y")
        except (ValueError, TypeError):
            created_str = str(created_raw)[:10]
    else:
        created_str = ""

    feedback_chip: Any = ""
    if feedback_count > 0:
        label = f"{feedback_count} feedback round{'s' if feedback_count != 1 else ''}"
        feedback_chip = Span(label, cls="badge badge-outline badge-sm ml-2")

    return Div(
        Div(
            Div(
                P(filename, cls="font-semibold mb-0"),
                P(created_str, cls="text-xs text-base-content/50 mb-0"),
                cls="flex-1",
            ),
            Div(
                _render_review_status_badge(status, feedback_count),
                feedback_chip,
                cls="flex items-center gap-2",
            ),
            A(
                "View",
                href=f"/submissions/{uid}",
                cls="btn btn-sm btn-ghost ml-3",
            ),
            cls="flex items-center gap-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )


def _render_yours_list(items: list[dict]) -> Any:
    """Render the full list of submissions with feedback status (HTMX swap target)."""
    if not items:
        return Div(
            P(
                "No submissions yet.",
                cls="text-center text-base-content/60 py-8",
            ),
            id="submissions-yours-list",
        )
    return Div(
        *[_render_submission_history_row(item) for item in items],
        id="submissions-yours-list",
    )


def _render_yours_list_container() -> Any:
    """HTMX-loading container for the submissions history list."""
    return Div(
        P("Loading your submissions...", cls="text-center text-base-content/60"),
        id="submissions-yours-list",
        cls="mt-4",
        **{
            "hx-get": "/submissions/yours/list",
            "hx-trigger": "load",
            "hx-swap": "outerHTML",
        },
    )


def _render_feedback_card(assessment: Any) -> Any:
    """Render a single received-feedback card (server-side, no inline JS)."""
    uid = getattr(assessment, "uid", "") or ""
    title = getattr(assessment, "title", "") or "Assessment"
    content = getattr(assessment, "content", "") or ""
    preview = content[:200] + ("..." if len(content) > 200 else "")
    created_at = getattr(assessment, "created_at", None)
    user_uid = getattr(assessment, "user_uid", "") or ""

    processor_type = getattr(assessment, "processor_type", None)
    if processor_type:
        # Use getattr sentinel pattern (SKUEL011: no hasattr)
        _missing = object()
        ptype_val = getattr(processor_type, "value", _missing)
        ptype_str = ptype_val if ptype_val is not _missing else str(processor_type)
        source_label = "AI" if ptype_str == "llm" else "Teacher"
    else:
        source_label = "Teacher"

    date_str = ""
    if created_at:
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(str(created_at))
            date_str = dt.strftime("%d %b %Y")
        except (ValueError, TypeError):
            date_str = str(created_at)[:10]

    return Div(
        Div(
            Div(
                H4(title, cls="font-semibold mb-1"),
                P(
                    f"From: {user_uid} · {date_str} · {source_label}",
                    cls="text-sm text-base-content/60 mb-2",
                ),
                P(preview, cls="text-sm"),
                A("View Full", href=f"/submissions/{uid}", cls="btn btn-sm btn-ghost mt-2"),
                cls="card-body p-4",
            ),
            cls="card bg-base-100 shadow-sm mb-3",
        ),
    )


def _render_received_feedback_list(items: list[Any]) -> Any:
    """Render the full list of received feedback (HTMX swap target)."""
    if not items:
        return Div(
            P("No feedback yet.", cls="text-center text-base-content/60 py-6"),
            P(
                "Assessments from teachers will appear here once submitted.",
                cls="text-sm text-center text-base-content/40",
            ),
            id="feedback-list",
        )
    return Div(
        *[_render_feedback_card(a) for a in items],
        id="feedback-list",
    )


# ============================================================================
# PROCESSOR BADGE + ACTIVITY/PROGRESS RENDERING HELPERS
# ============================================================================

_PROCESSOR_LABELS = {"llm": "LLM", "automatic": "Scheduled", "human": "Admin"}
_PROCESSOR_BADGE_CLASSES = {
    "llm": "badge-info",
    "automatic": "badge-ghost",
    "human": "badge-primary",
}


def _get_processor_type_str(report: Any) -> str:
    """Extract processor_type as lowercase string from a report/entity."""
    processor_type = getattr(report, "processor_type", None)
    if processor_type is None:
        return ""
    _missing = object()
    ptype_val = getattr(processor_type, "value", _missing)
    return str(ptype_val if ptype_val is not _missing else processor_type).lower()


def _render_processor_badge(processor_type_str: str) -> Any:
    """Render a DaisyUI badge for processor type (LLM / Scheduled / Admin)."""
    label = _PROCESSOR_LABELS.get(processor_type_str, processor_type_str or "AI")
    badge_cls = _PROCESSOR_BADGE_CLASSES.get(processor_type_str, "badge-ghost")
    return Span(label, cls=f"badge {badge_cls} badge-sm")


def _format_date(dt_value: Any) -> str:
    """Format a datetime-like value to a display string."""
    if not dt_value:
        return ""
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(str(dt_value))
        return dt.strftime("%d %b %Y")
    except (ValueError, TypeError):
        return str(dt_value)[:10]


def _render_activity_feedback_card(report: Any) -> Any:
    """Render a single activity feedback card (server-side)."""
    title = getattr(report, "title", "") or "Activity Feedback"
    created_at = getattr(report, "created_at", None)
    time_period = getattr(report, "time_period", None)
    content = getattr(report, "processed_content", "") or ""
    truncated = content[:200] + ("..." if len(content) > 200 else "")
    ptype_str = _get_processor_type_str(report)
    date_str = _format_date(created_at)

    date_parts = [date_str] if date_str else []
    if time_period:
        date_parts.append(str(time_period))
    subtitle = " \u00b7 ".join(date_parts)

    return Div(
        Div(
            Div(
                Div(
                    P(title, cls="font-semibold mb-0 text-sm"),
                    P(subtitle, cls="text-xs text-base-content/50 mb-1") if subtitle else None,
                ),
                _render_processor_badge(ptype_str),
                cls="flex items-start justify-between gap-2",
            ),
            P(truncated, cls="text-xs text-base-content/70 mt-1") if truncated else None,
            cls="card-body p-3",
        ),
        cls="card bg-base-100 border border-base-200 mb-2",
    )


def _render_activity_feedback_list(items: list[Any]) -> Any:
    """Render the full list of activity feedback (HTMX swap target)."""
    if not items:
        return Div(
            P(
                "No activity feedback yet.",
                cls="text-center text-base-content/60 py-4",
            ),
            id="activity-feedback-list",
        )
    return Div(
        *[_render_activity_feedback_card(r) for r in items],
        id="activity-feedback-list",
    )


def _render_progress_report_card(report: Any) -> Any:
    """Render a single progress report card (server-side)."""
    title = getattr(report, "title", "") or "Activity Feedback"
    created_at = getattr(report, "created_at", None)
    time_period = getattr(report, "time_period", None)
    depth = getattr(report, "depth", None)
    domains_covered = getattr(report, "domains_covered", ()) or ()
    content = getattr(report, "processed_content", "") or ""
    ptype_str = _get_processor_type_str(report)
    date_str = _format_date(created_at)

    # Badges row
    badges = []
    if time_period:
        badges.append(Span(str(time_period), cls="badge badge-outline badge-sm"))
    if depth:
        badges.append(Span(str(depth), cls="badge badge-outline badge-sm"))
    badges.append(_render_processor_badge(ptype_str))

    # Domain badges
    domain_badges = [Span(str(d), cls="badge badge-ghost badge-xs") for d in domains_covered]

    # Collapsible content
    if content:
        content_section = Div(
            NotStr(
                "<details class='mt-2'>"
                "<summary class='cursor-pointer text-sm text-base-content/70 select-none'>"
                "Read insights</summary>"
            ),
            P(content, cls="text-sm mt-2 whitespace-pre-wrap"),
            NotStr("</details>"),
        )
    else:
        content_section = P(
            "No insights generated yet.",
            cls="text-sm text-base-content/40 mt-1",
        )

    return Div(
        Div(
            Div(
                Div(
                    H4(title, cls="font-semibold mb-0"),
                    P(date_str, cls="text-xs text-base-content/60 mb-0") if date_str else None,
                ),
                cls="flex items-start justify-between gap-4 mb-2",
            ),
            Div(*badges, cls="flex flex-wrap gap-1 mb-2") if badges else None,
            Div(*domain_badges, cls="flex flex-wrap gap-1 mb-2") if domain_badges else None,
            content_section,
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-3",
    )


def _render_progress_report_list(items: list[Any]) -> Any:
    """Render the full list of progress reports (HTMX swap target)."""
    if not items:
        return Div(
            P(
                "No activity feedback yet. Generate your first one above!",
                cls="text-center text-base-content/60 py-4",
            ),
            id="progress-list",
        )
    return Div(
        *[_render_progress_report_card(r) for r in items],
        id="progress-list",
    )


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_submissions_ui_routes(
    _app,
    rt,
    _submissions_service,
    _processing_service,
    _exercises_service=None,
    _submissions_search_service=None,
    _submissions_core_service=None,
    _activity_report_service=None,
    _teacher_review_service=None,
):
    """
    Create all submission UI routes.

    Args:
        app: FastHTML application instance
        rt: Router instance
        report_service: SubmissionsService
        processing_service: SubmissionsProcessingService
        _exercises_service: ExerciseService for exercise dropdown (optional)
        _submissions_search_service: SubmissionsSearchService for feedback status queries (optional)
        _submissions_core_service: SubmissionsCoreService for received assessments (optional)
        _activity_report_service: ActivityReportService for activity feedback history (optional)
    """

    logger.info("Creating Submissions UI routes")

    # ========================================================================
    # SIDEBAR PAGES
    # ========================================================================

    @rt("/submissions")
    async def submissions_landing(request: Request) -> Any:
        """Submissions landing — defaults to Submit page."""
        return await _render_submit_page(request)

    @rt("/submissions/submit")
    async def submissions_submit_page(request: Request) -> Any:
        """Submit page: upload form."""
        return await _render_submit_page(request)

    async def _render_submit_page(request: Request) -> Any:
        user_uid = require_authenticated_user(request)

        # Fetch assigned exercises for exercise dropdown (via group membership)
        assigned_exercises: list[Any] = []
        if _exercises_service:
            exercises_result = await _exercises_service.get_student_exercises(user_uid)
            if not exercises_result.is_error and exercises_result.value:
                assigned_exercises = exercises_result.value

        # Pre-select exercise if arriving from assignments page
        selected_exercise_uid = request.query_params.get("exercise_uid")

        content = Div(
            PageHeader("Submit", subtitle="Upload a file linked to a Knowledge Unit"),
            _render_upload_form(assigned_exercises, selected_exercise_uid=selected_exercise_uid),
            _upload_form_script(),
        )
        return await SidebarPage(
            content=content,
            items=SUBMISSIONS_SIDEBAR_ITEMS,
            active="submit",
            title="Submissions",
            subtitle="Submit and manage files",
            storage_key="submissions-sidebar",
            page_title="Submit",
            request=request,
            active_page="submissions",
            title_href="/submissions",
        )

    @rt("/submissions/assignments")
    async def submissions_assignments_page(request: Request) -> Any:
        """Assignments page: exercises assigned to this student via group membership."""
        user_uid = require_authenticated_user(request)

        exercises: list[dict[str, Any]] = []
        if _exercises_service:
            result = await _exercises_service.get_student_exercises_with_status(user_uid)
            if not result.is_error and result.value:
                exercises = result.value

        content = Div(
            PageHeader(
                "Assignments",
                subtitle="Exercises assigned by your teachers",
            ),
            _render_assignments_list(exercises),
        )
        return await SidebarPage(
            content=content,
            items=SUBMISSIONS_SIDEBAR_ITEMS,
            active="assignments",
            title="Submissions",
            subtitle="Submit and manage files",
            storage_key="submissions-sidebar",
            page_title="Assignments",
            request=request,
            active_page="submissions",
            title_href="/submissions",
        )

    @rt("/submissions/browse")
    async def submissions_browse_page(request: Request) -> Any:
        """Browse page: filters + results grid."""
        require_authenticated_user(request)
        content = Div(
            PageHeader("Browse Submissions", subtitle="Filter and find submissions"),
            _render_filters_section(),
            _render_submissions_grid_container(),
        )
        return await SidebarPage(
            content=content,
            items=SUBMISSIONS_SIDEBAR_ITEMS,
            active="browse",
            title="Submissions",
            subtitle="Submit and manage files",
            storage_key="submissions-sidebar",
            page_title="Browse Submissions",
            request=request,
            active_page="submissions",
            title_href="/submissions",
        )

    @rt("/submissions/yours")
    async def submissions_yours_page(request: Request) -> Any:
        """Your Submissions page: list with teacher review status badges."""
        require_authenticated_user(request)
        content = Div(
            PageHeader(
                "Your Submissions",
                subtitle="See which submissions have been reviewed by a teacher",
            ),
            _render_yours_list_container(),
        )
        return await SidebarPage(
            content=content,
            items=SUBMISSIONS_SIDEBAR_ITEMS,
            active="yours",
            title="Submissions",
            subtitle="Submit and manage files",
            storage_key="submissions-sidebar",
            page_title="Your Submissions",
            request=request,
            active_page="submissions",
            title_href="/submissions",
        )

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/submissions/yours/list")
    async def submissions_yours_list(request: Request) -> Any:
        """HTMX fragment: student's submissions with teacher review status."""
        try:
            user_uid = require_authenticated_user(request)
            if not _submissions_search_service:
                return Div(
                    P("Submissions service unavailable.", cls="text-center text-error"),
                    id="submissions-yours-list",
                )
            result = await _submissions_search_service.get_submissions_with_feedback_status(
                user_uid
            )
            items = result.value if not result.is_error else []
            return _render_yours_list(items)
        except Exception as e:
            logger.error(f"Error loading submissions history: {e}", exc_info=True)
            return Div(
                P("Error loading submissions.", cls="text-center text-error"),
                id="submissions-yours-list",
            )

    @rt("/submissions/upload")
    async def upload_submission(request: Request) -> Any:
        """HTMX endpoint for submission file upload (human review)."""
        try:
            form = await request.form()
            uploaded_file = form.get("file")
            raw_identifier = form.get("identifier")
            identifier = str(raw_identifier).strip() if raw_identifier else ""

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

            # Extract optional exercise link
            raw_exercise_uid = form.get("fulfills_exercise_uid")
            fulfills_exercise_uid = (
                str(raw_exercise_uid).strip() or None if raw_exercise_uid else None
            )

            # Submit for human review — processor_type always HUMAN for regular users
            result = await _submissions_service.submit_file(
                file_content=file_content,
                original_filename=filename,
                user_uid=user_uid,
                entity_type=EntityType.SUBMISSION,
                processor_type=ProcessorType.HUMAN,
                metadata={"identifier": identifier},
                fulfills_exercise_uid=fulfills_exercise_uid,
            )

            if result.is_error:
                return _render_upload_status("error", str(result.error), is_error=True)

            submission = result.value
            return _render_upload_status(
                status=submission.status,
                message="File uploaded successfully",
                submission_uid=submission.uid,
            )

        except Exception as e:
            logger.error(f"Error uploading submission: {e}", exc_info=True)
            return _render_upload_status("error", f"Upload failed: {e}", is_error=True)

    @rt("/submissions/grid")
    async def get_submissions_grid(request: Request) -> Any:
        """HTMX endpoint for loading reports grid with filters."""
        try:
            user_uid = require_authenticated_user(request)  # Enforce authentication

            # Parse typed filter parameters
            filters = parse_submission_filters(request)

            # Build filter kwargs
            kwargs = {"user_uid": user_uid, "limit": 50}
            if filters.report_type:
                kwargs["report_type"] = filters.report_type
            if filters.status:
                kwargs["status"] = filters.status

            result = await _submissions_service.list_submissions(**kwargs)

            if result.is_error:
                return Div(
                    P("Failed to load reports", cls="text-center text-error"),
                    id="submissions-grid-container",
                )

            reports = result.value or []
            return _render_submissions_grid(reports)

        except Exception as e:
            logger.error(f"Error loading reports: {e}", exc_info=True)
            return Div(
                P(f"Error: {e}", cls="text-center text-error"),
                id="submissions-grid-container",
            )

    @rt("/submissions/{uid}/info")
    async def get_submission_info(request: Request, uid: str) -> Any:
        """HTMX endpoint for loading submission detail info."""
        try:
            result = await _submissions_service.get_submission(uid)

            if result.is_error:
                return Div(
                    Div(
                        P(f"Failed to load submission: {result.error}"),
                        cls="alert alert-error",
                    ),
                    id="submission-info",
                )

            submission = result.value
            if not submission:
                return Div(
                    Div(
                        P(f"Report {uid} not found"),
                        cls="alert alert-warning",
                    ),
                    id="submission-info",
                )
            return _render_submission_detail(submission)

        except Exception as e:
            logger.error(f"Error loading submission info: {e}", exc_info=True)
            return Div(
                Div(
                    P(f"Error: {e}"),
                    cls="alert alert-error",
                ),
                id="submission-info",
            )

    @rt("/submissions/{uid}/content")
    async def get_submission_content(request: Request, uid: str) -> Any:
        """HTMX endpoint for loading submission processed content."""
        try:
            result = await _submissions_service.get_submission(uid)

            if result.is_error or not result.value:
                return _render_processed_content(None, False)

            submission = result.value
            content = submission.processed_content if submission else None
            return _render_processed_content(content, bool(content))

        except Exception as e:
            logger.error(f"Error loading submission content: {e}", exc_info=True)
            return _render_processed_content(None, False)

    # ========================================================================
    # FEEDBACK & EXERCISE LINK HTMX ENDPOINTS
    # ========================================================================

    @rt("/submissions/{uid}/feedback")
    async def get_submission_feedback(request: Request, uid: str) -> Any:
        """HTMX endpoint: feedback received on this submission."""
        from ui.patterns.feedback_item import render_feedback_item

        try:
            user_uid = require_authenticated_user(request)

            # Verify ownership
            sub_result = await _submissions_service.get_submission(uid)
            if sub_result.is_error or not sub_result.value:
                return Div(P("Submission not found.", cls="text-error"), id="feedback-section")
            if sub_result.value.user_uid != user_uid:
                return Div(P("Access denied.", cls="text-error"), id="feedback-section")

            if not _teacher_review_service:
                return Div(
                    P("No feedback yet.", cls="text-center text-base-content/60 py-4"),
                    id="feedback-section",
                )

            history_result = await _teacher_review_service.get_feedback_history(uid)
            items = history_result.value if not history_result.is_error else []

            if not items:
                return Div(
                    H4("Feedback", cls="mb-4"),
                    P("No feedback yet.", cls="text-center text-base-content/60 py-4"),
                    id="feedback-section",
                )

            return Div(
                H4("Feedback", cls="mb-4"),
                *[render_feedback_item(fb) for fb in items],
                id="feedback-section",
            )
        except Exception as e:
            logger.error(f"Error loading feedback for {uid}: {e}", exc_info=True)
            return Div(
                P("Error loading feedback.", cls="text-error"),
                id="feedback-section",
            )

    @rt("/submissions/{uid}/exercise")
    async def get_submission_exercise(request: Request, uid: str) -> Any:
        """HTMX endpoint: which exercise this submission fulfills."""
        try:
            require_authenticated_user(request)

            if not _exercises_service:
                return Div(id="exercise-link")

            # Query the FULFILLS_EXERCISE relationship
            result = await _exercises_service.backend.execute_query(
                """
                MATCH (s:Entity {uid: $uid})-[:FULFILLS_EXERCISE]->(ex:Entity:Exercise)
                RETURN ex.uid AS exercise_uid, ex.title AS exercise_title
                LIMIT 1
                """,
                {"uid": uid},
            )

            if result.is_error or not result.value:
                return Div(id="exercise-link")

            record = result.value[0]
            ex_title = record.get("exercise_title", "Exercise")

            return Div(
                Span("Exercise: ", cls="font-medium text-sm text-base-content/60"),
                Span(ex_title, cls="badge badge-outline badge-sm"),
                id="exercise-link",
                cls="mt-2",
            )
        except Exception as e:
            logger.error(f"Error loading exercise link for {uid}: {e}", exc_info=True)
            return Div(id="exercise-link")

    # ========================================================================
    # CONTENT MANAGEMENT UI ROUTES
    # ========================================================================

    @rt("/submissions/{uid}/category-selector")
    async def get_category_selector(request: Request, uid: str) -> Any:
        """HTMX endpoint for category selector."""
        try:
            result = await _submissions_service.get_submission(uid)
            if result.is_error:
                return Div("Report not found", cls="text-error")

            submission = result.value
            return _render_category_selector(submission)

        except Exception as e:
            logger.error(f"Error loading category selector: {e}", exc_info=True)
            return Div("Error loading category selector", cls="text-error")

    @rt("/submissions/{uid}/tags-manager")
    async def get_tags_manager(request: Request, uid: str) -> Any:
        """HTMX endpoint for tags manager."""
        try:
            result = await _submissions_service.get_submission(uid)
            if result.is_error:
                return Div("Report not found", cls="text-error")

            submission = result.value
            return _render_tags_manager(submission)

        except Exception as e:
            logger.error(f"Error loading tags manager: {e}", exc_info=True)
            return Div("Error loading tags manager", cls="text-error")

    # ========================================================================
    # FEEDBACK PAGE (assessments received)
    # ========================================================================

    @rt("/submissions/feedback")
    async def submissions_feedback_page(request: Request) -> Any:
        """Feedback page: assessments received from teachers + AI activity feedback."""
        require_authenticated_user(request)

        teacher_section = Div(
            H3("Teacher Assessments", cls="font-semibold mb-4"),
            Div(
                P("Loading feedback...", cls="text-center text-base-content/60"),
                id="feedback-list",
                cls="mt-2",
                **{
                    "hx-get": "/submissions/feedback/list",
                    "hx-trigger": "load",
                    "hx-swap": "outerHTML",
                },
            ),
            cls="card bg-base-100 shadow-sm p-4 mb-6",
        )

        activity_feedback_section = Div(
            H3("Activity Feedback", cls="font-semibold mb-4"),
            Div(
                P("Loading activity feedback...", cls="text-center text-base-content/60"),
                id="activity-feedback-list",
                cls="mt-2",
                **{
                    "hx-get": "/submissions/feedback/activity-list",
                    "hx-trigger": "load",
                    "hx-swap": "outerHTML",
                },
            ),
            cls="card bg-base-100 shadow-sm p-4",
        )

        content = Div(
            PageHeader("SubmissionFeedback", subtitle="Assessments and feedback from teachers"),
            teacher_section,
            activity_feedback_section,
        )
        return await SidebarPage(
            content=content,
            items=SUBMISSIONS_SIDEBAR_ITEMS,
            active="feedback",
            title="Submissions",
            subtitle="Submit and manage files",
            storage_key="submissions-sidebar",
            page_title="SubmissionFeedback",
            request=request,
            active_page="submissions",
            title_href="/submissions",
        )

    @rt("/submissions/feedback/list")
    async def submissions_feedback_list(request: Request) -> Any:
        """HTMX fragment: server-rendered list of teacher assessments received."""
        try:
            user_uid = require_authenticated_user(request)
            if not _submissions_core_service:
                return Div(
                    P("Feedback service unavailable.", cls="text-center text-error"),
                    id="feedback-list",
                )
            result = await _submissions_core_service.get_assessments_for_student(
                student_uid=user_uid
            )
            items = result.value if not result.is_error else []
            return _render_received_feedback_list(items)
        except Exception as e:
            logger.error(f"Error loading feedback list: {e}", exc_info=True)
            return Div(
                P("Error loading feedback.", cls="text-center text-error"),
                id="feedback-list",
            )

    @rt("/submissions/feedback/activity-list")
    async def submissions_activity_feedback_list(request: Request) -> Any:
        """HTMX fragment: server-rendered list of activity feedback."""
        try:
            user_uid = require_authenticated_user(request)
            if not _activity_report_service:
                return Div(
                    P(
                        "Activity feedback unavailable.",
                        cls="text-center text-base-content/60 py-4",
                    ),
                    id="activity-feedback-list",
                )
            result = await _activity_report_service.get_history(subject_uid=user_uid, limit=10)
            items = result.value if not result.is_error else []
            return _render_activity_feedback_list(items)
        except Exception as e:
            logger.error(f"Error loading activity feedback list: {e}", exc_info=True)
            return Div(
                P("Error loading activity feedback.", cls="text-center text-error"),
                id="activity-feedback-list",
            )

    # ========================================================================
    # PROGRESS PAGE (generate + view progress reports)
    # ========================================================================

    @rt("/submissions/progress")
    async def submissions_progress_page(request: Request) -> Any:
        """Progress page: generate and view progress reports."""
        require_authenticated_user(request)

        generate_card = Div(
            Div(
                H3("Generate Progress Report", cls="font-semibold mb-4"),
                Form(
                    Div(
                        Label("Time Period", cls="label"),
                        Select(
                            Option("Last 7 days", value="7d", selected=True),
                            Option("Last 14 days", value="14d"),
                            Option("Last 30 days", value="30d"),
                            Option("Last 90 days", value="90d"),
                            name="time_period",
                            cls="select select-bordered w-full",
                        ),
                        cls="mb-3",
                    ),
                    Div(
                        Label("Depth", cls="label"),
                        Select(
                            Option("Summary (counts only)", value="summary"),
                            Option("Standard (counts + examples)", value="standard", selected=True),
                            Option("Detailed (full breakdown)", value="detailed"),
                            name="depth",
                            cls="select select-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    Div(
                        Button(
                            "Generate Now",
                            type="submit",
                            variant=ButtonT.primary,
                        ),
                        cls="text-center",
                    ),
                    Div(id="generate-status", cls="mt-4"),
                    **{
                        "hx-post": "/api/feedback/progress/generate",
                        "hx-target": "#generate-status",
                        "hx-swap": "innerHTML",
                        "hx-vals": 'js:JSON.stringify({time_period: document.querySelector("[name=time_period]").value, depth: document.querySelector("[name=depth]").value, include_insights: true})',
                        "hx-headers": '{"Content-Type": "application/json"}',
                    },
                ),
                cls="card-body",
            ),
            cls="card bg-base-100 shadow-sm mb-6",
        )

        recent_reports = Div(
            H3("Recent Progress Reports", cls="font-semibold mb-4"),
            Div(
                P("Loading...", cls="text-center text-base-content/60"),
                id="progress-list",
                **{
                    "hx-get": "/submissions/progress/list",
                    "hx-trigger": "load",
                    "hx-swap": "outerHTML",
                },
            ),
        )

        content = Div(
            PageHeader("Progress Reports", subtitle="Track your activity over time"),
            generate_card,
            recent_reports,
        )
        return await SidebarPage(
            content=content,
            items=SUBMISSIONS_SIDEBAR_ITEMS,
            active="progress",
            title="Submissions",
            subtitle="Submit and manage files",
            storage_key="submissions-sidebar",
            page_title="Progress Reports",
            request=request,
            active_page="submissions",
            title_href="/submissions",
        )

    @rt("/submissions/progress/list")
    async def submissions_progress_list(request: Request) -> Any:
        """HTMX fragment: server-rendered list of progress reports."""
        try:
            user_uid = require_authenticated_user(request)
            result = await _submissions_service.list_submissions(
                user_uid=user_uid,
                entity_type=EntityType.ACTIVITY_REPORT,
                limit=10,
            )
            items = result.value if not result.is_error else []
            return _render_progress_report_list(items)
        except Exception as e:
            logger.error(f"Error loading progress report list: {e}", exc_info=True)
            return Div(
                P("Error loading progress reports.", cls="text-center text-error"),
                id="progress-list",
            )

    @rt("/submissions/{uid}/shared-users")
    async def get_shared_users_ui(request: Request, uid: str) -> Any:
        """
        HTMX endpoint for rendering shared users list.

        Returns HTML fragment showing users the submission is shared with.
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
    # IMPORTANT: This route MUST be defined LAST because /submissions/{uid}
    # is a catch-all pattern that would match specific routes like
    # /reports/grid, /reports/upload, etc.
    # ========================================================================

    @rt("/submissions/{uid}")
    async def submission_detail(request: Request, uid: str) -> Any:
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

        # Fetch submission to determine if user is owner (for sharing controls)
        # Note: In production, this would use get_with_access_check()
        submission_result = await _submissions_service.get_submission(uid)
        is_owner = False
        if not submission_result.is_error and submission_result.value is not None:
            is_owner = submission_result.value.user_uid == user_uid

        # Detail view card with HTMX loading
        detail_card = Div(
            Div(
                H3("Submission Details", cls="card-title"),
                # Report info container (loaded via HTMX)
                Div(
                    P("Loading submission details...", cls="text-center text-base-content/60"),
                    id="submission-info",
                    cls="mb-4",
                    **{
                        "hx-get": f"/submissions/{uid}/info",
                        "hx-trigger": "load",
                        "hx-swap": "outerHTML",
                    },
                ),
                # Exercise link (loaded via HTMX)
                Div(
                    id="exercise-link",
                    **{
                        "hx-get": f"/submissions/{uid}/exercise",
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
                            "hx-get": f"/submissions/{uid}/content",
                            "hx-trigger": "load",
                            "hx-swap": "outerHTML",
                        },
                    ),
                    id="content-section",
                    cls="mb-4",
                ),
                # Feedback section (loaded via HTMX)
                Div(
                    P("Loading feedback...", cls="text-center text-base-content/60 py-2"),
                    id="feedback-section",
                    cls="mb-4",
                    **{
                        "hx-get": f"/submissions/{uid}/feedback",
                        "hx-trigger": "load",
                        "hx-swap": "outerHTML",
                    },
                ),
                # Sharing section (only for owner)
                (
                    _render_sharing_section(submission_result.value)
                    if is_owner and not submission_result.is_error
                    else None
                ),
                # Action buttons - use proper link instead of onclick
                Div(
                    A(
                        "\u2190 Back to Submissions",
                        href="/submissions",
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
                H1("Submission Details", cls="text-3xl font-bold"),
                P(f"UID: {uid}", cls="text-lg text-base-content/60"),
                cls="text-center mb-8",
            ),
            detail_card,
        )

        return await BasePage(
            content,
            title="Submission Details",
            request=request,
            active_page="submissions",
        )

    logger.info("Submissions UI routes created successfully")

    # Route order matters! Specific routes must come BEFORE parameterized routes.
    # Otherwise /submissions/grid would match /submissions/{uid} with uid="grid"
    return [
        submissions_landing,  # /submissions (exact)
        submissions_assignments_page,  # /submissions/assignments (specific)
        submissions_submit_page,  # /submissions/submit (specific)
        submissions_browse_page,  # /submissions/browse (specific)
        submissions_yours_page,  # /submissions/yours (specific)
        submissions_feedback_page,  # /submissions/feedback (specific)
        submissions_activity_feedback_list,  # /submissions/feedback/activity-list (HTMX fragment)
        submissions_progress_page,  # /submissions/progress (specific)
        submissions_progress_list,  # /submissions/progress/list (HTMX fragment)
        upload_submission,  # /reports/upload (specific, HTMX POST)
        get_submissions_grid,  # /reports/grid (specific, HTMX GET)
        get_submission_info,  # /submissions/{uid}/info (pattern + suffix)
        get_submission_content,  # /submissions/{uid}/content (pattern + suffix)
        get_submission_feedback,  # /submissions/{uid}/feedback (pattern + suffix)
        get_submission_exercise,  # /submissions/{uid}/exercise (pattern + suffix)
        get_category_selector,  # /submissions/{uid}/category-selector (pattern + suffix)
        get_tags_manager,  # /submissions/{uid}/tags-manager (pattern + suffix)
        get_shared_users_ui,  # /submissions/{uid}/shared-users (pattern + suffix)
        submission_detail,  # /submissions/{uid} (catch-all - MUST BE LAST)
    ]
