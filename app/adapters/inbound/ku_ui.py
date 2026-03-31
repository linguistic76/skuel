"""
Ku UI Routes — Knowledge Index + Detail Page + API
====================================================

All Ku routes in one file, backed by KuService only (no PsService dependency).

Routes:
- GET  /ku           — Knowledge index with bookmarks sidebar
- GET  /ku/{uid}     — Ku detail page with content, metadata, exercises
- POST /api/ku/{uid}/mark-studying   — Mark Ku as studying (IN_PROGRESS)
- POST /api/ku/{uid}/mark-understood — Mark Ku as understood (MASTERED)
"""

import json
from typing import Any

from fasthtml.common import H3, Div, Li, NotStr, P, Request, Span, Ul
from fasthtml.common import A as Anchor

from adapters.inbound.auth import is_authenticated, require_authenticated_user
from core.models.enums.submissions_enums import ExerciseScope
from core.models.ku.ku import Ku
from core.utils.logging import get_logger
from core.utils.markdown_renderer import render_markdown_with_toc
from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card, CardBody
from ui.exercises.inline_form import render_inline_exercise_form
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.breadcrumbs import Breadcrumbs
from ui.patterns.error_banner import render_error_banner
from ui.patterns.metadata_badge import metadata_badge
from ui.patterns.pin_button import PinButton
from ui.patterns.relationships import EntityRelationshipsSection
from ui.patterns.sidebar import SidebarItem, SidebarLink, SidebarPage

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
# Index page helpers
# =============================================================================


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
                        href=f"/ku/{ku.uid}",
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
    studying_kus: list[Ku] | None = None,
    understood_kus: list[Ku] | None = None,
) -> tuple[list[SidebarItem], list[Any]]:
    """Build sidebar items: Studying, Understood, Bookmarks, Latest sections."""
    from fasthtml.common import H4

    items: list[SidebarItem] = [
        SidebarItem(label="All Knowledge", href="/ku", slug="all"),
    ]

    extra_sections: list[Any] = []
    section_header_cls = (
        "text-xs font-semibold uppercase tracking-wider text-muted-foreground px-3 py-2"
    )

    # Studying section
    if studying_kus:
        studying_links = [
            SidebarLink(text=ku.title, href=f"/ku/{ku.uid}") for ku in studying_kus[:10]
        ]
        extra_sections.append(
            Li(
                H4("Studying", cls=section_header_cls),
                Ul(*studying_links, cls="list-none p-0"),
                cls="mt-1",
            )
        )

    # Understood section
    if understood_kus:
        understood_links = [
            SidebarLink(text=ku.title, href=f"/ku/{ku.uid}") for ku in understood_kus[:10]
        ]
        extra_sections.append(
            Li(
                Li(cls="border-t border-border my-2") if studying_kus else Span(),
                H4("Understood", cls=section_header_cls),
                Ul(*understood_links, cls="list-none p-0"),
            )
        )

    # Bookmarks section
    if pinned_kus:
        bookmark_links = [
            SidebarLink(text=ku.title, href=f"/ku/{ku.uid}") for ku in pinned_kus[:10]
        ]
        extra_sections.append(
            Li(
                Li(cls="border-t border-border my-2") if studying_kus or understood_kus else Span(),
                H4("Bookmarked", cls=section_header_cls),
                Ul(*bookmark_links, cls="list-none p-0"),
                cls="mt-1",
            )
        )

    # Latest section
    if latest_kus:
        latest_links = [SidebarLink(text=ku.title, href=f"/ku/{ku.uid}") for ku in latest_kus[:5]]
        extra_sections.append(
            Li(
                Li(cls="border-t border-border my-2"),
                H4("Latest", cls=section_header_cls),
                Ul(*latest_links, cls="list-none p-0"),
            )
        )

    return items, extra_sections


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
    """
    Create all /ku UI + API routes using KuService.

    Args:
        ku_service: KuService (services.ku) — NOT PsService.
        user_relationship_service: UserRelationshipService for pinned Kus.
        exercises_service: Exercise service (for REQUIRES_KNOWLEDGE reverse lookup).
    """

    # -----------------------------------------------------------------
    # GET /ku — Knowledge index
    # -----------------------------------------------------------------

    @rt("/ku")
    async def ku_index(request: Request) -> Any:
        """Main Ku index — flat listing with bookmarks/latest sidebar."""
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
                kus = result.value

        # Per-user data: bookmarks + learning states
        pinned_uids: set[str] = set()
        pinned_kus: list[Ku] = []
        studying_kus: list[Ku] = []
        understood_kus: list[Ku] = []
        ku_by_uid = {ku.uid: ku for ku in kus}

        if is_authenticated(request):
            user_uid = require_authenticated_user(request)

            # Bookmarks
            if user_relationship_service:
                pins_result = await user_relationship_service.get_pinned_entities(user_uid)
                if pins_result.is_error:
                    logger.warning(f"Failed to load bookmarks: {pins_result.error}")
                elif pins_result.value:
                    pinned_uids = set(pins_result.value)

            # Learning states (Studying / Understood sidebar sections)
            if ku_service:
                states_result = await ku_service.get_user_learning_states(user_uid)
                if states_result.is_ok and states_result.value:
                    for rec in states_result.value:
                        ku_obj = ku_by_uid.get(rec.get("uid", ""))
                        if not ku_obj:
                            continue
                        if rec.get("is_understood"):
                            understood_kus.append(ku_obj)
                        elif rec.get("is_studying"):
                            studying_kus.append(ku_obj)

        pinned_kus = [ku_by_uid[uid] for uid in pinned_uids if uid in ku_by_uid]

        # Latest Kus (first 5 from the list)
        latest_kus = kus[:5]

        # Build sidebar
        sidebar_items, extra_sections = _build_sidebar_items(
            pinned_kus, latest_kus, studying_kus, understood_kus
        )

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

    # -----------------------------------------------------------------
    # GET /ku/{uid} — Ku detail page
    # -----------------------------------------------------------------

    @rt("/ku/{uid}")
    async def ku_detail_page(request: Request, uid: str) -> Any:
        """Ku detail page — renders atomic Ku entities from KuService."""
        user_uid = require_authenticated_user(request)

        # Fetch atomic Ku
        ku_result = await ku_service.get_ku(uid) if ku_service else None

        if not ku_result or ku_result.is_error or not ku_result.value:
            return await BasePage(
                content=Div(
                    Card(
                        CardBody(
                            H3("Knowledge Unit Not Found", cls="text-lg font-bold"),
                            P(f"No KU with identifier: {uid}", cls="text-muted-foreground mt-2"),
                            ButtonLink(
                                "← Back to Knowledge",
                                href="/ku",
                                variant=ButtonT.ghost,
                                size=Size.sm,
                                cls="mt-4",
                            ),
                        ),
                    ),
                    cls="max-w-4xl mx-auto p-8",
                ),
                title="KU Not Found",
                request=request,
            )

        ku = ku_result.value
        content_body = ku.description or ""

        # Get learning state (Studying / Understood)
        learning_state = {"is_studying": False, "is_understood": False}
        state_result = await ku_service.get_ku_learning_state(user_uid, uid)
        if state_result.is_ok:
            learning_state = state_result.value

        # Check bookmark state
        is_pinned = False
        if user_relationship_service:
            pins_result = await user_relationship_service.get_pinned_entities(user_uid)
            if pins_result.is_ok and pins_result.value:
                is_pinned = uid in set(pins_result.value)

        # Render markdown content with TOC
        content_html, toc_html = render_markdown_with_toc(content_body)
        has_toc = bool(toc_html and toc_html.strip())

        # Metadata badges
        metadata_items = []
        if getattr(ku, "domain", None):
            domain_label = getattr(ku.domain, "value", str(ku.domain))
            metadata_items.append(metadata_badge("Domain:", domain_label, BadgeT.primary))
        if getattr(ku, "namespace", None):
            metadata_items.append(metadata_badge("Namespace:", ku.namespace))
        if getattr(ku, "ku_category", None):
            metadata_items.append(metadata_badge("Category:", ku.ku_category))

        metadata_section = (
            Div(*metadata_items, cls="flex flex-wrap gap-2") if metadata_items else None
        )

        # Tags
        tags_section = None
        if getattr(ku, "tags", None):
            tag_badges = [Badge(tag, variant=BadgeT.outline, size=Size.sm) for tag in ku.tags]
            tags_section = Div(*tag_badges, cls="flex flex-wrap gap-1 mt-3")

        # Exercises
        exercises_for_ku: list[dict] = []
        if exercises_service:
            exercises_result = await exercises_service.get_exercises_for_curriculum(uid)
            exercises_for_ku = exercises_result.value if exercises_result.is_ok else []

        # Breadcrumbs
        breadcrumb_path = [
            {"uid": "knowledge", "title": "Knowledge", "url": "/ku"},
            {"uid": uid, "title": ku.title, "url": ""},
        ]

        reading_content = Div(
            NotStr(content_html or "No content available."),
            cls="prose prose-lg max-w-none",
        )

        # Action buttons — progressive learning state
        learning_buttons = _ku_learning_buttons(
            uid, learning_state["is_studying"], learning_state["is_understood"]
        )

        # Metadata footer
        metadata_footer_items = []
        if metadata_section:
            metadata_footer_items.append(metadata_section)
        if tags_section:
            metadata_footer_items.append(tags_section)

        metadata_footer = (
            Div(*metadata_footer_items, cls="border-t border-border pt-6 mt-8")
            if metadata_footer_items
            else Div()
        )

        main_column = Div(
            Breadcrumbs(path=breadcrumb_path, show_home=False),
            reading_content,
            # Actions below content
            Div(
                learning_buttons,
                PinButton(entity_uid=uid, is_pinned=is_pinned),
                cls="flex gap-2 items-center border-t border-border pt-6 mt-8",
            ),
            metadata_footer,
            _exercises_for_ku_section(exercises_for_ku),
            Div(
                EntityRelationshipsSection(entity_uid=uid, entity_type="ku"),
                cls="mt-8",
            ),
            cls="flex-1 min-w-0 max-w-4xl mx-auto px-6 lg:px-8 py-4 lg:py-6",
        )

        if has_toc:
            toc_sidebar = Div(
                Div(
                    H3("Contents", cls="font-semibold text-sm mb-3"),
                    Div(NotStr(toc_html), cls="prose prose-sm max-w-none toc-nav"),
                    cls="sticky top-20 p-5 max-h-[calc(100vh-6rem)] overflow-y-auto",
                ),
                cls="hidden lg:block w-56 shrink-0 border-r border-border",
            )
            content = Div(toc_sidebar, main_column, cls="flex")
        else:
            content = main_column

        return await BasePage(
            content=content,
            title=ku.title,
            request=request,
            active_page="knowledge",
            page_type=PageType.CUSTOM,
        )

    # -----------------------------------------------------------------
    # POST /api/ku/{uid}/mark-studying — Mark Ku as studying
    # -----------------------------------------------------------------

    @rt("/api/ku/{uid}/mark-studying", methods=["POST"])
    async def mark_ku_as_studying(request: Request, uid: str) -> Any:
        """Mark Ku as studying. Returns updated learning buttons for HTMX swap."""
        user_uid = require_authenticated_user(request)
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
        "Ku UI routes registered: /ku, /ku/{uid}, "
        "/api/ku/{uid}/mark-studying, /api/ku/{uid}/mark-understood"
    )

    return []  # Routes registered via @rt() decorators


__all__ = ["create_ku_ui_routes"]
