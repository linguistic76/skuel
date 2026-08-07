"""Analytics dashboard, period fields, and result rendering."""

from typing import Any

from fasthtml.common import Div, Form, Label, Option, P

from ui.analytics.domain_metrics import render_metrics_cards
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle
from ui.forms import Input, Select
from ui.layouts.navbar import create_navbar_for_request
from ui.patterns.page_header import PageHeader


def render_analytics_dashboard(request: Any) -> Any:
    """Main analytics dashboard - select domain and period."""
    navbar = create_navbar_for_request(request, active_page="analytics")

    return Div(
        navbar,
        PageHeader(
            "Analytics Dashboard",
            subtitle="Generate statistical analytics for any domain. Pure metrics — no AI recommendations, just transparent data.",
        ),
        Card(
            CardHeader(CardTitle("Generate Analytics")),
            CardBody(
                Form(
                    Div(
                        Label("Domain", cls="label"),
                        Select(
                            Option("Tasks", value="tasks"),
                            Option("Habits", value="habits"),
                            Option("Goals", value="goals"),
                            Option("Events", value="events"),
                            Option("Choices", value="choices"),
                            Option("Principles", value="principles"),
                            name="analytics_domain",
                            id="analytics-domain-select",
                        ),
                        cls="mb-4",
                    ),
                    Div(
                        Label("Period", cls="label"),
                        Select(
                            Option("This Week", value="week_current"),
                            Option("Last Week", value="week_last"),
                            Option("This Month", value="month_current"),
                            Option("Last Month", value="month_last"),
                            Option("This Year", value="year_current"),
                            Option("Custom Range", value="custom"),
                            name="period",
                            id="period-select",
                            hx_get="/ui/analytics/period-fields",
                            hx_target="#period-fields",
                            hx_trigger="change",
                        ),
                        cls="mb-4",
                    ),
                    Div(id="period-fields"),
                    Div(
                        Button(
                            "Generate Analytics",
                            type="button",
                            hx_get="/ui/analytics/view",
                            hx_include="[name='analytics_domain'],[name='period'],[name='start_date'],[name='end_date']",
                            hx_target="#analytics-display",
                            cls=ButtonT.primary,
                        ),
                        cls="mb-4",
                    ),
                )
            ),
            cls="mb-6",
        ),
        Div(id="analytics-display", cls="mt-6"),
        cls="container mx-auto p-6",
    )


def render_period_fields(period: str) -> Any:
    """Dynamic period input fields."""
    if period == "custom":
        return Div(
            Div(
                Label("Start Date", cls="label"),
                Input(type="date", name="start_date"),
                cls="mb-4",
            ),
            Div(
                Label("End Date", cls="label"),
                Input(type="date", name="end_date"),
                cls="mb-4",
            ),
        )
    return ""


def render_analytics_result(report: Any) -> Any:
    """Render generated analytics result."""
    return Div(
        Card(
            CardHeader(CardTitle(report.title)),
            CardBody(
                P(
                    f"{report.format_period()} • Generated {report.generated_at.strftime('%Y-%m-%d %H:%M')}",
                    cls="text-muted-foreground text-sm",
                ),
            ),
            cls="mb-4",
        ),
        render_metrics_cards(report),
        Div(
            Button(
                "View as Markdown",
                cls=(ButtonT.ghost, "mb-4"),
                **{"@click": "showMarkdown = !showMarkdown"},  # fasthtml dynamic-attr splat
            ),
            render_markdown_view(report.markdown_content),
            **{"x-data": "{ showMarkdown: false }"},
        ),
        cls="mt-6",
    )


def render_markdown_view(markdown_content: str) -> Any:
    """Render markdown content, toggled by Alpine showMarkdown state."""
    return Card(
        Div(markdown_content, cls="whitespace-pre-wrap leading-relaxed text-foreground"),
        cls="bg-background shadow-xs p-6 mt-4",
        **{"x-show": "showMarkdown", "x-cloak": True},
    )
