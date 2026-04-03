"""
Ku UI Routes — Redirects + Learning State API
===============================================

GET routes redirect to /explore (merged discovery page).
POST mutation endpoints remain here for HTMX learning state actions.

Routes:
- GET  /ku                           — 301 redirect to /explore
- GET  /api/ku/search                — 301 redirect to /api/explore/search
- GET  /ku/{uid}                     — 301 redirect to /explore/ku/{uid}
- POST /api/ku/{uid}/mark-studying   — Mark Ku as studying (IN_PROGRESS)
- POST /api/ku/{uid}/mark-understood — Mark Ku as understood (MASTERED)
"""

import json
from typing import Any

from fasthtml.common import (
    H3,
    Div,
    P,
    Request,
    Span,
)
from starlette.responses import RedirectResponse

from adapters.inbound.auth import require_authenticated_user
from core.models.enums.submissions_enums import ExerciseScope
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonT
from ui.exercises.inline_form import render_inline_exercise_form
from ui.feedback import Badge, BadgeT
from ui.layout import Size

logger = get_logger("skuel.routes.ku.ui")


# =============================================================================
# Shared helpers
# =============================================================================


def _ku_learning_buttons(uid: str, is_studying: bool, is_understood: bool) -> Any:
    """Render progressive learning state buttons for a Ku.

    States: Not started → Studying → Understood (no regression).
    Wrapped in id="ku-learning-actions" for HTMX outerHTML swap.
    """
    if is_understood:
        return Div(
            Badge("Understood", variant=BadgeT.success),
            id="ku-learning-actions",
        )
    if is_studying:
        return Div(
            Badge("Studying", variant=BadgeT.secondary),
            Button(
                "Mark as Understood",
                variant=ButtonT.success,
                size=Size.sm,
                hx_post=f"/api/ku/{uid}/mark-understood",
                hx_swap="outerHTML",
                hx_target="#ku-learning-actions",
            ),
            id="ku-learning-actions",
            cls="flex gap-2 items-center",
        )
    # Not started
    return Div(
        Button(
            "Mark as Studying",
            variant=ButtonT.primary,
            size=Size.sm,
            hx_post=f"/api/ku/{uid}/mark-studying",
            hx_swap="outerHTML",
            hx_target="#ku-learning-actions",
        ),
        Button(
            "Mark as Understood",
            variant=ButtonT.ghost,
            size=Size.sm,
            disabled=True,
        ),
        id="ku-learning-actions",
        cls="flex gap-2 items-center",
    )


def _parse_form_schema(raw: Any) -> list[dict] | None:
    """Parse form_schema from Neo4j (may be JSON string, list, or None)."""
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) and parsed else None
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(raw, list) and raw:
        return raw
    return None


# =============================================================================
# Detail page helpers
# =============================================================================


def _exercises_for_ku_section(exercises: list[dict]) -> Any:
    """Exercises that practice this knowledge — Ku -> Exercise loop entry point."""
    if not exercises:
        return Div()

    rows = []
    for e in exercises:
        form_schema = _parse_form_schema(e.get("form_schema"))

        if form_schema:
            rows.append(
                render_inline_exercise_form(
                    exercise_uid=e.get("uid", ""),
                    form_schema=form_schema,
                    exercise_title=e.get("title"),
                )
            )
        else:
            scope = e.get("scope", "personal")
            scope_variant = BadgeT.secondary if scope == ExerciseScope.ASSIGNED else BadgeT.ghost
            due = e.get("due_date")
            due_span = Span(f" · due {due}", cls="text-xs text-muted-foreground") if due else None
            row_parts: list[Any] = [
                Span(e.get("title", "Untitled Exercise"), cls="text-sm font-medium"),
                Badge(scope.title(), variant=scope_variant, size=Size.sm, cls="ml-2"),
            ]
            if due_span:
                row_parts.append(due_span)
            rows.append(Div(*row_parts, cls="flex items-center py-1.5"))

    return Div(
        H3("Practice This Knowledge", cls="text-base font-semibold mb-3"),
        P(
            "These exercises develop understanding of this knowledge unit.",
            cls="text-sm text-muted-foreground mb-3",
        ),
        Div(*rows, cls="space-y-2"),
        cls="border-t border-border pt-6 mt-8",
    )


