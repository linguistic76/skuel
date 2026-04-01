"""
Reports Hub UI Route — /reports
================================

/reports redirects 301 to /library (the unified learning hub).

The Exercise Reports and Activity Reports tabs live inside /library.
The HTMX fragment endpoints (/reports/list, /reports/activity-list) remain
in exercise_reports_ui.py and activity_reports_ui.py and are reused by /library.

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from starlette.responses import RedirectResponse

from adapters.inbound.fasthtml_types import Request, RouteDecorator, RouteList
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.reports")


def create_reports_ui_routes(
    _app: Any,
    rt: RouteDecorator,
) -> RouteList:
    """Register /reports → 301 redirect to /library."""

    @rt("/reports")
    async def reports_redirect(request: Request) -> Any:
        """Redirect legacy /reports route to /library hub."""
        return RedirectResponse(url="/library", status_code=301)

    return []
