"""
LifePath UI Routes
==================

UI routes for LifePath domain. All HTML construction delegated to ui/lifepath/.

UI Routes:
- GET /lifepath - Main dashboard
- GET /lifepath/vision - Vision capture page
- POST /lifepath/vision - Process vision capture
- POST /lifepath/designate - Designate an LP as life path
- GET /lifepath/alignment - Alignment dashboard
- GET /api/lifepath/alignment/chart - Chart.js radar config (5 dimensions)
"""

from typing import Any

from fasthtml.common import Div
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import safe_form_string
from core.config.settings import get_settings
from core.utils.logging import get_logger
from ui.components import ButtonT
from ui.lifepath import (
    lifepath_sidebar_page,
    render_alignment_dashboard,
    render_dashboard_content,
    render_recommendations_page,
    render_vision_form,
)
from ui.patterns.error_banner import render_error_banner
from ui.patterns.loading import content_loading_placeholder
from ui.primitives import ButtonLink

logger = get_logger("skuel.routes.lifepath.ui")


# ============================================================================
# ERROR HELPERS
# ============================================================================


def _service_unavailable_page() -> Any:
    """Return page when LifePath service is not available."""
    return Div(
        render_error_banner(
            "Service Unavailable",
            technical_details="The LifePath service is not available. Please try again later.",
            show_details=get_settings().application.debug,
        ),
        cls="container mx-auto px-4 py-8",
    )


def _error_page(message: str) -> Any:
    """Return error page."""
    return Div(
        render_error_banner(
            "Error",
            technical_details=message,
            show_details=get_settings().application.debug,
        ),
        ButtonLink("Go back", href="/lifepath", cls=(ButtonT.primary, "mt-4")),
        cls="container mx-auto px-4 py-8",
    )


# ============================================================================
# ROUTE HANDLERS
# ============================================================================