# =============================================================================
# Route factory
# =============================================================================


def create_ku_ui_routes(
    _app: Any,
    rt: Any,
    ku_service: Any,
    user_relationship_service: Any = None,
    exercises_service: Any = None,
) -> list[Any]:
    """Create /ku UI + API routes.

    GET routes redirect to /explore (merged discovery page).
    POST mutation endpoints remain here for HTMX learning state actions.
    """

    # -----------------------------------------------------------------
    # GET /ku — 301 redirect to /explore
    # -----------------------------------------------------------------

    @rt("/ku")
    async def ku_index(request: Request) -> RedirectResponse:
        """Knowledge index merged into /explore."""
        return RedirectResponse(url="/explore", status_code=301)

    # -----------------------------------------------------------------
    # GET /api/ku/search — 301 redirect to /api/explore/search
    # -----------------------------------------------------------------

    @rt("/api/ku/search")
    async def ku_search(request: Request) -> RedirectResponse:
        """Ku search merged into /api/explore/search."""
        qs = str(request.query_params)
        url = f"/api/explore/search?{qs}" if qs else "/api/explore/search"
        return RedirectResponse(url=url, status_code=301)

    # -----------------------------------------------------------------
    # GET /ku/{uid} — 301 redirect to /explore/ku/{uid}
    # -----------------------------------------------------------------

    @rt("/ku/{uid}")
    async def ku_detail_page(request: Request, uid: str) -> RedirectResponse:
        """Ku detail merged into /explore/ku/{uid}."""
        return RedirectResponse(url=f"/explore/ku/{uid}", status_code=301)

    # -----------------------------------------------------------------
    # POST /api/ku/{uid}/mark-studying — Mark Ku as studying
    # -----------------------------------------------------------------

    @rt("/api/ku/{uid}/mark-studying", methods=["POST"])
    async def mark_ku_as_studying(request: Request, uid: str) -> Any:
        """Mark Ku as studying. Returns updated learning buttons for HTMX swap.

        Enforces a limit of 5 simultaneously studying Kus.
        """
        user_uid = require_authenticated_user(request)

        # Enforce 5-Ku studying limit
        count_result = await ku_service.count_studying_kus(user_uid)
        if not count_result.is_error and (count_result.value or 0) >= 5:
            return _ku_learning_buttons(uid, False, False)

        result = await ku_service.mark_as_studying(user_uid, uid)
        if result.is_error:
            return _ku_learning_buttons(uid, False, False)
        return _ku_learning_buttons(uid, is_studying=True, is_understood=False)

    # -----------------------------------------------------------------
    # POST /api/ku/{uid}/mark-understood — Mark Ku as understood
    # -----------------------------------------------------------------

    @rt("/api/ku/{uid}/mark-understood", methods=["POST"])
    async def mark_ku_as_understood(request: Request, uid: str) -> Any:
        """Mark Ku as understood. Returns updated learning buttons for HTMX swap."""
        user_uid = require_authenticated_user(request)
        result = await ku_service.mark_as_understood(user_uid, uid)
        if result.is_error:
            return _ku_learning_buttons(uid, True, False)
        return _ku_learning_buttons(uid, is_studying=True, is_understood=True)

    logger.info(
        "Ku UI routes registered: /ku (→/explore), /ku/{uid} (→/explore/ku/{uid}), "
        "/api/ku/{uid}/mark-studying, /api/ku/{uid}/mark-understood"
    )

    return []  # Routes registered via @rt() decorators


__all__ = ["create_ku_ui_routes"]
