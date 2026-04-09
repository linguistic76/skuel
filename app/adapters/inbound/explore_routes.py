"""
Explore Routes — Orchestrator-Driven Registration
====================================================

Wires the /explore discovery page and /learning-loop engagement
fragments using the ExploreOrchestrator.

Routes:
- GET  /explore              — Discovery index
- GET  /api/explore/search   — HTMX fragment: filtered card grid
- GET  /api/explore/graph    — Hub learning universe graph (Vis.js JSON)
- GET  /explore/ku/{uid}     — Ku detail page
- GET  /explore/ps/{uid}     — PathStep detail page
- GET  /learning-loop/ps/{ps_uid}/exercises                — Exercise list fragment
- GET  /learning-loop/ps/{ps_uid}/submissions-and-feedback — Submissions + feedback fragment
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.explore_ui import create_explore_api_routes, create_explore_ui_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.learning_loop_routes import create_learning_loop_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


def create_explore_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services", _sync_service: Any = None
) -> None:
    """Wire explore UI + API routes via ExploreOrchestrator."""
    if services.explore_orchestrator is None:
        raise RuntimeError("ExploreOrchestrator is required — check bootstrap wiring")

    orchestrator = services.explore_orchestrator

    create_explore_api_routes(app, rt, orchestrator=orchestrator)
    create_explore_ui_routes(app, rt, orchestrator=orchestrator)
    create_learning_loop_routes(app, rt, orchestrator=orchestrator)


__all__ = ["create_explore_routes"]
