"""
Submission Form UI Components
==============================

Upload form, filter controls, and content management widgets.
"""

from typing import Any

from fasthtml.common import (
    Div,
    Form,
    NotStr,
    Option,
    P,
    Script,
    Span,
)

from ui.buttons import Button, ButtonT
from ui.forms import Input, Label, Select
from ui.layout import Size


def render_upload_form(
    assigned_exercises: list[Any] | None = None,
    selected_exercise_uid: str | None = None,
) -> Any:
    """Render the file upload form card with optional exercise selector."""
    exercise_section: Any = ""
    if assigned_exercises:
        exercise_options = [Option("None \u2014 standalone submission", value="")]

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
            ),
            P(
                "Link this submission to a teacher exercise",
                cls="text-xs text-muted-foreground mt-1",
            ),
            cls="mb-4",
        )

    return Div(
        Div(
            Form(
                exercise_section,
                Div(
                    Label("Identifier", cls="label"),
                    Input(
                        type="text",
                        name="identifier",
                        placeholder="e.g. meditation-basics, yoga-101",
                        required=True,
                    ),
                    P(
                        "A short label linking this submission to a Knowledge Unit",
                        cls="text-xs text-muted-foreground mt-1",
                    ),
                    cls="mb-4",
                ),
                Div(
                    Label(
                        Div(
                            P("Select File", cls="text-center mb-0"),
                            P(
                                "Click to browse for files (audio, text, PDF, images, video)",
                                cls="text-sm text-muted-foreground text-center mt-0",
                            ),
                            cls="p-4 text-center bg-muted rounded-lg cursor-pointer border-2 border-dashed border-border",
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
                Div(
                    Button(
                        "Submit for Review",
                        variant=ButtonT.primary,
                        type="submit",
                    ),
                    cls="text-center",
                ),
                Div(id="upload-status", cls="mt-4 text-center"),
                **{
                    "hx-post": "/upload",
                    "hx-target": "#upload-status",
                    "hx-swap": "outerHTML",
                    "hx-encoding": "multipart/form-data",
                },
                id="upload-form",
            ),
            cls="card-body",
        ),
        cls="card bg-background shadow-sm hover:shadow-md transition-shadow",
    )


def upload_form_script() -> Any:
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


def render_filters_section() -> Any:
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
                        ),
                        cls="flex-1",
                    ),
                    cls="flex gap-4",
                ),
                **{
                    "hx-get": "/grid",
                    "hx-target": "#submissions-grid-container",
                    "hx-swap": "outerHTML",
                    "hx-trigger": "change from:select",
                },
                id="filter-form",
            ),
            cls="card-body",
        ),
        cls="card bg-background shadow-sm mb-6",
    )


def render_submissions_grid_container() -> Any:
    """Render the HTMX-loading reports grid container."""
    return Div(
        P("Loading reports...", cls="text-center text-muted-foreground"),
        id="submissions-grid-container",
        cls="mt-4",
        **{
            "hx-get": "/grid",
            "hx-trigger": "load",
            "hx-swap": "outerHTML",
        },
    )


def render_yours_list_container() -> Any:
    """HTMX-loading container for the submissions history list."""
    return Div(
        P("Loading your submissions...", cls="text-center text-muted-foreground"),
        id="submissions-yours-list",
        cls="mt-4",
        **{
            "hx-get": "/submissions/list",
            "hx-trigger": "load",
            "hx-swap": "outerHTML",
        },
    )


# ============================================================================
# CONTENT MANAGEMENT WIDGETS
# ============================================================================


def render_category_selector(submission: Any) -> Any:
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
            hx_post=f"/api/submissions/categorize?submission_uid={submission.uid}&user_uid={submission.user_uid}",
            hx_trigger="change",
            hx_target=f"#category-display-{submission.uid}",
            hx_swap="outerHTML",
            hx_vals="js:{category: event.target.value}",
        ),
        id=f"category-selector-{submission.uid}",
        cls="form-control",
    )


def render_category_display(submission: Any) -> Any:
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


def render_tags_manager(submission: Any) -> Any:
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
        else Div("No tags", cls="text-sm text-muted-foreground"),
        Form(
            Input(
                type="text",
                name="new_tag",
                placeholder="Add tag...",
                cls="max-w-xs",
                size=Size.sm,
            ),
            Button("Add Tag", type="submit", cls="btn btn-primary btn-sm ml-2"),
            cls="flex items-center mt-2",
            hx_post=f"/api/submissions/tags/add?submission_uid={submission.uid}&user_uid={submission.user_uid}",
            hx_vals="js:{tags: [document.querySelector('[name=\"new_tag\"]').value]}",
            hx_target=f"#tags-manager-{submission.uid}",
            hx_swap="outerHTML",
        ),
        id=f"tags-manager-{submission.uid}",
        cls="p-4 bg-muted rounded-lg",
    )


def render_status_buttons(submission: Any) -> Any:
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
                f"Current status: {current_status}", cls="text-xs text-muted-foreground mt-2 block"
            ),
        ),
        id=f"status-buttons-{submission.uid}",
        cls="p-4 bg-muted rounded-lg",
    )
