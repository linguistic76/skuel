"""Generate Report Form — shared component for progress report generation.

Used by both the Transfer hub (HTMX fragment) and the Study generate-reports page.
"""

from fasthtml.common import H3, Div, Form, Label, Option, P

from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody
from ui.forms import Select


def render_generate_report_card():
    """Card with time period + depth selectors and Generate Now button."""
    return Card(
        CardBody(
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
                        "Generate Now",
                        type="submit",
                        variant=ButtonT.primary,
                    ),
                    cls="text-center",
                ),
                Div(id="generate-status", cls="mt-4"),
                **{
                    "hx-post": "/api/reports/progress/generate",
                    "hx-target": "#generate-status",
                    "hx-swap": "innerHTML",
                    "hx-vals": 'js:JSON.stringify({time_period: document.querySelector("[name=time_period]").value, depth: document.querySelector("[name=depth]").value, include_insights: true})',
                    "hx-headers": '{"Content-Type": "application/json"}',
                },
            ),
        ),
        cls="bg-background shadow-sm mb-6",
    )


def render_recent_reports_section():
    """HTMX-loading section for recent progress reports."""
    return Div(
        H3("Recent Progress Reports", cls="font-semibold mb-4"),
        Div(
            P("Loading...", cls="text-center text-muted-foreground"),
            id="progress-list",
            **{
                "hx-get": "/reports/progress-list",
                "hx-trigger": "load",
                "hx-swap": "outerHTML",
            },
        ),
    )
