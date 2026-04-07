"""Library Routes — Orchestrator-Driven Registration
==========================================================

Wires the Library browsing hub via LibraryOrchestrator:
- library_ui.py → /library, /library/exercises, /library/resources, /library/ku, /library/path-steps
"""

from typing import Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.library_ui import create_library_ui_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.library")


def create_library_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> None:
    """Wire Library hub routes via LibraryOrchestrator."""
    create_library_ui_routes(app, rt, orchestrator=services.library_orchestrator)
    logger.info("Library hub routes wired")
