"""Analytics dashboard, period fields, and result rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, Form, Label, Option, P

from ui.analytics.domain_metrics import render_metrics_cards
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle
from ui.forms import Input, Select
from ui.layouts.base_page import BasePage
from ui.patterns.format_date import format_date
from ui.patterns.page_header import PageHeader

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request


def render_analytics_dashboard(request: Request) -> FT:
    """The analytics dashboard page: pick a domain and a period, and the result
    loads into the page below the form."""
    body = Div(
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
                    Button(
                        "Generate Analytics",
                        type="button",
                        hx_get="/ui/analytics/view",
                        hx_include="[name='analytics_domain'],[name='period'],[name='start_date'],[name='end_date']",
                        hx_target="#analytics-display",
                        cls=ButtonT.primary,
                    ),
                )
            ),
        ),
        # The slot spaces whatever is swapped into it (a result, an inline error, a
        # boundary banner) from the form; while empty it is out of the layout.
        Div(id="analytics-display", cls="mt-6 empty:hidden"),
    )
    return BasePage(body, title="Analytics", request=request)


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
                    f"{report.format_period()} • Generated {format_date(report.generated_at, '%Y-%m-%d %H:%M')}",
                    cls="text-muted-foreground text-sm",
                ),
            ),
            cls="mb-4",
        ),
        render_metrics_cards(report),
        Div(
            Button(
                "View as Markdown",
                cls=ButtonT.ghost,
                **{"@click": "showMarkdown = !showMarkdown"},  # fasthtml dynamic-attr splat
            ),
            render_markdown_view(report.markdown_content),
            cls="mt-4",
            **{"x-data": "{ showMarkdown: false }"},
        ),
    )


def render_markdown_view(markdown_content: str) -> Any:
    """Render markdown content, toggled by Alpine showMarkdown state."""
    return Card(
        Div(markdown_content, cls="whitespace-pre-wrap leading-relaxed text-foreground"),
        cls="bg-background shadow-xs p-6 mt-4",
        **{"x-show": "showMarkdown", "x-cloak": True},
    )
