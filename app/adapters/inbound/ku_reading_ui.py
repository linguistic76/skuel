"""
KU Reading UI Routes - MVP Phase A
===================================

User-facing routes for reading Knowledge Units with:
- Content display (title, description, markdown)
- Breadcrumbs from MOC context
- Mark as read / bookmark actions
- Next/prev navigation via MOC ORGANIZES order

Routes:
- GET /ku/read/{uid} - KU detail page with reading interface
- GET /ku/browse - KU browse page with MOC navigation (future)
"""

from typing import Any

from fasthtml.common import Div, H1, H2, H3, NotStr, P, Request, Span, Button, A
from fasthtml.common import A as Anchor

from core.auth import require_authenticated_user
from core.ui.daisy_components import Card, CardBody
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.breadcrumbs import Breadcrumbs
from ui.patterns.page_header import PageHeader

logger = get_logger("skuel.routes.ku.reading.ui")


def create_ku_reading_ui_routes(
    app: Any,
    rt: Any,
    ku_service: Any,
    moc_service: Any,
    ku_interaction_service: Any,
) -> list[Any]:
    """
    Create KU reading UI routes.

    Args:
        app: FastHTML app instance
        rt: FastHTML route decorator
        ku_service: KU service facade
        moc_service: MOC service for navigation
        ku_interaction_service: Interaction tracking service

    Returns:
        List of registered route functions
    """

    @rt("/ku/read/{uid}")
    async def ku_read_page(request: Request, uid: str) -> Any:
        """
        KU detail page with reading interface.

        Displays:
        - KU title, description, content (markdown)
        - Breadcrumbs (from MOC if available)
        - Mark as read button
        - Bookmark button
        - Next/prev navigation (via MOC order)
        """
        user_uid = require_authenticated_user(request)

        # Get KU
        ku_result = await ku_service.get_ku(uid)
        if ku_result.is_error:
            return BasePage(
                content=Div(
                    P(f"KU not found: {uid}", cls="text-error"),
                    cls="p-8",
                ),
                title="KU Not Found",
                request=request,
            )

        ku = ku_result.value

        # Record view (track interaction)
        await ku_interaction_service.record_view(user_uid, uid)

        # Get learning state
        state_result = await ku_interaction_service.get_learning_state(user_uid, uid)
        is_marked_read = state_result.value.state.value == "marked_as_read" if state_result.is_ok else False

        # Get MOC context for breadcrumbs
        mocs_result = await moc_service.find_mocs_containing(uid)
        mocs = mocs_result.value if mocs_result.is_ok else []

        # Build breadcrumbs
        breadcrumb_items = [("Home", "/"), ("Knowledge", "/sel")]
        if mocs:
            # Use first MOC for breadcrumb
            moc = mocs[0]
            breadcrumb_items.append((moc.get("title", "MOC"), f"/moc/{moc.get('uid')}"))
        breadcrumb_items.append((ku.title, f"/ku/read/{uid}"))

        # Build content
        content = Div(
            # Breadcrumbs
            Breadcrumbs(items=breadcrumb_items),
            # Page Header
            PageHeader(
                title=ku.title,
                description=ku.description or "",
                actions=[
                    Button(
                        "✓ Marked as Read" if is_marked_read else "Mark as Read",
                        cls="btn btn-sm btn-primary" if not is_marked_read else "btn btn-sm btn-outline",
                        hx_post=f"/api/ku/{uid}/mark-read",
                        hx_swap="outerHTML",
                        hx_target="this",
                    ),
                    Button(
                        "⭐ Bookmark",
                        cls="btn btn-sm btn-ghost",
                        hx_post=f"/api/ku/{uid}/bookmark",
                        hx_swap="outerHTML",
                        hx_target="this",
                    ),
                ],
            ),
            # Content Card
            Card(
                CardBody(
                    # Markdown content
                    Div(
                        NotStr(ku.content or "No content available."),
                        cls="prose prose-lg max-w-none",
                    ),
                ),
                cls="mt-6",
            ),
            # Navigation (placeholder - will be enhanced with MOC order)
            Div(
                Div(
                    Button("← Previous", cls="btn btn-outline", disabled=True),
                    Button("Next →", cls="btn btn-outline", disabled=True),
                    cls="flex justify-between mt-8",
                ),
                cls="border-t pt-6 mt-6",
            ),
            cls="max-w-4xl mx-auto p-8",
        )

        return BasePage(
            content=content,
            title=ku.title,
            request=request,
        )

    logger.info("KU reading UI routes registered (1 endpoint)")

    return [
        ku_read_page,
    ]


__all__ = ["create_ku_reading_ui_routes"]
