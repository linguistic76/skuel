"""Activity Review form components."""

from typing import Any

from fasthtml.common import Div, Form, Input, NotStr, Option, Script
from monsterui.franken import CardBody, CardHeader, CardTitle
from monsterui.franken import CardContainer as Card

from ui.activity_review.types import DOMAIN_CHOICES
from ui.components import Button, ButtonT
from ui.forms import Checkbox, Label, LabelInput, LabelSelect, LabelTextArea


def render_snapshot_form(subject_uid: str = "", time_period: str = "7d") -> Any:
    """Build the snapshot loading form card."""
    domain_checkboxes = []
    for domain_value, domain_label in DOMAIN_CHOICES:
        domain_checkboxes.append(
            Div(
                Checkbox(
                    name="domains",
                    value=domain_value,
                    checked=True,
                    id=f"domain-{domain_value}",
                ),
                Label(domain_label, _for=f"domain-{domain_value}", cls="ml-2"),
                cls="flex items-center gap-1",
            )
        )

    return Card(
        CardHeader(CardTitle("Load Activity Snapshot")),
        CardBody(
            Form(
                LabelInput(
                    "User UID",
                    type="text",
                    name="subject_uid",
                    value=subject_uid,
                    placeholder="user_name",
                    id="snapshot-subject-uid",
                    cls="space-y-2 mb-3",
                ),
                LabelSelect(
                    Option("Last 7 days", value="7d", selected=(time_period == "7d")),
                    Option("Last 14 days", value="14d", selected=(time_period == "14d")),
                    Option("Last 30 days", value="30d", selected=(time_period == "30d")),
                    Option("Last 90 days", value="90d", selected=(time_period == "90d")),
                    label="Time Period",
                    name="time_period",
                    id="snapshot-time-period",
                    cls="space-y-2 mb-3",
                ),
                Div(
                    Label("Domains"),
                    Div(*domain_checkboxes, cls="flex flex-wrap gap-4 mt-1"),
                    cls="space-y-2 mb-4",
                ),
                Div(
                    Button(
                        "Load Snapshot",
                        type="submit",
                        cls=ButtonT.secondary,
                    ),
                    cls="text-right",
                ),
                hx_get="/activity-review/snapshot-fragment",
                hx_target="#snapshot-display",
                hx_swap="innerHTML",
                hx_include="[name='subject_uid'],[name='time_period'],[name='domains']",
            )
        ),
        cls="mb-4",
    )


def render_feedback_form(subject_uid: str = "", time_period: str = "7d") -> Any:
    """Build the feedback submission form card."""
    return Card(
        CardHeader(CardTitle("Write Feedback")),
        CardBody(
            Form(
                Input(
                    type="hidden",
                    name="subject_uid",
                    id="feedback-subject-uid",
                    value=subject_uid,
                ),
                Input(
                    type="hidden",
                    name="time_period",
                    id="feedback-time-period",
                    value=time_period,
                ),
                LabelTextArea(
                    "Feedback",
                    name="feedback_text",
                    placeholder="Write your qualitative feedback here. What patterns do you notice? What recommendations do you have?",
                    input_cls="h-40",
                    cls="space-y-2 mb-4",
                ),
                Div(
                    Button(
                        "Submit Feedback",
                        type="submit",
                        cls=ButtonT.primary,
                    ),
                    cls="text-right",
                ),
                Div(id="submit-status", cls="mt-3"),
                hx_post="/activity-review/submit-feedback",
                hx_target="#submit-status",
                hx_swap="innerHTML",
                hx_include="[name='subject_uid'],[name='time_period'],[name='feedback_text']",
            ),
            # Sync hidden fields from snapshot form before posting
            Script(
                NotStr("""
            document.body.addEventListener('htmx:afterRequest', function(evt) {
                if (evt.detail.elt.getAttribute('hx-target') === '#snapshot-display') {
                    var subjectEl = document.getElementById('snapshot-subject-uid');
                    var periodEl = document.getElementById('snapshot-time-period');
                    var fbSubjectEl = document.getElementById('feedback-subject-uid');
                    var fbPeriodEl = document.getElementById('feedback-time-period');
                    if (subjectEl && fbSubjectEl) fbSubjectEl.value = subjectEl.value;
                    if (periodEl && fbPeriodEl) fbPeriodEl.value = periodEl.value;
                }
            });
            """)
            ),
        ),
        cls="mt-4",
    )
