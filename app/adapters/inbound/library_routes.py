"""Library Routes — Orchestrator for Library Hub UI Routes
==========================================================

Wires the Library browsing hub:
- library_ui.py → /library, /library/exercises, /library/resources, /library/ku, /library/path-steps

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.library_ui import create_library_ui_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.library")


def create_library_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> None:
    """Wire Library hub routes."""

    create_library_ui_routes(
        app,
        rt,
        exercises_service=getattr(services, "exercises", None),
        resource_service=getattr(services, "resource", None),
        ku_service=getattr(services, "ku", None),
        ps_service=getattr(services, "ps", None),
        submissions_service=getattr(services, "submissions", None),
        user_relationship_service=getattr(services, "user_relationships", None),
    )

    logger.info("Library hub routes wired")
