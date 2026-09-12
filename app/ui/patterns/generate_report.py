"""Activity report request form and the calendar door's "generate" state.

The request card is shared by the Transfer hub (HTMX fragment) and the Study
submit-activity-report page; the period prompt is what
``GET /activity-reports/for`` renders when the period has no reusable report
yet — the one place a report is minted from is its CSRF-protected POST.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from fasthtml.common import H3, Div, Form, Input, Label, Option, P

from core.utils.report_periods import report_period_token
from ui.components import Button, ButtonT, Card, CardBody
from ui.forms import Select
from ui.journals.period_links import period_link, period_step
from ui.patterns.csrf import csrf_hidden_input
from ui.patterns.loading import content_loading_placeholder

if TYPE_CHECKING:
    from fasthtml.common import FT

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
    """Card with time period + depth selectors and Submit Request button."""
    options = period_options(today or date.today())
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
                        "Submit Request",
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
    *, token: str, label: str, is_closed: bool, note: str | None = None
) -> FT:
    """The calendar door's "generate" state: no reusable report for the period.

    A plain (non-HTMX) form so the transition that mints the report is one
    CSRF-protected POST the user chose — never a prefetch or a speculative
    navigation of the GET that rendered this.
    """
    status = (
        f"{label} has closed; its report will count the whole period."
        if is_closed
        else f"{label} is still open; a report now is partial and re-opens until the period closes."
    )
    return Card(
        CardBody(
            H3(f"No report for {label} yet", cls="font-semibold mb-2"),
            P(status, cls="text-sm text-muted-foreground mb-4"),
            P(note, cls="text-sm text-warning mb-4", role="status") if note else None,
            Form(
                csrf_hidden_input(),
                Input(type="hidden", name="time_period", value=token),
                Button("Generate report", type="submit", cls=ButtonT.primary),
                method="post",
                action="/activity-reports/for",
            ),
        ),
        cls="bg-background shadow-xs mb-6",
    )


def render_recent_reports_section() -> FT:
    """HTMX-loading section for recent activity reports."""
    return Div(
        H3("Recent Activity Reports", cls="font-semibold mb-4"),
        content_loading_placeholder("/reports/progress-list", "progress-list"),
    )
