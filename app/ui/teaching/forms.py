"""
Teaching UI Forms
=================

Form components and display helpers for teacher actions — feedback submission,
revision requests, form metadata display, and form response rendering.

Extracted here so route handlers only handle auth, service calls, and delegation.
"""

from typing import Any

from fasthtml.common import Div, Form, Input, Label, P, Strong

from core.models.enums.entity_enums import REVIEWABLE_ENTRY_STATUSES, EntityStatus
from ui.activities._shared import safe_id
from ui.components import Button, ButtonT, Card, CardBody
from ui.forms import Textarea
from ui.patterns.empty_state import EmptyState
from ui.patterns.format_date import format_date

_REVIEWABLE_VALUES = frozenset(status.value for status in REVIEWABLE_ENTRY_STATUSES)


def render_feedback_submission_form(submission_uid: str, result_id: str) -> Any:
    """Feedback file upload card — its outcome lands in ``#result_id``."""
    input_id = f"feedback_file_{safe_id(submission_uid)}"
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
                        fr=input_id,
                        cls="text-sm font-medium mb-1 block",
                    ),
                    Input(
                        type="file",
                        name="feedback_file",
                        id=input_id,
                        accept=".md",
                        required=True,
                        cls="block w-full text-sm file:mr-3 file:py-1 file:px-3 file:rounded-sm file:border-0 file:text-sm file:bg-primary file:text-primary-foreground hover:file:bg-primary/90 cursor-pointer",
                    ),
                    cls="mb-4",
                ),
                Button("Submit Feedback", cls=ButtonT.primary, type="submit"),
                enctype="multipart/form-data",
                hx_post=f"/api/teaching/review/{submission_uid}/report",
                hx_target=f"#{result_id}",
                hx_swap="innerHTML",
                hx_encoding="multipart/form-data",
            ),
        ),
        cls="bg-background shadow-xs mb-3",
    )


def render_revision_request_form(submission_uid: str, has_exercise: bool, result_id: str) -> Any:
    """The one revision request form — the review page and the per-student panel.

    Posts ``instructions`` (required), and for a turn-in the feedback points
    (the ``revisionForm`` Alpine rows, ``fp_count``) and an optional
    ``revision_rationale``: the route reads the exercise from the gated detail
    and files a RevisedExercise beside the report. Without an exercise the
    instructions reach the student as a revision-requested report only.
    """
    dom = safe_id(submission_uid)
    exercise_fields: list[Any] = []
    if has_exercise:
        exercise_fields = [
            Div(
                Label("Feedback points", cls="text-sm font-medium mb-1 block"),
                P(
                    "Categorize the specific gaps in the student's work.",
                    cls="text-xs text-muted-foreground mb-2",
                ),
                Div(id=f"fp-rows-{dom}", **{"x-ref": "fpRows"}),
                Div(
                    Button(
                        "+ Add feedback point",
                        cls=ButtonT.ghost,
                        size="sm",
                        type="button",
                        **{"@click": "addPoint()"},  # fasthtml dynamic-attr splat
                    ),
                    cls="mb-2",
                ),
                Input(
                    type="hidden",
                    name="fp_count",
                    value="0",
                    **{"x-bind:value": "points.length"},
                ),
                cls="mb-3",
                **{"x-data": "revisionForm()"},
            ),
            Div(
                Label(
                    "Revision rationale",
                    fr=f"revision_rationale_{dom}",
                    cls="text-sm font-medium mb-1 block",
                ),
                P(
                    "Optional: explain why this revision is needed.",
                    cls="text-xs text-muted-foreground mb-1",
                ),
                Textarea(
                    name="revision_rationale",
                    id=f"revision_rationale_{dom}",
                    placeholder="Why is this revision needed?",
                    cls="h-16",
                ),
                cls="mb-3",
            ),
        ]
        intro = "Ask the student to revise — they get revised instructions to answer."
    else:
        intro = (
            "Ask the student to revise. With no exercise behind this work, your "
            "instructions reach them as feedback; no revised exercise is created."
        )

    return Card(
        CardBody(
            P(intro, cls="text-sm text-muted-foreground mb-3"),
            Form(
                Div(
                    Label(
                        "Revision instructions",
                        fr=f"revision_instructions_{dom}",
                        cls="text-sm font-medium mb-1 block",
                    ),
                    Textarea(
                        name="instructions",
                        id=f"revision_instructions_{dom}",
                        placeholder="What should the student do differently?",
                        cls="h-24",
                        required=True,
                    ),
                    cls="mb-3",
                ),
                *exercise_fields,
                Button("Request Revision", cls=ButtonT.secondary, type="submit"),
                hx_post=f"/api/teaching/review/{submission_uid}/revision",
                hx_target=f"#{result_id}",
                hx_swap="innerHTML",
            ),
        ),
        cls="bg-background shadow-xs",
    )


def render_waiting_actions(submission_uid: str, result_id: str) -> Any:
    """Waiting-for-resubmit card — Approve is the one valid teacher action.

    A revision-requested entry accepts no feedback and no further revision
    request (both write ops gate on ``REVIEWABLE_ENTRY_STATUSES``);
    ``approve_report`` closes the loop without a resubmit (allowed only from
    ``revision_requested``).
    """
    return Card(
        CardBody(
            P("Waiting for the student to resubmit.", cls="text-sm font-medium mb-1"),
            P(
                "Their resubmission arrives as a new version in Needs review. "
                "Approve instead to accept the work as it stands and close the loop.",
                cls="text-sm text-muted-foreground mb-3",
            ),
            Button(
                "Approve",
                cls=ButtonT.primary,
                type="button",
                hx_post=f"/api/teaching/review/{submission_uid}/approve",
                hx_target=f"#{result_id}",
                hx_swap="innerHTML",
                hx_confirm="Approve this submission?",
            ),
        ),
        cls="bg-background shadow-xs",
    )


def render_review_actions(
    submission_uid: str, status: str, has_exercise: bool, superseded: bool
) -> Any:
    """The one action rule for a submission under review — both teacher surfaces.

    Actions follow the writers' status guards, so no form is offered that the
    service must refuse: feedback and a revision request from
    ``REVIEWABLE_ENTRY_STATUSES``, Approve from ``revision_requested``. A
    superseded copy — a newer version the teacher can see was handed in — is
    history and takes none. Every form reports into the one result target this
    renders, keyed by the submission so two panels on a page never collide.
    """
    result_id = f"review-result-{safe_id(submission_uid)}"
    if superseded:
        return P(
            "A newer version of this work has been handed in — this copy is history.",
            cls="text-sm text-muted-foreground italic",
        )
    if status in _REVIEWABLE_VALUES:
        actions: Any = Div(
            render_feedback_submission_form(submission_uid, result_id),
            render_revision_request_form(submission_uid, has_exercise, result_id),
        )
    elif status == EntityStatus.REVISION_REQUESTED.value:
        actions = render_waiting_actions(submission_uid, result_id)
    else:
        return P(
            "This submission is not awaiting review.",
            cls="text-sm text-muted-foreground italic",
        )
    return Div(actions, Div(id=result_id, cls="mt-4"))


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
    return Div(*meta_items, cls="border border-border rounded-sm p-4 mb-6")


def render_form_responses_section(
    form_data: dict[str, Any] | None,
    form_schema: tuple[dict[str, Any], ...] | None = None,
) -> Div:
    """Responses panel for a form submission detail page."""
    return Div(
        P("Responses", cls="text-base font-semibold mb-3"),
        render_form_data_detail(form_data, form_schema),
        cls="border border-border rounded-sm p-4",
    )
