"""
Ku UI Routes — Knowledge Index + Detail Page + API
====================================================

All Ku routes in one file, backed by KuService only (no PsService dependency).

Routes:
- GET  /ku                           — Knowledge index with search panel + bookmarks/available sections
- GET  /api/ku/search                — HTMX fragment: filtered Ku list
- GET  /ku/{uid}                     — Ku detail page with content, metadata, exercises
- POST /api/ku/{uid}/mark-studying   — Mark Ku as studying (IN_PROGRESS)
- POST /api/ku/{uid}/mark-understood — Mark Ku as understood (MASTERED)
"""

import json
from typing import Any

from fasthtml.common import Form, H3, H4, Input, Option, Select
from fasthtml.common import Div, Li, NotStr, P, Request, Span, Ul
from fasthtml.common import A as Anchor

from adapters.inbound.auth import get_current_user, is_authenticated, require_authenticated_user
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
from ui.patterns.breadcrumbs import Breadcrumbs
from ui.patterns.error_banner import render_error_banner
from ui.patterns.metadata_badge import metadata_badge
from ui.patterns.pin_button import PinButton
from ui.patterns.relationships import EntityRelationshipsSection
from ui.patterns.page_header import PageHeader
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


def _filter_kus(
    kus: list[Ku],
    q: str,
    namespace: str,
    ku_type: str,
    tag: str,
    sort: str,
) -> list[Ku]:
    """Filter and sort a Ku list by search params."""
    results = kus

    if namespace:
        results = [k for k in results if getattr(k, "namespace", None) == namespace]

    if ku_type:
        results = [k for k in results if getattr(k, "ku_category", None) == ku_type]

    if tag:
        tag_lower = tag.lower()
        results = [k for k in results if any(t.lower() == tag_lower for t in (k.tags or ()))]

    if q:
        q_lower = q.lower()
        results = [
            k
            for k in results
            if q_lower in (k.title or "").lower()
            or q_lower in (k.description or "").lower()
            or any(q_lower in t.lower() for t in (k.tags or ()))
        ]

    if sort == "created_at":
        results = sorted(results, key=lambda k: getattr(k, "created_at", None) or "", reverse=True)
    else:
        results = sorted(results, key=lambda k: (k.title or "").lower())

    return results


