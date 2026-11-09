"""Activity Review form components."""

from fasthtml.common import FT, Div, Form, Input, Option, Script

from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone
from ui.activity_review.types import DOMAIN_CHOICES
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle
from ui.forms import Checkbox, Label, LabelInput, LabelSelect, LabelTextArea
from ui.patterns.generate_report import period_options


def _period_options(time_period: str) -> list[FT]:
    """The report periods a learner can ask for, the requested one selected.

    A request made last week names a period today's list may no longer offer
    (``Last week`` has moved on), so a token not in the list is added as itself.
    """
    options = period_options(today_in(current_zone()))
    if time_period not in {token for _, token in options}:
        options.append((time_period, time_period))
    return [Option(label, value=token, selected=(token == time_period)) for label, token in options]


def render_snapshot_form(
    subject_uid: str = "", time_period: str = "7d", domains: list[str] | None = None
) -> FT:
    """Build the snapshot loading form card; ``domains`` ticked (none = all six)."""
    domain_checkboxes = []
    for domain_value, domain_label in DOMAIN_CHOICES:
        domain_checkboxes.append(
            Div(
                Checkbox(
                    name="domains",
                    value=domain_value,
                    checked=not domains or domain_value in domains,
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
                    *_period_options(time_period),
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


def render_feedback_form(
    subject_uid: str = "", time_period: str = "7d", review_request_uid: str = ""
) -> FT:
    """Build the feedback submission form card.

    The form posts its own fields, plus the snapshot form's ticked domains and the
    snapshot the admin loaded (``snapshot_context``, a hidden field the snapshot
    fragment renders). ``review_request_uid`` is the learner's request this review
    answers, when it was started from the queue.
    """
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
                    name="review_request_uid",
                    id="feedback-review-request-uid",
                    value=review_request_uid,
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
                # The form's own fields go with it; these two live outside it.
                hx_include="[name='domains'],[name='snapshot_context']",
            ),
            # Sync hidden fields from snapshot form before posting
            Script(src="/static/js/activity-review.js"),
        ),
        cls="mt-4",
    )
