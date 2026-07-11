"""
Explore Routes — Orchestrator-Driven Registration
====================================================

Wires the /explore discovery surface and learning loop engagement
pages using the ExploreOrchestrator.

Discovery (explore_ui.py):
- GET  /explore              — Discovery index with search + bento card grid
- GET  /explore/content      — HTMX fragment: card grid with search panel
- GET  /api/explore/search   — HTMX fragment: filtered card grid
- GET  /api/explore/graph    — Hub learning universe graph (Vis.js JSON)

Engagement (learning_loop_routes.py):
- GET  /explore/ku/{uid}     — Ku detail page
- GET  /explore/ps/{uid}     — PathStep detail page (learning loop anchor)
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
    create_learning_loop_routes(
        app,
        rt,
        orchestrator=orchestrator,
        ps_engagement_service=services.ps_engagement,
        user_service=services.user,
        form_submission_service=services.form_submissions,
        # None on CORE tier — the "Related concepts" sections are simply absent
        vector_search_service=services.vector_search_service,
        # None on CORE tier — "Related to your next step" is simply absent
        zpd_service=services.zpd_service,
    )


__all__ = ["create_explore_routes"]