def _render_ku_search_panel(
    all_tags: list[str],
    namespaces: list[str],
    categories: list[str],
    suggested_kus: list[Ku],
) -> Any:
    """Clean search + filter panel — search box, type/namespace/sort dropdowns, tag chips.

    Uses HTMX to stream filtered results into #ku-list.
    Alpine.js tracks query state to show/hide the "for you" suggestions row.
    """
    # Dropdown options
    type_options = [Option("All Types", value="")]
    for cat in sorted(set(categories)):
        type_options.append(Option(cat.replace("_", " ").title(), value=cat))

    ns_options = [Option("All Namespaces", value="")]
    for ns in sorted(set(namespaces)):
        ns_options.append(Option(ns.replace("_", " ").title(), value=ns))

    sort_options = [
        Option("Title A–Z", value="title"),
        Option("Newest First", value="created_at"),
    ]

    # Tag chips
    tag_chips = [
        Span(
            f"#{tag}",
            cls="cursor-pointer text-xs px-2 py-0.5 rounded-full border border-border "
            "text-muted-foreground hover:border-foreground hover:text-foreground "
            "transition-colors select-none",
            x_on_click=f"setTag('{tag}')",
        )
        for tag in all_tags[:24]
    ]

    # "For you" suggestion chips (studying + bookmarked)
    suggestion_chips: list[Any] = [
        Anchor(
            ku.title,
            href=f"/ku/{ku.uid}",
            cls="text-xs px-2.5 py-1 rounded-full bg-muted text-muted-foreground "
            "hover:bg-primary/10 hover:text-primary transition-colors whitespace-nowrap",
        )
        for ku in suggested_kus[:8]
    ]

    suggestions_row = (
        Div(
            Span("For you", cls="text-xs text-muted-foreground shrink-0 pt-0.5"),
            Div(*suggestion_chips, cls="flex flex-wrap gap-1.5"),
            cls="flex items-start gap-3 pt-3 border-t border-border",
            x_show="!query",
        )
        if suggestion_chips
        else None
    )

    dropdown_cls = (
        "text-sm border border-border rounded-md px-2 py-1.5 bg-background "
        "text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer"
    )

    return Div(
        Form(
            # Row 1: search input
            Div(
                Span(
                    NotStr(
                        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
                        'viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
                        'class="text-muted-foreground shrink-0">'
                        '<circle cx="11" cy="11" r="8"/>'
                        '<path d="m21 21-4.35-4.35"/>'
                        "</svg>"
                    ),
                    cls="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none",
                ),
                Input(
                    name="q",
                    type="search",
                    placeholder="Search knowledge units...",
                    autocomplete="off",
                    cls="w-full pl-9 pr-4 py-2 text-sm border border-border rounded-lg "
                    "bg-background focus:outline-none focus:ring-1 focus:ring-primary "
                    "focus:border-primary",
                    x_model="query",
                    x_ref="searchInput",
                    hx_get="/api/ku/search",
                    hx_target="#ku-list",
                    hx_trigger="input delay:250ms",
                    hx_include="closest form",
                ),
                cls="relative",
            ),
            # Row 2: dropdowns
            Div(
                Select(
                    *type_options,
                    name="ku_type",
                    cls=dropdown_cls,
                    hx_get="/api/ku/search",
                    hx_target="#ku-list",
                    hx_trigger="change",
                    hx_include="closest form",
                ),
                Select(
                    *ns_options,
                    name="namespace",
                    cls=dropdown_cls,
                    hx_get="/api/ku/search",
                    hx_target="#ku-list",
                    hx_trigger="change",
                    hx_include="closest form",
                ),
                Select(
                    *sort_options,
                    name="sort",
                    cls=dropdown_cls,
                    hx_get="/api/ku/search",
                    hx_target="#ku-list",
                    hx_trigger="change",
                    hx_include="closest form",
                ),
                cls="flex flex-wrap gap-2",
            ),
            # Row 3: tags
            Div(*tag_chips, cls="flex flex-wrap gap-1.5") if tag_chips else None,
            # Hidden input for active tag (set by Alpine.js)
            Input(name="tag", type="hidden", x_bind_value="activeTag"),
            cls="flex flex-col gap-3",
        ),
        # Row 4: for-you suggestions
        suggestions_row,
        cls="p-4 mb-5 border border-border rounded-xl bg-background flex flex-col gap-3",
        x_data="kuSearch()",
        x_init="init()",
    )


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




