"""
KU Reading UI Routes - Phase A
===============================

User-facing routes for reading Knowledge Units with:
- Markdown content rendering with table of contents
- Breadcrumbs from MOC context
- Mark as read / bookmark actions
- Next/prev navigation via MOC ORGANIZES order
- KU metadata display (domain, complexity, tags)
- Lateral relationships visualization

Routes:
- GET /ku/{uid} - KU detail page with reading interface
"""

from typing import Any

from fasthtml.common import H3, A, Button, Div, NotStr, P, Request, Small, Span

from adapters.inbound.auth import require_authenticated_user
from core.utils.logging import get_logger
from core.utils.markdown_renderer import render_markdown_with_toc
from ui.daisy_components import Card, CardBody
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.breadcrumbs import Breadcrumbs
from ui.patterns.relationships import EntityRelationshipsSection

logger = get_logger("skuel.routes.ku.reading.ui")


def _metadata_badge(label: str, value: str, color: str = "badge-ghost") -> Span:
    """Render a metadata badge."""
    return Span(
        Span(label, cls="font-medium mr-1"),
        value,
        cls=f"badge {color} gap-1",
    )


def _nav_button(ku: dict | None, direction: str) -> Any:
    """Render a navigation button (previous or next)."""
    if not ku:
        label = f"{'Previous' if direction == 'prev' else 'Next'}"
        return Button(
            f"{'←' if direction == 'prev' else ''} {label} {'→' if direction == 'next' else ''}",
            cls="btn btn-outline btn-disabled",
            disabled=True,
        )

    label = ku.get("title", "...")
    if len(label) > 40:
        label = label[:37] + "..."

    if direction == "prev":
        return A(
            Div(
                Small("Previous", cls="text-xs text-base-content/50"),
                Div(f"← {label}", cls="text-sm"),
                cls="text-left",
            ),
            href=f"/ku/{ku.get('uid')}",
            cls="btn btn-outline",
        )
    return A(
        Div(
            Small("Next", cls="text-xs text-base-content/50"),
            Div(f"{label} →", cls="text-sm"),
            cls="text-right",
        ),
        href=f"/ku/{ku.get('uid')}",
        cls="btn btn-outline",
    )


