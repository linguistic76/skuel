"""Curriculum Legacy Redirects
==============================

Redirects for retired curriculum hub routes.

Routes:
- GET /curriculum — 301 redirect to /profile (hub shelved)
- GET /lessons — 301 redirect to /explore (merged into PathStep, then Explore)
- GET /path-steps — 301 redirect to /explore (merged)
"""

from typing import Any

from starlette.responses import RedirectResponse

from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator


def create_curriculum_hub_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Any,
) -> None:
    """Register legacy curriculum redirects."""

    @rt("/curriculum")
    async def curriculum_landing(request: Request) -> RedirectResponse:
        """Curriculum hub shelved — redirect to Profile."""
        return RedirectResponse(url="/profile", status_code=301)

    @rt("/lessons")
    async def lessons_redirect(request: Request) -> RedirectResponse:
        """Lesson merged into PathStep, now in Explore."""
        return RedirectResponse(url="/explore", status_code=301)

    @rt("/path-steps")
    async def path_steps_browser(request: Request) -> RedirectResponse:
        """PathStep browser merged into Explore."""
        return RedirectResponse(url="/explore", status_code=301)
