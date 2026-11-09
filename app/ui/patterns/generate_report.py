"""Activity report request forms and the period prompt.

The submit-activity-report page (where the GradeBook's "Request activity report"
button and the calendar toolbar's "Report for …" pill land) holds two cards: the
machine report, generated now, and the personal review, asked of a person and
answered later in the GradeBook. The period prompt is what
``POST /activity-reports/for`` (the detail page's "Regenerate") renders when it
refuses to mint the period's report.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, get_args

from fasthtml.common import H3, Div, Fieldset, Form, Input, Label, Legend, Option, P

from core.models.entity_requests import ActivityReviewDomain
from core.utils.report_periods import report_period_token
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone
from ui.components import Button, ButtonT, Card, CardBody
from ui.forms import Checkbox, LabelTextArea, Select
from ui.journals.period_links import period_link, period_step
from ui.patterns.csrf import csrf_hidden_input
from ui.patterns.format_date import format_date
from ui.patterns.loading import content_loading_placeholder

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.ports.query_types import ReviewRequestResult

#: The personal-review card's id: the request door answers the card re-rendered.
ACTIVITY_REVIEW_CARD_ID = "activity-review-request"

# The trailing windows, in the order the form lists them. Their tokens are
# ``ReportTimePeriod.DAYS``' keys; the calendar options below are derived from
# the day the form renders on.
_TRAILING_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Last 7 days", "7d"),
    ("Last 14 days", "14d"),
    ("Last 30 days", "30d"),
    ("Last 90 days", "90d"),
)


def period_options(today: date) -> list[tuple[str, str]]:
    """The form's (label, token) pairs: the trailing windows, then the current
    and previous month and ISO week — the calendar periods a report can be
    aligned to, named the way the periodic notes name them."""
    options = list(_TRAILING_OPTIONS)
    for kind, steps, prefix in (
        ("monthly", 0, "This month"),
        ("monthly", -1, "Last month"),
        ("weekly", 0, "This week"),
        ("weekly", -1, "Last week"),
    ):
        anchor = period_step(kind, today, steps)
        link = period_link(kind, anchor)
        options.append((f"{prefix} · {link.label}", report_period_token(kind, anchor)))
    return options


def render_activity_report_request_card(today: date | None = None) -> FT:
    """Card with time period + depth selectors; its button generates the report now."""
    options = period_options(today or today_in(current_zone()))
    return Card(
        CardBody(
            H3("Submit Activity Report Request", cls="font-semibold mb-4"),
            Form(
                Div(
                    Label("Time Period", cls="label"),
                    Select(
                        *[
                            Option(label, value=token, selected=(token == "7d"))
                            for label, token in options
                        ],
                        name="time_period",
                    ),
                    cls="mb-3",
                ),
                Div(
                    Label("Depth", cls="label"),
                    Select(
                        Option("Summary (counts only)", value="summary"),
                        Option(
                            "Standard (counts + examples)",
                            value="standard",
                            selected=True,
                        ),
                        Option("Detailed (full breakdown)", value="detailed"),
                        name="depth",
                    ),
                    cls="mb-4",
                ),
                Div(
                    Button(
                        "Generate now",
                        type="submit",
                        cls=ButtonT.primary,
                    ),
                    cls="text-center",
                ),
                Div(id="generate-status", cls="mt-4"),
                # A plain form post: HTMX sends the enclosing form's fields
                # url-encoded, which is what the handler parses.
                hx_post="/api/reports/progress/generate",
                hx_target="#generate-status",
                hx_swap="innerHTML",
            ),
        ),
        cls="bg-background shadow-xs mb-6",
    )


def render_period_report_prompt(
    *,
    token: str,
    label: str,
    is_closed: bool,
    has_started: bool = True,
    note: str | None = None,
) -> FT:
    """The period's "not generated" state: the refusal (``note``) and the offer
    to try again.

    A plain (non-HTMX) form so the transition that mints the report is one
    CSRF-protected POST the user chose — never a prefetch or a speculative
    navigation. A period that has not started offers no form: there is nothing
    to count yet.
    """
    if not has_started:
        status = f"{label} has not started; a report can be generated once it begins."
    elif is_closed:
        status = f"{label} has closed; its report will count the whole period."
    else:
        status = f"{label} is still open; a report now is partial, counted through today."
    return Card(
        CardBody(
            H3(f"Generate a report for {label}", cls="font-semibold mb-2"),
            P(status, cls="text-sm text-muted-foreground mb-4"),
            P(note, cls="text-sm text-warning mb-4", role="status") if note else None,
            Form(
                csrf_hidden_input(),
                Input(type="hidden", name="time_period", value=token),
                Button("Generate report", type="submit", cls=ButtonT.primary),
                method="post",
                action="/activity-reports/for",
            )
            if has_started
            else None,
        ),
        cls="bg-background shadow-xs",
    )


def render_activity_review_request_card(
    pending: ReviewRequestResult | None = None,
    *,
    note: str | None = None,
    today: date | None = None,
) -> FT:
    """The personal-review card: ask a person to read your activity and write feedback.

    With a pending request it says so, and offers no second ask (one at a time).
    ``note`` is a refusal from the request door, shown above the form. The door
    answers with this card re-rendered (``ACTIVITY_REVIEW_CARD_ID``).
    """
    intro = P(
        "A person reads your activity for the period and writes you feedback. "
        "It arrives in your GradeBook.",
        cls="text-sm text-muted-foreground mb-4",
    )
    note_line = P(note, cls="text-sm text-error mb-3", role="alert") if note else None
    if pending is not None:
        message = pending.get("message") or ""
        body: FT = Div(
            P(
                f"You asked on {format_date(pending.get('created_at', ''))} "
                f"for {pending.get('time_period', '')}; it's waiting.",
                cls="font-semibold",
                data_announce="Review requested",
            ),
            P(message, cls="text-sm text-muted-foreground mt-2 whitespace-pre-wrap")
            if message
            else None,
        )
    else:
        options = period_options(today or today_in(current_zone()))
        body = Form(
            Div(
                Label("Time Period", cls="label", _for="review-time-period"),
                Select(
                    *[
                        Option(label, value=token, selected=(token == "7d"))
                        for label, token in options
                    ],
                    name="time_period",
                    id="review-time-period",
                ),
                cls="mb-3",
            ),
            Fieldset(
                Legend("Activities", cls="label"),
                Div(
                    *[
                        Div(
                            Checkbox(
                                name="domains",
                                value=domain,
                                checked=True,
                                id=f"review-domain-{domain}",
                            ),
                            Label(domain.title(), _for=f"review-domain-{domain}", cls="ml-2"),
                            cls="flex items-center gap-1",
                        )
                        for domain in get_args(ActivityReviewDomain)
                    ],
                    cls="flex flex-wrap gap-4 mt-1",
                ),
                cls="mb-3",
            ),
            LabelTextArea(
                "Message (optional)",
                name="message",
                id="review-message",
                placeholder="Anything you'd like the reviewer to look at?",
                maxlength="1000",
                cls="space-y-2 mb-4",
            ),
            Div(
                Button("Ask for a review", type="submit", cls=ButtonT.primary),
                cls="text-center",
            ),
            hx_post="/api/activity-reviews/request",
            hx_target=f"#{ACTIVITY_REVIEW_CARD_ID}",
            hx_swap="outerHTML",
        )
    return Card(
        CardBody(
            H3("Ask for a personal review", cls="font-semibold mb-2"),
            intro,
            note_line,
            body,
        ),
        id=ACTIVITY_REVIEW_CARD_ID,
        cls="bg-background shadow-xs mb-6",
    )


def render_recent_reports_section() -> FT:
    """HTMX-loading section for recent activity reports."""
    return Div(
        H3("Recent Activity Reports", cls="font-semibold mb-4"),
        content_loading_placeholder("/reports/progress-list", "progress-list"),
    )