def create_ku_reading_ui_routes(
    app: Any,
    rt: Any,
    ku_service: Any,
    ku_interaction_service: Any,
) -> list[Any]:
    """
    Create KU reading UI routes.

    Args:
        app: FastHTML app instance
        rt: FastHTML route decorator
        ku_service: KU service facade (with organization methods for breadcrumbs/navigation)
        ku_interaction_service: Interaction tracking service

    Returns:
        List of registered route functions
    """

    @rt("/ku/{uid}")
    async def ku_detail_page(request: Request, uid: str) -> Any:
        """
        KU detail page with full reading interface.

        Displays:
        - Breadcrumbs (from MOC if available)
        - Page header with mark-as-read and bookmark actions
        - KU metadata (domain, complexity, tags)
        - Markdown content with table of contents
        - Next/prev navigation (via MOC ORGANIZES order)
        - Lateral relationships visualization
        """
        user_uid = require_authenticated_user(request)

        # Get KU with content (content lives on :Content node)
        ku_result = await ku_service.get_with_content(uid)
        if ku_result.is_error:
            return await BasePage(
                content=Div(
                    Card(
                        CardBody(
                            H3("Knowledge Unit Not Found", cls="text-lg font-bold"),
                            P(f"No KU with identifier: {uid}", cls="text-base-content/70 mt-2"),
                            A("← Back to Knowledge", href="/sel", cls="btn btn-ghost btn-sm mt-4"),
                        ),
                    ),
                    cls="max-w-4xl mx-auto p-8",
                ),
                title="KU Not Found",
                request=request,
            )

        ku, content_body = ku_result.value

        # Record view
        await ku_interaction_service.record_view(user_uid, uid)

        # Get learning state (includes marked-as-read and bookmark status)
        state_result = await ku_interaction_service.get_learning_state(user_uid, uid)
        is_marked_read = state_result.value.is_marked_as_read if state_result.is_ok else False
        is_bookmarked = state_result.value.is_bookmarked if state_result.is_ok else False
        view_count = state_result.value.view_count if state_result.is_ok else 0

        # Get organization context for breadcrumbs + navigation
        organizers_result = await ku_service.find_organizers(uid)
        mocs = organizers_result.value if organizers_result.is_ok else []

        # Build navigation from siblings under parent organizer
        prev_ku = None
        next_ku = None
        if mocs:
            moc = mocs[0]
            moc_uid = moc.get("uid")
            moc_view_result = await ku_service.get_organization_view(moc_uid, max_depth=1)
            if moc_view_result.is_ok:
                children = moc_view_result.value.children
                current_idx = None
                for idx, child in enumerate(children):
                    if child.uid == uid:
                        current_idx = idx
                        break
                if current_idx is not None:
                    if current_idx > 0:
                        prev_child = children[current_idx - 1]
                        prev_ku = {"uid": prev_child.uid, "title": prev_child.title}
                    if current_idx < len(children) - 1:
                        next_child = children[current_idx + 1]
                        next_ku = {"uid": next_child.uid, "title": next_child.title}

        # Build breadcrumbs
        breadcrumb_path = [
            {"uid": "knowledge", "title": "Knowledge", "url": "/sel"},
        ]
        if mocs:
            moc = mocs[0]
            breadcrumb_path.append(
                {
                    "uid": moc.get("uid"),
                    "title": moc.get("title", "MOC"),
                    "url": f"/moc/{moc.get('uid')}",
                }
            )
        breadcrumb_path.append({"uid": uid, "title": ku.title, "url": ""})

        # Render markdown content with TOC
        content_html, toc_html = render_markdown_with_toc(content_body or "")
        has_toc = bool(toc_html and toc_html.strip())

        # Action buttons
        mark_read_btn = Button(
            "Marked as Read" if is_marked_read else "Mark as Read",
            cls="btn btn-sm btn-outline btn-success"
            if is_marked_read
            else "btn btn-sm btn-primary",
            hx_post=f"/api/ku/{uid}/mark-read",
            hx_swap="outerHTML",
            hx_target="this",
            disabled=is_marked_read,
        )

        bookmark_btn = Button(
            "Bookmarked" if is_bookmarked else "Bookmark",
            cls="btn btn-sm btn-secondary" if is_bookmarked else "btn btn-sm btn-ghost",
            hx_post=f"/api/ku/{uid}/bookmark",
            hx_swap="outerHTML",
            hx_target="this",
        )

        # Metadata badges
        metadata_items = []
        if ku.domain:
            domain_label = getattr(ku.domain, "value", str(ku.domain))
            metadata_items.append(
                _metadata_badge("Domain:", domain_label, "badge-primary badge-outline")
            )
        if ku.complexity:
            metadata_items.append(_metadata_badge("Complexity:", ku.complexity, "badge-ghost"))
        if view_count > 0:
            metadata_items.append(_metadata_badge("Views:", str(view_count), "badge-ghost"))

        metadata_section = (
            Div(*metadata_items, cls="flex flex-wrap gap-2") if metadata_items else None
        )

        # Tags
        tags_section = None
        if ku.tags:
            tag_badges = [Span(tag, cls="badge badge-outline badge-sm") for tag in ku.tags]
            tags_section = Div(*tag_badges, cls="flex flex-wrap gap-1 mt-3")

        # Reading content (markdown only — TOC is separate)
        reading_content = Div(
            NotStr(content_html or "No content available."),
            cls="prose prose-lg max-w-none",
        )

        # Navigation bar
        nav_section = Div(
            Div(
                _nav_button(prev_ku, "prev"),
                _nav_button(next_ku, "next"),
                cls="flex justify-between",
            ),
            cls="border-t border-base-200 pt-6 mt-8",
        )

        # Build metadata footer (below content, not competing with reading)
        metadata_footer_items = []
        if metadata_section:
            metadata_footer_items.append(metadata_section)
        if tags_section:
            metadata_footer_items.append(tags_section)

        metadata_footer = (
            Div(*metadata_footer_items, cls="border-t border-base-200 pt-6 mt-8")
            if metadata_footer_items
            else Div()
        )

        # Main content column — breadcrumbs, content, actions, metadata, nav
        main_column = Div(
            Breadcrumbs(path=breadcrumb_path, show_home=False),
            reading_content,
            # Actions at the bottom of reading area
            Div(
                mark_read_btn,
                bookmark_btn,
                cls="flex gap-2 border-t border-base-200 pt-6 mt-8",
            ),
            metadata_footer,
            nav_section,
            Div(
                EntityRelationshipsSection(
                    entity_uid=uid,
                    entity_type="ku",
                ),
                cls="mt-8",
            ),
            cls="flex-1 min-w-0 max-w-4xl mx-auto px-6 lg:px-8 py-4 lg:py-6",
        )

        if has_toc:
            # Two-column layout: TOC pinned left, content centered
            toc_sidebar = Div(
                Div(
                    H3("Contents", cls="font-semibold text-sm mb-3"),
                    Div(
                        NotStr(toc_html),
                        cls="prose prose-sm max-w-none toc-nav",
                    ),
                    cls="sticky top-20 p-5 max-h-[calc(100vh-6rem)] overflow-y-auto",
                ),
                cls="hidden lg:block w-56 shrink-0 border-r border-base-200",
            )
            content = Div(toc_sidebar, main_column, cls="flex")
        else:
            content = main_column

        return await BasePage(
            content=content,
            title=ku.title,
            request=request,
            active_page="learning",
            page_type=PageType.CUSTOM,
        )

    logger.info("KU reading UI routes registered: /ku/{uid}")

    return [
        ku_detail_page,
    ]


__all__ = ["create_ku_reading_ui_routes"]
