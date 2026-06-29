"""
Submission Form UI Components
==============================

Filter controls and content management widgets for the submissions hub.
Upload form moved to ``ui/user_entry/forms.py`` as part of ADR-054 Step 5b.
"""

from typing import Any

from fasthtml.common import (
    Div,
    Form,
    Option,
    Span,
)
from monsterui.franken import CardBody
from monsterui.franken import CardContainer as Card

from ui.components import Button, ButtonT
from ui.feedback import Badge, BadgeT
from ui.forms import Input, Label, Select
from ui.layout import Size
from ui.patterns.skeleton import SkeletonList


def render_filters_section() -> Any:
    """Render the status and type filter controls card."""
    return Card(
        CardBody(
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
                            name="entity_type",
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
                hx_get="/grid",
                hx_target="#submissions-grid-container",
                hx_swap="outerHTML",
                hx_trigger="change from:select",
                id="filter-form",
            ),
        ),
        cls="bg-background shadow-sm mb-6",
    )


def render_submissions_grid_container() -> Any:
    """Render the HTMX-loading reports grid container."""
    return Div(
        SkeletonList(count=4),
        id="submissions-grid-container",
        cls="mt-4",
        hx_get="/grid",
        hx_trigger="load",
        hx_swap="outerHTML",
    )


def render_yours_list_container() -> Any:
    """HTMX-loading container for the submissions history list."""
    return Div(
        SkeletonList(count=3),
        id="submissions-yours-list",
        cls="mt-4",
        hx_get="/gradebook/list",
        hx_trigger="load",
        hx_swap="outerHTML",
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
        cls="space-y-2",
    )


def render_category_display(submission: Any) -> Any:
    """Render category display with edit button."""
    current_category = (
        submission.metadata.get("category", "none") if submission.metadata else "none"
    )

    return Div(
        Badge(f"Category: {current_category.title()}", variant=BadgeT.primary),
        Button(
            "Change",
            cls=(ButtonT.ghost, "ml-2"),
            size="xs",
            hx_get=f"/gradebook/{submission.uid}/category-selector",
            hx_target=f"#category-display-{submission.uid}",
            hx_swap="outerHTML",
        ),
        id=f"category-display-{submission.uid}",
    )


def render_tags_manager(submission: Any) -> Any:
    """Render tags manager for submission."""
    tags = submission.metadata.get("tags", []) if submission.metadata else []

    tag_elements = [
        Badge(
            tag,
            Button(
                "\u00d7",
                cls=(ButtonT.ghost, "ml-1"),
                size="xs",
                hx_delete=f"/api/submissions/tags/remove?submission_uid={submission.uid}&user_uid={submission.user_uid}",
                hx_vals=f'js:{{tags: ["{tag}"]}}',
                hx_target=f"#tags-manager-{submission.uid}",
                hx_swap="outerHTML",
            ),
            variant=BadgeT.secondary,
            cls="mr-2 mb-2",
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
            Button("Add Tag", type="submit", cls=(ButtonT.primary, "ml-2"), size="sm"),
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
                cls=ButtonT.primary,
                size="sm",
                hx_post=f"/api/submissions/publish?submission_uid={submission.uid}&user_uid={submission.user_uid}",
                hx_target=f"#status-buttons-{submission.uid}",
                hx_swap="outerHTML",
                disabled=(current_status == "published"),
            ),
            Button(
                "Archive",
                cls=(ButtonT.secondary, "ml-2"),
                size="sm",
                hx_post=f"/api/submissions/archive?submission_uid={submission.uid}&user_uid={submission.user_uid}",
                hx_target=f"#status-buttons-{submission.uid}",
                hx_swap="outerHTML",
                disabled=(current_status == "archived"),
            ),
            Button(
                "Mark as Draft",
                cls=(ButtonT.ghost, "ml-2"),
                size="sm",
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