def _render_ku_sections(
    pinned_kus: list[Ku],
    available_kus: list[Ku],
    pinned_uids: set[str],
) -> Any:
    """Render Ku list split into Bookmarked + Available sections."""
    rows: list[Any] = []

    if pinned_kus:
        rows.append(H4("Bookmarked", cls="text-sm font-semibold text-foreground mt-2 mb-2"))
        rows.append(
            Ul(*[_render_ku_row(ku, pinned_uids) for ku in pinned_kus], cls="list-none p-0")
        )

    if available_kus:
        rows.append(
            H4(
                "Available",
                cls=f"text-sm font-semibold text-foreground {'mt-6' if pinned_kus else 'mt-2'} mb-2",
            )
        )
        rows.append(
            Ul(*[_render_ku_row(ku, pinned_uids) for ku in available_kus], cls="list-none p-0")
        )

    if not rows:
        return Div(
            P(
                "No knowledge units yet. Ingest Ku YAML files to populate this page.",
                cls="text-muted-foreground italic py-8 text-center",
            ),
        )

    return Div(*rows)


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

    Routes registered:
        GET  /ku                  — Knowledge index with search panel + sidebar
        GET  /api/ku/search       — HTMX fragment: filtered Ku list
        GET  /ku/{uid}            — Ku detail page
        POST /api/ku/{uid}/mark-* — Learning state mutations
    """

    # -----------------------------------------------------------------
    # GET /ku — Knowledge index
    # -----------------------------------------------------------------

    async def _load_ku_index_data(
        request: Request,
    ) -> tuple[list[Ku], bool, set[str], list[Ku], list[Ku], list[Ku]]:
        """Load all Ku index data — Kus, pinned UIDs, and learning states."""
        kus: list[Ku] = []
        ku_load_error = False
        if ku_service and getattr(ku_service, "core", None):
            result = await ku_service.core.list(limit=500)
            if result.is_error:
                logger.error(f"Failed to load knowledge units: {result.error}")
                ku_load_error = True
            elif result.value:
                kus = result.value

        pinned_uids: set[str] = set()
        pinned_kus: list[Ku] = []
        studying_kus: list[Ku] = []
        understood_kus: list[Ku] = []
        ku_by_uid = {ku.uid: ku for ku in kus}

        if is_authenticated(request):
            user_uid = require_authenticated_user(request)

            if user_relationship_service:
                pins_result = await user_relationship_service.get_pinned_entities(user_uid)
                if pins_result.is_error:
                    logger.warning(f"Failed to load bookmarks: {pins_result.error}")
                elif pins_result.value:
                    pinned_uids = set(pins_result.value)

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
        return kus, ku_load_error, pinned_uids, pinned_kus, studying_kus, understood_kus

    @rt("/ku")
    async def ku_index(request: Request) -> Any:
        """Main Ku index — search panel + flat listing with bookmarks/latest sidebar."""
        kus, ku_load_error, pinned_uids, pinned_kus, studying_kus, understood_kus = (
            await _load_ku_index_data(request)
        )

        # Studying = bookmarked for Kus. Available = everything not actively studying.
        studying_uids = {ku.uid for ku in studying_kus}
        available_kus = [ku for ku in kus if ku.uid not in studying_uids]

        # Collect filter facets from loaded Kus
        all_tags = sorted(
            {t for ku in kus for t in (ku.tags or ())} - {""}
        )
        namespaces = sorted({ku.namespace for ku in kus if ku.namespace})
        categories = sorted({ku.ku_category for ku in kus if ku.ku_category})

        # Suggestions: bookmarked (studying) first
        suggested_kus = studying_kus[:8]

        if ku_load_error:
            ku_list_content: Any = render_error_banner(
                "Unable to load knowledge units. Please try again later."
            )
        else:
            ku_list_content = _render_ku_sections(studying_kus, available_kus, pinned_uids)

        content = Div(
            PageHeader("Knowledge", subtitle="Bookmarked · Available"),
            _render_ku_search_panel(all_tags, namespaces, categories, suggested_kus),
            Div(ku_list_content, id="ku-list"),
        )

        return await BasePage(
            content=content,
            title="Knowledge",
            request=request,
            active_page="knowledge",
        )

    # -----------------------------------------------------------------
    # GET /api/ku/search — HTMX fragment: filtered Ku list
    # -----------------------------------------------------------------

    @rt("/api/ku/search")
    async def ku_search(
        request: Request,
        q: str = "",
        namespace: str = "",
        ku_type: str = "",
        tag: str = "",
        sort: str = "title",
    ) -> Any:
        """Return filtered Ku list HTML fragment for HTMX swap into #ku-list."""
        kus, _error, pinned_uids, _pinned, _studying, _understood = (
            await _load_ku_index_data(request)
        )

        filtered = _filter_kus(kus, q.strip(), namespace, ku_type, tag, sort)

        if not filtered:
            return Div(
                P(
                    "No knowledge units match your search.",
                    cls="text-muted-foreground italic py-8 text-center",
                ),
            )

        return Ul(
            *[_render_ku_row(ku, pinned_uids) for ku in filtered],
            cls="list-none p-0",
        )

    # -----------------------------------------------------------------
    # GET /ku/{uid} — Ku detail page
    # -----------------------------------------------------------------

    @rt("/ku/{uid}")
    async def ku_detail_page(request: Request, uid: str) -> Any:
        """Ku detail page — renders atomic Ku entities from KuService.

        Public: shared curriculum content is readable without authentication.
        Learning state tracking (studying, understood, bookmark) requires authentication.
        """
        user_uid: str | None = get_current_user(request)

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

        # Learning state — only available for authenticated users
        learning_state: dict[str, bool] = {"is_studying": False, "is_understood": False}
        is_pinned = False
        if user_uid:
            state_result = await ku_service.get_ku_learning_state(user_uid, uid)
            if state_result.is_ok:
                learning_state = state_result.value
            if user_relationship_service:
                pins_result = await user_relationship_service.get_pinned_entities(user_uid)
                if pins_result.is_ok and pins_result.value:
                    is_pinned = uid in set(pins_result.value)

        # Sidebar — studying KUs for contextual navigation
        sidebar_kus: list[Ku] = []
        if user_uid and ku_service:
            studying_uids_result = await ku_service.get_studying_ku_uids(user_uid)
            if studying_uids_result.is_ok and studying_uids_result.value:
                for studying_uid in studying_uids_result.value[:6]:
                    if studying_uid == uid:
                        continue
                    ku_r = await ku_service.get_ku(studying_uid)
                    if ku_r.is_ok and ku_r.value:
                        sidebar_kus.append(ku_r.value)
                    if len(sidebar_kus) >= 5:
                        break

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

        # Action buttons — learning state tracking requires authentication
        if user_uid:
            ku_action_area: Any = Div(
                _ku_learning_buttons(
                    uid, learning_state["is_studying"], learning_state["is_understood"]
                ),
                PinButton(entity_uid=uid, is_pinned=is_pinned),
                cls="flex gap-2 items-center border-t border-border pt-6 mt-8",
            )
        else:
            ku_action_area = Div(
                ButtonLink(
                    "Log in to track your progress",
                    href="/login",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                ),
                cls="border-t border-border pt-6 mt-8",
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
            ku_action_area,
            metadata_footer,
            _exercises_for_ku_section(exercises_for_ku),
            Div(
                EntityRelationshipsSection(entity_uid=uid, entity_type="ku"),
                cls="mt-8",
            ),
            cls="flex-1 min-w-0 max-w-4xl",
        )

        if has_toc:
            toc_sidebar = Div(
                Div(
                    H3("Contents", cls="font-semibold text-sm mb-3"),
                    Div(NotStr(toc_html), cls="prose prose-sm max-w-none toc-nav"),
                    cls="sticky top-20 p-5 max-h-[calc(100vh-6rem)] overflow-y-auto",
                ),
                cls="hidden lg:block w-56 shrink-0 border-l border-border",
            )
            content = Div(main_column, toc_sidebar, cls="flex gap-6")
        else:
            content = main_column

        ku_sidebar_items = [SidebarItem(label="All Knowledge", href="/ku", slug="all")]
        ku_sidebar_extra = []
        if sidebar_kus:
            ku_sidebar_extra.append(
                Li(
                    P(
                        "Studying",
                        cls="text-xs font-semibold uppercase text-muted-foreground px-4 pt-3 pb-1",
                    ),
                    Ul(
                        *[SidebarLink(text=k.title, href=f"/ku/{k.uid}") for k in sidebar_kus],
                        cls="list-none p-0",
                    ),
                )
            )

        return await SidebarPage(
            content=content,
            items=ku_sidebar_items,
            active="all",
            title="Knowledge",
            storage_key="ku-detail-sidebar",
            extra_sidebar_sections=ku_sidebar_extra or None,
            page_title=ku.title,
            request=request,
            active_page="knowledge",
            title_href="/ku",
        )

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
        "Ku UI routes registered: /ku, /api/ku/search, /ku/{uid}, "
        "/api/ku/{uid}/mark-studying, /api/ku/{uid}/mark-understood"
    )

    return []  # Routes registered via @rt() decorators


__all__ = ["create_ku_ui_routes"]
