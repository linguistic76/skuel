"""
Transfer UI Routes — Submission Hub
=====================================

The /transfer page is the submission hub. "Transfer" is the user-facing
name for the act of submitting work. Tabs: My Submissions | Submit | Generate.

Default tab loads on page load; non-default tabs lazy-load on first click
(via custom 'tab-activate' event + 'once').

Routes:
- GET /transfer — Submission hub (tabbed)
- GET /transfer/submit-form — HTMX fragment: upload form
- GET /transfer/generate-form — HTMX fragment: generate report form
"""

from typing import Any

from fasthtml.common import (
    H3,
    Div,
    Form,
    Label,
    Option,
    P,
)
from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import RouteDecorator, RouteList
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody
from ui.forms import Select
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.page_header import PageHeader
from ui.submissions.forms import render_upload_form, upload_form_script

logger = get_logger("skuel.routes.transfer")


# ============================================================================
# TAB COMPONENT
# ============================================================================


def _tab_button(label: str, tab_id: str) -> Any:
    """Single tab button with inline Alpine.js state.

    On click, sets the active tab and dispatches a custom 'tab-activate'
    event on the target panel so HTMX can lazy-load its content.
    """
    from fasthtml.common import A

    return A(
        label,
        role="tab",
        cls="px-4 py-2 text-sm font-medium cursor-pointer transition-colors rounded-t border-b-2",
        **{
            ":aria-selected": f"tab === '{tab_id}'",
            "@click": f"tab = '{tab_id}'; htmx.trigger('#tab-panel-{tab_id}', 'tab-activate')",
            ":class": f"tab === '{tab_id}' ? 'border-primary text-primary bg-background' : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'",
        },
    )


def _tab_panel(tab_id: str, hx_get: str, default: bool = False) -> Div:
    """Tab panel with lazy-loaded HTMX content.

    Default tabs load immediately (hx-trigger="load"). Non-default tabs
    load on first activation via a custom 'tab-activate' event dispatched
    by _tab_button. The 'once' modifier ensures content is fetched only once.
    """
    attrs: dict[str, str] = {
        "x-show": f"tab === '{tab_id}'",
        "hx-get": hx_get,
        "hx-trigger": "load" if default else "tab-activate once",
        "hx-swap": "innerHTML",
    }
    if not default:
        attrs["x-cloak"] = ""

    return Div(
        P("Loading...", cls="text-center text-muted-foreground py-4"),
        id=f"tab-panel-{tab_id}",
        role="tabpanel",
        **attrs,
    )


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_transfer_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    services: Any,
) -> RouteList:
    """Register /transfer UI routes.

    Args:
        _app: FastHTML application instance.
        rt: Router instance.
        services: Service container — uses submissions, exercises,
            submissions_search, submissions_core, activity_report.
    """

    # ========================================================================
    # TRANSFER HUB
    # ========================================================================

    @rt("/transfer")
    async def transfer_landing(request: Request) -> Any:
        """Transfer hub — tabbed submission view."""
        require_authenticated_user(request)

        content = Div(
            PageHeader(
                "Transfer",
                subtitle="Submit work and track submissions",
            ),
            Div(
                Div(
                    _tab_button("My Submissions", "submissions"),
                    _tab_button("Submit", "submit"),
                    _tab_button("Generate", "generate"),
                    role="tablist",
                    cls="flex gap-1 border-b border-border mb-4",
                ),
                _tab_panel("submissions", "/submissions/list", default=True),
                _tab_panel("submit", "/transfer/submit-form"),
                _tab_panel("generate", "/transfer/generate-form"),
                **{"x-data": "{ tab: 'submissions' }"},
            ),
            cls="px-4 sm:px-6 lg:px-10 py-6",
        )

        return await BasePage(
            content=content,
            title="Transfer",
            request=request,
            active_page="transfer",
            page_type=PageType.CUSTOM,
        )

    # ========================================================================
    # HTMX FRAGMENTS — tab content
    # ========================================================================

    @rt("/transfer/submit-form")
    async def transfer_submit_form(request: Request) -> Any:
        """HTMX fragment: upload form with exercise selector for Submit tab."""
        try:
            user_uid = require_authenticated_user(request)

            assigned_exercises: list[Any] = []
            exercises_service = getattr(services, "exercises", None)
            if exercises_service:
                exercises_result = await exercises_service.get_student_exercises(user_uid)
                if not exercises_result.is_error and exercises_result.value:
                    assigned_exercises = exercises_result.value

            return Div(
                render_upload_form(assigned_exercises),
                upload_form_script(),
            )
        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading submit form: {e}", exc_info=True)
            from ui.patterns.error_banner import render_error_banner

            return Div(render_error_banner("Failed to load submit form", str(e)))

    @rt("/transfer/generate-form")
    async def transfer_generate_form(request: Request) -> Any:
        """HTMX fragment: generate report form + recent reports for Generate tab."""
        try:
            require_authenticated_user(request)

            generate_card = Card(
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

            recent_reports = Div(
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

            return Div(generate_card, recent_reports)
        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading generate form: {e}", exc_info=True)
            from ui.patterns.error_banner import render_error_banner

            return Div(render_error_banner("Failed to load generate form", str(e)))

    logger.info(
        "Transfer UI routes created (/transfer, /transfer/submit-form, /transfer/generate-form)"
    )
    return []  # Routes registered via @rt() decorators
