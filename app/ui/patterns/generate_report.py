"""Activity Report Request Form — shared component for activity report submission.

Used by both the Transfer hub (HTMX fragment) and the Study submit-activity-report page.
"""

from fasthtml.common import H3, Div, Form, Label, Option

from ui.components import Button, ButtonT, Card, CardBody
from ui.forms import Select
from ui.patterns.loading import content_loading_placeholder


def render_activity_report_request_card():
    """Card with time period + depth selectors and Submit Request button."""
    return Card(
        CardBody(
            H3("Submit Activity Report Request", cls="font-semibold mb-4"),
            Form(
                Div(
                    Label("Time Period", cls="label"),
                    Select(
                        Option("Last 7 days", value="7d", selected=True),
                        Option("Last 14 days", value="14d"),
                        Option("Last 30 days", value="30d"),
                        Option("Last 90 days", value="90d"),
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


def render_recent_reports_section():
    """HTMX-loading section for recent activity reports."""
    return Div(
        H3("Recent Activity Reports", cls="font-semibold mb-4"),
        content_loading_placeholder("/reports/progress-list", "progress-list"),
    )
