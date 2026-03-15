"""
Ku UI Routes — SEL-Organized Knowledge Index
=============================================

The /ku page is a simple, single-scroll reference index:
SEL categories as headings, Ku entities listed under each.
No cards, no tabs, no lazy-loading fragments.

KuService is the primary service (not LessonService).
"""

from typing import Any

from fasthtml.common import H2, Div, Li, P, Span, Ul
from fasthtml.common import A as Anchor

from core.models.enums import SELCategory
from core.utils.logging import get_logger
from ui.patterns.sidebar import SidebarItem, SidebarPage

logger = get_logger("skuel.routes.ku.ui")


def _sel_sidebar_items() -> list[SidebarItem]:
    """Build sidebar items from SEL categories — anchor links within the page."""
    items = [
        SidebarItem(label="All", href="/ku", slug="all"),
    ]
    items.extend(
        SidebarItem(
            label=f"{cat.get_icon()} {cat.name.replace('_', ' ').title()}",
            href=f"#sel-{cat.value}",
            slug=cat.value,
        )
        for cat in SELCategory
    )
    return items


def _render_ku_item(ku) -> Any:
    """Render a single Ku as a compact list item."""
    title = getattr(ku, "title", "Untitled")
    description = getattr(ku, "description", None)
    ku_category = getattr(ku, "ku_category", None)
    uid = getattr(ku, "uid", "")

    badge = (
        Span(
            ku_category,
            cls="badge badge-sm badge-outline ml-2",
        )
        if ku_category
        else None
    )

    return Li(
        Div(
            Div(
                Anchor(
                    title,
                    href=f"/lesson/{uid}",
                    cls="font-medium link link-hover",
                ),
                badge,
                cls="flex items-center gap-1",
            )
            if badge
            else Anchor(
                title,
                href=f"/lesson/{uid}",
                cls="font-medium link link-hover",
            ),
            P(description, cls="text-sm text-base-content/60 mt-0.5") if description else None,
            cls="py-2",
        ),
        cls="border-b border-base-200 last:border-0",
    )


def _render_sel_section(category: SELCategory, kus: list) -> Any:
    """Render one SEL category heading + its Ku list."""
    return Div(
        H2(
            Span(category.get_icon(), cls="mr-2"),
            category.name.replace("_", " ").title(),
            cls="text-xl font-bold mb-1",
            id=f"sel-{category.value}",
        ),
        P(category.get_description(), cls="text-sm text-base-content/60 mb-3"),
        Ul(
            *[_render_ku_item(ku) for ku in kus],
            cls="list-none p-0",
        )
        if kus
        else P("No knowledge units yet", cls="text-sm text-base-content/40 italic"),
        cls="mb-8",
    )


def _render_uncategorized_section(kus: list) -> Any:
    """Render Kus that have no sel_category."""
    if not kus:
        return None
    return Div(
        H2(
            "Other",
            cls="text-xl font-bold mb-1",
            id="sel-other",
        ),
        P(
            "Knowledge units not yet assigned to an SEL competency",
            cls="text-sm text-base-content/60 mb-3",
        ),
        Ul(
            *[_render_ku_item(ku) for ku in kus],
            cls="list-none p-0",
        ),
        cls="mb-8",
    )


def create_ku_ui_routes(_app, rt, ku_service):
    """
    Create /ku UI routes using KuService.

    Args:
        ku_service: The actual KuService (services.ku), NOT LessonService.
    """

    logger.info("Ku UI routes registered (/ku index)")

    @rt("/ku")
    async def ku_index(request) -> Any:
        """Main Ku index — single-scroll page organized by SEL category."""
        from ui.patterns.page_header import PageHeader

        # Fetch all Kus in one call
        kus = []
        if ku_service and getattr(ku_service, "core", None):
            result = await ku_service.core.list(limit=500)
            if not result.is_error and result.value:
                entities, _count = result.value
                kus = entities

        # Group by sel_category
        grouped: dict[SELCategory | None, list] = {cat: [] for cat in SELCategory}
        grouped[None] = []
        for ku in kus:
            cat = getattr(ku, "sel_category", None)
            if cat in grouped:
                grouped[cat].append(ku)
            else:
                grouped[None].append(ku)

        # Build sections
        sections = [_render_sel_section(cat, grouped[cat]) for cat in SELCategory]

        uncategorized = _render_uncategorized_section(grouped[None])
        if uncategorized:
            sections.append(uncategorized)

        content = Div(
            PageHeader(
                "Knowledge",
                subtitle="Atomic concepts organized by SEL competency",
            ),
            *sections,
        )

        return await SidebarPage(
            content=content,
            items=_sel_sidebar_items(),
            active="all",
            title="Knowledge",
            subtitle="SEL Competencies",
            storage_key="ku-sidebar",
            page_title="Knowledge",
            request=request,
            active_page="knowledge",
            title_href="/ku",
        )

    return []  # Routes registered via @rt() decorators


__all__ = ["create_ku_ui_routes"]