def create_lifepath_ui_routes(
    _app: Any,
    rt: Any,
    lifepath_service: Any,
    services: Any = None,
) -> list[Any]:
    """Create LifePath UI routes."""

    @rt("/lifepath")
    def lifepath_dashboard(request: Request) -> Any:
        """Main life path dashboard — shell only, content loads via HTMX."""
        require_authenticated_user(request)
        if not lifepath_service:
            return _service_unavailable_page()
        content = content_loading_placeholder("/lifepath/content", "lifepath-dashboard-content")
        return lifepath_sidebar_page("dashboard", content, request)

    @rt("/lifepath/content")
    async def lifepath_dashboard_content(request: Request) -> Any:
        """HTMX fragment: lifepath dashboard body."""
        user_uid = require_authenticated_user(request)
        if not lifepath_service:
            return Div(render_error_banner("Service Unavailable"), id="lifepath-dashboard-content")
        status_result = await lifepath_service.get_full_status(user_uid)
        if status_result.is_error:
            return Div(
                render_error_banner(str(status_result.expect_error())),
                id="lifepath-dashboard-content",
            )
        return Div(
            render_dashboard_content(status_result.value, user_uid),
            id="lifepath-dashboard-content",
        )

    @rt("/lifepath/vision", methods=["GET"])
    async def vision_capture_page(request: Request) -> Any:
        """Vision capture page - where user expresses their vision."""
        user_uid = require_authenticated_user(request)

        if not lifepath_service:
            return _service_unavailable_page()

        designation_result = await lifepath_service.core.get_designation(user_uid)
        existing_vision = ""
        if designation_result.is_ok and designation_result.value:
            existing_vision = designation_result.value.vision_statement

        content = render_vision_form(existing_vision)
        return lifepath_sidebar_page("vision", content, request)

    @rt("/lifepath/vision", methods=["POST"])
    @csrf_protected
    async def process_vision_capture(request: Request) -> Any:
        """Process vision capture and show recommendations."""
        user_uid = require_authenticated_user(request)

        form = await request.form()
        vision_statement = safe_form_string(form.get("vision_statement"))

        if not vision_statement or len(vision_statement) < 10:
            return _error_page("Please provide a vision statement of at least 10 characters.")

        if not lifepath_service:
            return _service_unavailable_page()

        result = await lifepath_service.capture_and_recommend(user_uid, vision_statement)
        if result.is_error:
            return _error_page(str(result.expect_error()))

        content = render_recommendations_page(result.value, user_uid)
        return lifepath_sidebar_page("vision", content, request)

    @rt("/lifepath/designate", methods=["POST"])
    @csrf_protected
    async def designate_life_path(request: Request) -> Any:
        """Designate an LP as the user's life path."""
        user_uid = require_authenticated_user(request)

        form = await request.form()
        life_path_uid = safe_form_string(form.get("life_path_uid"))

        if not life_path_uid:
            return _error_page("Please select a Learning Path.")

        if not lifepath_service:
            return _service_unavailable_page()

        result = await lifepath_service.designate_and_calculate(user_uid, life_path_uid)
        if result.is_error:
            return _error_page(str(result.expect_error()))

        return RedirectResponse(url="/lifepath/alignment", status_code=303)

    @rt("/lifepath/alignment")
    def alignment_dashboard(request: Request) -> Any:
        """Alignment dashboard — shell only, content loads via HTMX."""
        require_authenticated_user(request)
        if not lifepath_service:
            return _service_unavailable_page()
        content = content_loading_placeholder(
            "/lifepath/alignment/content", "lifepath-alignment-content"
        )
        return lifepath_sidebar_page(
            "alignment",
            content,
            request,
            extra_scripts=["/static/vendor/chart.js/chart.umd.js"],
        )

    @rt("/lifepath/alignment/content")
    async def alignment_dashboard_content(request: Request) -> Any:
        """HTMX fragment: lifepath alignment body."""
        user_uid = require_authenticated_user(request)
        if not lifepath_service:
            return Div(render_error_banner("Service Unavailable"), id="lifepath-alignment-content")
        status_result = await lifepath_service.get_full_status(user_uid)
        if status_result.is_error:
            return Div(
                render_error_banner(str(status_result.expect_error())),
                id="lifepath-alignment-content",
            )
        status = status_result.value
        if not status.get("has_designation"):
            return HTMLResponse("", status_code=200, headers={"HX-Redirect": "/lifepath/vision"})
        return Div(render_alignment_dashboard(status, user_uid), id="lifepath-alignment-content")

    @rt("/api/lifepath/alignment/chart")
    async def alignment_radar_chart(request: Request) -> Any:
        """Chart.js radar config for the 5 alignment dimensions.

        Fetched by the chartVis Alpine component on the /lifepath/alignment
        dashboard. Zeroed data on error/no designation so the chart still
        renders a frame.
        """
        user_uid = require_authenticated_user(request)

        dimensions: dict[str, float] = {}
        if lifepath_service:
            alignment_result = await lifepath_service.get_alignment(user_uid)
            if alignment_result.is_ok:
                dimensions = alignment_result.value.get("dimensions") or {}

        labels = ["Knowledge", "Activity", "Goals", "Principles", "Momentum"]
        keys = ["knowledge", "activity", "goal", "principle", "momentum"]
        data = [float(dimensions.get(key, 0.0)) for key in keys]

        return JSONResponse(
            {
                "type": "radar",
                "data": {
                    "labels": labels,
                    "datasets": [
                        {
                            "label": "Your Alignment",
                            "data": data,
                            "backgroundColor": "rgba(59, 130, 246, 0.2)",
                            "borderColor": "rgba(59, 130, 246, 1)",
                            "borderWidth": 2,
                            "pointBackgroundColor": "rgba(59, 130, 246, 1)",
                            "pointBorderColor": "#fff",
                        }
                    ],
                },
                "options": {
                    "scales": {"r": {"min": 0, "max": 1, "ticks": {"stepSize": 0.2}}},
                    "plugins": {"legend": {"display": False}},
                },
            }
        )

    logger.info("LifePath UI routes registered (6 routes)")

    return [
        lifepath_dashboard,
        lifepath_dashboard_content,
        vision_capture_page,
        process_vision_capture,
        designate_life_path,
        alignment_dashboard,
        alignment_dashboard_content,
        alignment_radar_chart,
    ]
