"""
Ku UI Routes — Knowledge Index with Bookmarks Sidebar
=====================================================

The /ku page shows a flat listing of all Knowledge Units with:
- Sidebar: Bookmarked Kus + Latest Kus
- Main: Full Ku listing with pin buttons and category badges

KuService is the primary service (not LessonService).
"""

from typing import Any

from fasthtml.common import A as Anchor
from fasthtml.common import Div, Li, P, Span, Ul

from ui.feedback import Badge, BadgeT

from core.models.ku.ku import Ku
from core.utils.logging import get_logger
from ui.patterns.error_banner import render_error_banner
from ui.patterns.pin_button import PinButton
from ui.patterns.sidebar import SidebarItem, SidebarLink, SidebarPage

logger = get_logger("skuel.routes.ku.ui")


def _render_ku_row(ku: Ku, pinned_uids: set[str]) -> Any:
    """Render a single Ku as a list row with pin button and badges."""
    is_pinned = ku.uid in pinned_uids

    # Truncate description
    desc_text = None
    if ku.description:
        desc_text = ku.description[:200] + "..." if len(ku.description) > 200 else ku.description

    # Category badges
    badges: list[Any] = []
    if ku.ku_category:
        badges.append(Badge(ku.ku_category, variant=BadgeT.neutral))
    if ku.sel_category:
        sel_label = ku.sel_category if isinstance(ku.sel_category, str) else ku.sel_category.value
        badges.append(Badge(sel_label.replace("_", " ").title(), variant=BadgeT.primary))

    return Li(
        Div(
            Div(
                Div(
                    Anchor(
                        ku.title,
                        href=f"/ku/detail?uid={ku.uid}",
                        cls="font-medium text-foreground hover:text-primary transition-colors",
                    ),
                    *badges,
                    cls="flex items-center gap-2 flex-wrap",
                ),
                P(desc_text, cls="text-sm text-muted-foreground mt-1") if desc_text else None,
                cls="flex-1 min-w-0",
            ),
            PinButton(entity_uid=ku.uid, is_pinned=is_pinned),
            cls="flex items-center gap-3",
        ),
        cls="py-3 border-b border-border last:border-0",
    )


def _build_sidebar_items(
    pinned_kus: list[Ku],
    latest_kus: list[Ku],
) -> tuple[list[SidebarItem], list[Any]]:
    """Build sidebar items: Bookmarks section + Latest section."""
    items: list[SidebarItem] = [
        SidebarItem(label="All Knowledge", href="/ku", slug="all"),
    ]

    # Extra sidebar sections for bookmarks and latest
    from fasthtml.common import H4

    extra_sections: list[Any] = []

    # Bookmarks section
    if pinned_kus:
        bookmark_links = [
            SidebarLink(text=ku.title, href=f"/ku/detail?uid={ku.uid}") for ku in pinned_kus[:10]
        ]
        extra_sections.append(
            Li(
                H4(
                    "Bookmarked",
                    cls="text-xs font-semibold uppercase tracking-wider text-muted-foreground px-3 py-2",
                ),
                Ul(*bookmark_links, cls="list-none p-0"),
                cls="mt-1",
            )
        )
    else:
        extra_sections.append(
            Li(
                H4(
                    "Bookmarked",
                    cls="text-xs font-semibold uppercase tracking-wider text-muted-foreground px-3 py-2",
                ),
                P("No bookmarks yet", cls="text-xs text-muted-foreground/60 italic px-3 py-1"),
                cls="mt-1",
            )
        )

    # Latest section
    if latest_kus:
        latest_links = [
            SidebarLink(text=ku.title, href=f"/ku/detail?uid={ku.uid}") for ku in latest_kus[:5]
        ]
        extra_sections.append(
            Li(
                Li(cls="border-t border-border my-2"),
                H4(
                    "Latest",
                    cls="text-xs font-semibold uppercase tracking-wider text-muted-foreground px-3 py-2",
                ),
                Ul(*latest_links, cls="list-none p-0"),
            )
        )

    return items, extra_sections


def create_ku_ui_routes(_app, rt, ku_service, user_relationship_service=None):
    """
    Create /ku UI routes using KuService.

    Args:
        ku_service: The actual KuService (services.ku), NOT LessonService.
        user_relationship_service: UserRelationshipService for pinned Kus.
    """

    logger.info("Ku UI routes registered (/ku index)")

    @rt("/ku")
    async def ku_index(request) -> Any:
        """Main Ku index — flat listing with bookmarks/latest sidebar."""
        from adapters.inbound.auth import is_authenticated, require_authenticated_user
        from ui.patterns.page_header import PageHeader

        # Fetch all Kus
        kus: list[Ku] = []
        ku_load_error = False
        if ku_service and getattr(ku_service, "core", None):
            result = await ku_service.core.list(limit=500)
            if result.is_error:
                logger.error(f"Failed to load knowledge units: {result.error}")
                ku_load_error = True
            elif result.value:
                entities, _count = result.value
                kus = entities

        # Fetch pinned entity UIDs for the current user
        pinned_uids: set[str] = set()
        pinned_kus: list[Ku] = []
        if user_relationship_service and is_authenticated(request):
            user_uid = require_authenticated_user(request)
            pins_result = await user_relationship_service.get_pinned_entities(user_uid)
            if pins_result.is_error:
                logger.warning(f"Failed to load bookmarks: {pins_result.error}")
            elif pins_result.value:
                pinned_uids = set(pins_result.value)

        # Build pinned Kus list (matching pinned UIDs to Ku objects)
        ku_by_uid = {ku.uid: ku for ku in kus}
        pinned_kus = [ku_by_uid[uid] for uid in pinned_uids if uid in ku_by_uid]

        # Latest Kus (first 5 from the list — already sorted by created_at desc from service)
        latest_kus = kus[:5]

        # Build sidebar
        sidebar_items, extra_sections = _build_sidebar_items(pinned_kus, latest_kus)

        # Build main content — flat listing
        if ku_load_error:
            ku_list = render_error_banner("Unable to load knowledge units. Please try again later.")
        elif kus:
            ku_list = Ul(
                *[_render_ku_row(ku, pinned_uids) for ku in kus],
                cls="list-none p-0",
            )
        else:
            ku_list = Div(
                P(
                    "No knowledge units yet. Ingest Ku YAML files to populate this page.",
                    cls="text-muted-foreground italic py-8 text-center",
                ),
            )

        content = Div(
            PageHeader(
                "Knowledge",
                subtitle="Atomic knowledge units",
            ),
            ku_list,
        )

        return await SidebarPage(
            content=content,
            items=sidebar_items,
            active="all",
            title="Knowledge",
            subtitle="Bookmarks & Latest",
            storage_key="ku-sidebar",
            extra_sidebar_sections=extra_sections,
            page_title="Knowledge",
            request=request,
            active_page="knowledge",
            title_href="/ku",
        )

    return []  # Routes registered via @rt() decorators


__all__ = ["create_ku_ui_routes"]
