"""
LifePath UI Routes
==================

UI routes for LifePath domain. All HTML construction delegated to ui/lifepath/.

UI Routes:
- GET /lifepath - Main dashboard
- GET /lifepath/content - HTMX fragment: dashboard body
- GET /lifepath/vision - Vision capture page
- POST /lifepath/vision - Process vision capture
- POST /lifepath/designate - Designate an LP as life path
- GET /lifepath/alignment - Alignment dashboard
- GET /lifepath/alignment/content - HTMX fragment: alignment dashboard body
- GET /api/lifepath/alignment/chart - Chart.js radar config (5 dimensions)
"""

import asyncio
from typing import TYPE_CHECKING, Any

from fasthtml.common import FT, Div
from starlette.responses import HTMLResponse, RedirectResponse

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import safe_form_string
from core.config.settings import get_settings
from core.ports.query_types import AlignmentDimensions, ChartJsConfig
from core.utils.logging import get_logger
from core.utils.palette import ChartColor, SemanticColor, rgba
from core.utils.result_simplified import ErrorCategory, ErrorContext, Result
from ui.lifepath import (
    lifepath_sidebar_page,
    render_alignment_dashboard,
    render_dashboard_content,
    render_designation_refused,
    render_lived_cards,
    render_recommendations_page,
    render_vision_form,
)
from ui.patterns.error_banner import render_error_banner
from ui.patterns.loading import content_loading_placeholder

if TYPE_CHECKING:
    from core.services.analytics_service import AnalyticsService

logger = get_logger("skuel.routes.lifepath.ui")


def _read_failed_banner(message: str, error: ErrorContext) -> FT:
    """A failed read's banner: a plain sentence, its detail only in debug."""
    return render_error_banner(
        message, technical_details=error.message, show_details=get_settings().application.debug
    )


def _refusal_banner(error: ErrorContext, retry_message: str) -> FT:
    """The banner a refused Life Path form shows: a validation refusal's own
    reason, anything else a plain retry message (its detail only in debug)."""
    if error.category == ErrorCategory.VALIDATION:
        return render_error_banner(error.message)
    return _read_failed_banner(retry_message, error)


# ============================================================================
# ROUTE HANDLERS
# ============================================================================


def create_lifepath_ui_routes(
    _app: Any,
    rt: Any,
    lifepath_service: Any,
    analytics_service: AnalyticsService,
) -> None:
    """Create LifePath UI routes.

    ``analytics_service`` supplies the alignment page's step-level half: the
    learner's personal substance over every step of the designated path.
    """

    @rt("/lifepath")
    def lifepath_dashboard(request: Request) -> Any:
        """Main life path dashboard — shell only, content loads via HTMX."""
        require_authenticated_user(request)
        content = content_loading_placeholder("/lifepath/content", "lifepath-dashboard-content")
        return lifepath_sidebar_page("dashboard", content, request)

    @rt("/lifepath/content")
    async def lifepath_dashboard_content(request: Request) -> Any:
        """HTMX fragment: lifepath dashboard body."""
        user_uid = require_authenticated_user(request)
        status_result = await lifepath_service.get_full_status(user_uid)
        if status_result.is_error:
            return Div(
                _read_failed_banner("Could not load your Life Path", status_result.expect_error()),
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

        result = await lifepath_service.capture_and_recommend(user_uid, vision_statement)
        if result.is_error:
            refusal = _refusal_banner(result.expect_error(), "Could not read your vision")
            return lifepath_sidebar_page(
                "vision", render_vision_form(vision_statement, refusal), request
            )

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
            refusal = render_error_banner("Please choose a Learning Path.")
            return lifepath_sidebar_page("vision", render_designation_refused(refusal), request)

        result = await lifepath_service.designate_and_calculate(user_uid, life_path_uid)
        if result.is_error:
            refusal = _refusal_banner(result.expect_error(), "Could not set your Life Path")
            return lifepath_sidebar_page("vision", render_designation_refused(refusal), request)

        return RedirectResponse(url="/lifepath/alignment", status_code=303)

    @rt("/lifepath/alignment")
    def alignment_dashboard(request: Request) -> FT:
        """Alignment dashboard — shell only, content loads via HTMX."""
        require_authenticated_user(request)
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
    async def alignment_dashboard_content(request: Request) -> FT | HTMLResponse:
        """HTMX fragment: lifepath alignment body.

        The five-dimension alignment and the steps' personal substance are read
        together; a failed substance read banners its own cards and leaves the
        five-dimension half standing.
        """
        user_uid = require_authenticated_user(request)
        status_result, lived_result = await asyncio.gather(
            lifepath_service.get_full_status(user_uid),
            analytics_service.calculate_life_path_alignment(user_uid),
        )
        if status_result.is_error:
            return Div(
                _read_failed_banner(
                    "Could not load your Life Path alignment", status_result.expect_error()
                ),
                id="lifepath-alignment-content",
            )
        status = status_result.value
        if not status.get("has_designation"):
            return HTMLResponse("", status_code=200, headers={"HX-Redirect": "/lifepath/vision"})
        lived = (
            _read_failed_banner(
                "Could not load how your path's steps are lived", lived_result.expect_error()
            )
            if lived_result.is_error
            else render_lived_cards(lived_result.value)
        )
        return Div(render_alignment_dashboard(status, lived), id="lifepath-alignment-content")

    @rt("/api/lifepath/alignment/chart")
    @boundary_handler(success_status=200)
    async def alignment_radar_chart(request: Request) -> Result[ChartJsConfig]:
        """Chart.js radar config for the 5 alignment dimensions.

        Fetched by the chartVis Alpine component on the /lifepath/alignment
        dashboard. Without a designation the alignment carries no dimensions and
        the radar draws an empty frame; a failed alignment read is an error
        response, which the card shows.
        """
        user_uid = require_authenticated_user(request)
        alignment_result = await lifepath_service.get_alignment(user_uid)
        if alignment_result.is_error:
            return Result.fail(alignment_result)
        return Result.ok(_alignment_radar_config(alignment_result.value.get("dimensions")))

    logger.info("LifePath UI routes registered")


def _alignment_radar_config(dimensions: AlignmentDimensions | None) -> ChartJsConfig:
    """The radar's Chart.js config: one axis from 0 to 1 per alignment dimension.

    The axes carry the names the score rows below the radar print, and the
    scale draws no tick numbers: Chart.js puts them along the first axis, under
    its point, and the rows print every score.
    """
    scores = (
        [
            dimensions["knowledge"],
            dimensions["activity"],
            dimensions["goal"],
            dimensions["principle"],
            dimensions["momentum"],
        ]
        if dimensions
        else [0.0] * 5
    )
    return {
        "type": "radar",
        "data": {
            "labels": ["Knowledge", "Activity", "Goal", "Principle", "Momentum"],
            "datasets": [
                {
                    "label": "Your Alignment",
                    "data": [float(score) for score in scores],
                    "backgroundColor": rgba(SemanticColor.PRIMARY, ChartColor.AREA_ALPHA),
                    "borderColor": rgba(SemanticColor.PRIMARY, 1),
                    "borderWidth": 2,
                    "pointBackgroundColor": rgba(SemanticColor.PRIMARY, 1),
                    "pointBorderColor": ChartColor.POINT_BORDER,
                }
            ],
        },
        "options": {
            "scales": {"r": {"min": 0, "max": 1, "ticks": {"stepSize": 0.2, "display": False}}},
            "plugins": {"legend": {"display": False}},
        },
    }
