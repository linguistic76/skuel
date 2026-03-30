"""Curriculum Hub Routes — Configuration-Driven Registration
============================================================

Wires the /curriculum hub routes: landing redirect + browser sub-pages.

Routes:
- GET /curriculum — 301 redirect to /profile
- GET /lessons — Lesson browser
- GET /path-steps — Learning Steps browser
- GET /learning-paths — Learning Paths browser

Exercises routes are registered separately via exercises_routes.py.
"""

from typing import Any

from adapters.inbound.curriculum_hub_ui import create_curriculum_hub_ui_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.curriculum_hub")


def create_curriculum_hub_routes(app: FastHTMLApp, rt: RouteDecorator, services: Any) -> RouteList:
    """Wire curriculum hub routes."""
    routes = create_curriculum_hub_ui_routes(app, rt, services)
    logger.info(
        "Curriculum hub routes registered (/curriculum, /lessons, /path-steps, /learning-paths)"
    )
    return routes
