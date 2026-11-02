"""Library Routes — Orchestrator-Driven Registration
==========================================================

Wires the Library browsing hub via LibraryOrchestrator:
- library_ui.py → /library, /library/exercises, /library/resources, /library/ku, /library/path-steps
"""

from typing import TYPE_CHECKING

from adapters.inbound.fasthtml_types import RouteDecorator
from adapters.inbound.library_ui import create_library_ui_routes
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from services_bootstrap import Services

logger = get_logger("skuel.routes.library")


def create_library_routes(rt: RouteDecorator, services: Services) -> None:
    """Wire Library hub routes via LibraryOrchestrator.

    An absent orchestrator is a warning and registers nothing.
    """
    orchestrator = services.library_orchestrator
    if orchestrator is None:
        logger.warning("Library hub routes skipped: LibraryOrchestrator unavailable")
        return
    create_library_ui_routes(rt, orchestrator=orchestrator)
    logger.info("Library hub routes wired")
