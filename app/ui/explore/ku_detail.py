"""
Explore Ku Detail — Pure Rendering
===================================

Renders the Ku detail content fragment for /explore/ku/{uid}/content.
No async, no service calls — receives pre-fetched data.
"""

from typing import Any

from fasthtml.common import H3, Div, NotStr, P

from adapters.inbound.ku_ui import (
    _exercises_for_ku_section,
    _ku_learning_buttons,
)
from core.models.type_hints import EntityUID
from ui.buttons import ButtonLink, ButtonT
from ui.cards import Card, CardBody
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.patterns.breadcrumbs import Breadcrumbs
from ui.patterns.metadata_badge import metadata_badge
from ui.patterns.pin_button import PinButton
from ui.patterns.relationships import EntityRelationshipsSection


def render_ku_not_found(uid: str) -> Div:
    """Render the not-found state for a Ku detail page."""
    return Div(
        Card(
            CardBody(
                H3("Knowledge Unit Not Found", cls="text-lg font-bold"),
                P(f"No KU with identifier: {uid}", cls="text-muted-foreground mt-2"),
                ButtonLink(
                    "\u2190 Back to Explore",
                    href="/explore",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                    cls="mt-4",
                ),
            ),
        ),
        id="ku-detail-content",
        cls="max-w-4xl mx-auto p-8",
    )


def render_ku_detail_content(
    *,
    ku: Any,
    uid: str,
    content_html: str,
    toc_html: str,
    learning_state: dict[str, bool],
    is_pinned: bool,
    user_uid: str | None,
    exercises_for_ku: list[dict],
) -> Div:
    """Render the full Ku detail content fragment.

    Args:
        ku: The Ku entity.
        uid: Ku UID.
        content_html: Pre-rendered markdown HTML.
        toc_html: Pre-rendered table-of-contents HTML.
        learning_state: Dict with is_studying, is_understood keys.
        is_pinned: Whether pinned by the current user.
        user_uid: Current user UID, or None if unauthenticated.
        exercises_for_ku: Exercise dicts for this Ku.
    """
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

    metadata_section = Div(*metadata_items, cls="flex flex-wrap gap-2") if metadata_items else None

    # Tags
    tags_section = None
    if getattr(ku, "tags", None):
        tag_badges = [Badge(tag, variant=BadgeT.outline, size=Size.sm) for tag in ku.tags]
        tags_section = Div(*tag_badges, cls="flex flex-wrap gap-1 mt-3")

    # Breadcrumbs
    breadcrumb_path = [
        {"uid": "explore", "title": "Explore", "url": "/explore"},
        {"uid": uid, "title": ku.title, "url": ""},
    ]

    reading_content = Div(
        NotStr(content_html or "No content available."),
        cls="prose prose-lg max-w-none",
    )

    # Action buttons
    if user_uid:
        ku_action_area: Any = Div(
            _ku_learning_buttons(
                uid, learning_state["is_studying"], learning_state["is_understood"]
            ),
            PinButton(entity_uid=EntityUID(uid), is_pinned=is_pinned),
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
            EntityRelationshipsSection(entity_uid=EntityUID(uid), entity_type="ku"),
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
        return Div(main_column, toc_sidebar, cls="flex gap-6")
    return main_column
