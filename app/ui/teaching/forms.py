"""
Teaching UI Forms
=================

Form components and display helpers for teacher actions — feedback submission,
revision requests, form metadata display, and form response rendering.

Extracted here so route handlers only handle auth, service calls, and delegation.
"""

from typing import Any

from fasthtml.common import Div, Form, Input, Label, P, Strong

from ui.components import Button, ButtonT, Card, CardBody
from ui.forms import Textarea
from ui.patterns.empty_state import EmptyState
from ui.patterns.format_date import format_date


def render_feedback_submission_form(submission_uid: str) -> Any:
    """Feedback file upload card for the teacher review detail page."""
    return Card(
        CardBody(
            P(
                "Upload your feedback as a Markdown file (.md).",
                cls="text-sm text-muted-foreground mb-3",
            ),
            Form(
                Div(
                    Label(
                        "Feedback file",
                        fr="feedback_file",
                        cls="text-sm font-medium mb-1 block",
                    ),
                    Input(
                        type="file",
                        name="feedback_file",
                        id="feedback_file",
                        accept=".md",
                        required=True,
                        cls="block w-full text-sm file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-sm file:bg-primary file:text-primary-foreground hover:file:bg-primary/90 cursor-pointer",
                    ),
                    cls="mb-4",
                ),
                Button("Submit Feedback", cls=ButtonT.primary, type="submit"),
                enctype="multipart/form-data",
                hx_post=f"/api/teaching/review/{submission_uid}/report",
                hx_target="#review-result",
                hx_swap="innerHTML",
                hx_encoding="multipart/form-data",
            ),
            Div(id="review-result", cls="mt-4"),
        ),
        cls="bg-background shadow-sm mb-3",
    )


def render_revision_request_form(submission_uid: str) -> Any:
    """Revision request card — text notes + approve button — for teacher review detail page."""
    return Card(
        CardBody(
            P(
                "Request the student revise their work.",
                cls="text-sm text-muted-foreground mb-3",
            ),
            Form(
                Div(
                    Label(
                        "Revision notes",
                        fr="revision_notes",
                        cls="text-sm font-medium mb-1 block",
                    ),
                    Textarea(
                        name="notes",
                        id="revision_notes",
                        placeholder="Describe what needs to be revised...",
                        cls="h-24",
                        required=True,
                    ),
                    cls="mb-4",
                ),
                Div(
                    Button("Request Revision", cls=ButtonT.secondary, type="submit"),
                    Button(
                        "Approve",
                        cls=ButtonT.primary,
                        type="button",
                        hx_post=f"/api/teaching/review/{submission_uid}/approve",
                        hx_target="#review-result",
                        hx_swap="innerHTML",
                        hx_confirm="Approve this submission?",
                    ),
                    cls="flex gap-3",
                ),
                hx_post=f"/api/teaching/review/{submission_uid}/revision",
                hx_target="#review-result",
                hx_swap="innerHTML",
            ),
        ),
        cls="bg-background shadow-sm",
    )


def form_data_preview(form_data: dict[str, Any] | None, max_fields: int = 3) -> str:
    """Build a short preview string from form_data for submission list cards."""
    if not form_data:
        return "No data"
    items = list(form_data.items())[:max_fields]
    parts = [f"{k}: {v}" for k, v in items if v is not None]
    preview = " · ".join(parts)
    if len(form_data) > max_fields:
        preview += f" (+{len(form_data) - max_fields} more)"
    return preview or "No data"


def render_form_data_detail(
    form_data: dict[str, Any] | None,
    form_schema: tuple[dict[str, Any], ...] | None = None,
) -> Div:
    """Render form_data as read-only key-value pairs, using schema labels if available."""
    if not form_data:
        return EmptyState("No form data")

    label_map: dict[str, str] = {}
    if form_schema:
        for spec in form_schema:
            name = spec.get("name", "")
            label_map[name] = spec.get("label", name)

    rows = []
    for key, value in form_data.items():
        label = label_map.get(key, key)
        display_value = str(value) if value is not None else "—"
        rows.append(
            Div(
                Strong(label, cls="text-sm text-foreground"),
                P(display_value, cls="text-sm text-muted-foreground mt-0.5"),
                cls="py-2 border-b border-border last:border-0",
            )
        )
    return Div(*rows)


def render_submission_metadata(submission: Any, template: Any | None) -> Div:
    """Metadata panel for a form submission detail page (template, submitted by, date)."""
    meta_items = [
        Div(
            Strong("Submitted by", cls="text-sm"),
            P(submission.user_uid or "Unknown", cls="text-sm text-muted-foreground mt-0.5"),
            cls="py-2",
        ),
        Div(
            Strong("Date", cls="text-sm"),
            P(
                format_date(submission.created_at, "%Y-%m-%d %H:%M", empty="—"),
                cls="text-sm text-muted-foreground mt-0.5",
            ),
            cls="py-2",
        ),
    ]
    if template:
        meta_items.insert(
            0,
            Div(
                Strong("Template", cls="text-sm"),
                P(template.title, cls="text-sm text-muted-foreground mt-0.5"),
                cls="py-2",
            ),
        )
    return Div(*meta_items, cls="border border-border rounded p-4 mb-6")


def render_form_responses_section(
    form_data: dict[str, Any] | None,
    form_schema: tuple[dict[str, Any], ...] | None = None,
) -> Div:
    """Responses panel for a form submission detail page."""
    return Div(
        P("Responses", cls="text-base font-semibold mb-3"),
        render_form_data_detail(form_data, form_schema),
        cls="border border-border rounded p-4",
    )
