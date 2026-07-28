"""
Timeline Routes - Vis.js Timeline Web Interface
===============================================

Serves the ``/timelines`` page.

Architecture (January 2026 - Vis.js Timeline):
    - UI Components: /ui/timeline/components.py
    - CSS: /static/css/timeline.css
    - Alpine.js: timelineVis component in /static/js/skuel.js
    - Vendor: /static/vendor/vis-timeline/
    - Timeline data: /api/visualizations/timeline (visualization_api.py)

Version: 3.0 - Vis.js Timeline
"""

from typing import TYPE_CHECKING

from fasthtml.common import FT

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from ui.timeline.components import (
    render_timeline_error,
    render_timeline_viewer_page,
)

if TYPE_CHECKING:
    from services_bootstrap import Services

logger = get_logger(__name__)


def create_timeline_ui_routes(_app, rt, _tasks_service: object):
    """Create the timeline viewer page route.

    The page fetches its own data from ``/api/visualizations/timeline``, so the
    injected tasks service is unused — it is present because
    ``register_domain_routes`` gates registration on it being composed.
    """

    @rt("/timelines")
    @boundary_handler()
    async def timeline_viewer(  # skuel-lint: disable=SKUEL029 -- @boundary_handler awaits the handler unconditionally
        request: Request,
        src: str | None = None,
        project: str | None = None,
        _view: str = "timeline",
    ) -> Result[FT]:
        """
        Web interface for Vis.js Timeline visualization.

        Query Parameters:
        - src: URL to timeline data source (optional - uses visualization API if not provided)
        - project: Project filter to apply
        - view: View type (timeline, calendar, gantt) - future enhancement

        Returns interactive Vis.js timeline viewer HTML page.
        """
        user_uid = require_authenticated_user(request)

        try:
            return Result.ok(
                render_timeline_viewer_page(
                    request=request,
                    src=src,
                    project=project,
                    user_uid=user_uid,
                )
            )

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error("Timeline viewer error", error=str(e))
            return Result.ok(render_timeline_error(str(e), request=request))

    return [timeline_viewer]


# ---------------------------------------------------------------------------
# DomainRouteConfig wiring
# ---------------------------------------------------------------------------

TIMELINE_CONFIG = DomainRouteConfig(
    domain_name="timeline",
    primary_service_attr="tasks",
    ui_factory=create_timeline_ui_routes,
)


def create_timeline_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None"
) -> None:
    """Wire timeline routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, TIMELINE_CONFIG)


__all__ = ["create_timeline_routes"]
