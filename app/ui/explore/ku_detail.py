"""
Explore Ku Detail — Reading-First Design
=========================================

Reading-column layout for /explore/ku/{uid}/content.
Implements the design from data/handoff/explore/ku.html:
calm centered column, real reading typography, status controls
and mastery self-check below the prose.

No async, no service calls — receives pre-fetched data.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H1,
    A,
    Article,
    Button,
    Div,
    Header,
    NotStr,
    P,
    Section,
    Span,
)

from core.models.type_hints import EntityUID
from ui.components import Icon
from ui.explore.ku_mastery import render_ku_mastery_section
from ui.library.resource_chip import resource_chip
from ui.patterns.pin_button import PinButton
from ui.patterns.relationships import EntityRelationshipsSection

if TYPE_CHECKING:
    from fasthtml.common import FT

    from ui.page_contexts import RelatedConceptChip

_COLUMN_CLS = "mx-auto max-w-[700px] px-4 sm:px-6 pt-6 sm:pt-9 pb-28"

# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def render_ku_not_found(uid: str) -> Div:
    """Render the not-found state for a Ku detail fragment."""
    return Div(
        A(
            Icon("arrow-left", cls="w-3.5 h-3.5"),
            " Explore",
            href="/explore",
            cls="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-muted-foreground hover:text-foreground mb-6",
        ),
        Div(
            P("Knowledge unit not found.", cls="text-[14px] font-semibold text-foreground"),
            P(f"No KU with ID: {uid}", cls="text-[13px] text-muted-foreground mt-1"),
            A(
                "← Back to Explore",
                href="/explore",
                cls="inline-flex items-center gap-1.5 text-[13px] font-medium text-muted-foreground hover:text-foreground mt-4",
            ),
            cls="p-8 border border-border rounded-xl bg-card text-center",
        ),
        id="ku-detail-content",
        cls=_COLUMN_CLS,
    )


def render_ku_detail_content(
    *,
    ku: Any,
    uid: str,
    content_html: str,
    learning_state: dict[str, bool],
    is_pinned: bool,
    user_uid: str | None,
    mastery_checkins: list[dict] | None = None,
    resources: list[dict] | None = None,
    show_related: bool = False,
) -> Div:
    """Reading-first Ku detail content fragment.

    Serves as the HTMX fragment for GET /explore/ku/{uid}/content.
    The Alpine component (kuReading) is registered in ku-reading.js,
    loaded in the shell before the fragment arrives.

    Args:
        resources: Curated Resources this Ku cites (CITES_RESOURCE) — rendered
            as reference chips in a bottom-of-page "Resources" section, mirroring
            the PathStep detail page. SKUEL points at the source; the human reads it.
        show_related: Mount the lazy "Related concepts" fragment (vector
            similarity). FULL tier only — False (section absent) when the
            vector search service is unavailable.
    """
    status = (
        "understood"
        if learning_state.get("is_understood")
        else "studying"
        if learning_state.get("is_studying")
        else "none"
    )
    seed = {"uid": uid, "status": status}
    # Inline in x-data, never a window global set by a sibling <script>: htmx
    # defers inline-script evaluation to the settle phase, but Alpine
    # initializes the swapped tree first — the global would be undefined.
    seed_json = json.dumps(seed, default=str)

    title = getattr(ku, "title", uid) or uid
    word_count = len((content_html or "").split())
    reading_minutes = max(1, round(word_count / 150))

    post_read: list[FT] = (
        [
            render_ku_mastery_section(uid, mastery_checkins or []),
            _relationships_section(uid),
        ]
        if user_uid
        else [_relationships_section(uid)]
    )
    if resources:
        post_read.append(_resources_section(resources))
    if show_related:
        post_read.append(_related_placeholder(uid))

    return Div(
        _back_link(),
        Article(
            _article_header(uid, title, reading_minutes, user_uid, is_pinned),
            _reading_body(content_html),
            _end_of_read_marker(),
        ),
        *post_read,
        _footer_nav(),
        id="ku-detail-content",
        cls=_COLUMN_CLS,
        **{
            "x-data": f"kuReading({seed_json})",
            "@keydown.window": "onKey($event)",
        },
    )


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


def _back_link() -> "FT":
    return A(
        Icon("arrow-left", cls="w-3.5 h-3.5"),
        " Explore",
        href="/explore",
        hx_get="/explore",
        hx_push_url="true",
        cls="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-muted-foreground hover:text-foreground mb-6",
    )


def _footer_nav() -> "FT":
    return Div(
        A(
            Icon("arrow-left", cls="w-4 h-4"),
            " Back to Explore",
            href="/explore",
            hx_get="/explore",
            hx_push_url="true",
            cls="inline-flex items-center gap-2 text-[13px] font-medium text-muted-foreground hover:text-foreground",
        ),
        cls="mt-9 flex items-center",
    )


# ---------------------------------------------------------------------------
# Article header
# ---------------------------------------------------------------------------


def _article_header(
    uid: str,
    title: str,
    reading_minutes: int,
    user_uid: str | None,
    is_pinned: bool = False,
) -> "FT":
    meta_items: list[FT] = [
        Span(f"{reading_minutes} min read", cls="font-mono text-[12.5px] text-muted-foreground"),
        Span("·", cls="text-muted-foreground/40"),
    ]
    if user_uid:
        meta_items.append(_status_control(uid))
        meta_items.append(PinButton(entity_uid=EntityUID(uid), is_pinned=is_pinned))

    return Header(
        Div(
            Span(
                Icon("info", cls="w-3 h-3"),
                " Knowledge",
                cls="inline-flex items-center gap-1.5 font-mono text-[10.5px] font-medium tracking-[0.1em] uppercase text-muted-foreground",
            ),
            cls="flex flex-wrap items-center gap-2.5 mb-3",
        ),
        H1(title, cls="skuel-title font-bold"),
        Div(*meta_items, cls="flex flex-wrap items-center gap-x-4 gap-y-2 mt-4"),
        cls="mb-7",
    )


def _status_control(uid: str) -> "FT":
    def _btn(label: str, val: str, endpoint: str) -> "FT":
        return Button(
            label,
            type="button",
            role="radio",
            hx_post=endpoint,
            hx_swap="none",
            cls="px-2.5 py-1 rounded-md text-[12px] font-medium transition-colors",
            **{
                ":aria-checked": f"(status==='{val}').toString()",
                "@click": f"setStatus('{val}')",
                ":class": f"status==='{val}' ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground'",
            },
        )

    return Div(
        _btn("Studying", "studying", f"/api/ku/{uid}/mark-studying"),
        _btn("Understood", "understood", f"/api/ku/{uid}/mark-understood"),
        cls="inline-flex items-center rounded-lg border border-border p-0.5 bg-muted",
        role="radiogroup",
        **{"aria-label": "Your status with this idea"},
    )


# ---------------------------------------------------------------------------
# Reading body
# ---------------------------------------------------------------------------


def _reading_body(content_html: str) -> "FT":
    body = content_html or "<p>No content available.</p>"
    return Div(NotStr(body), cls="skuel-prose mt-7")


def _end_of_read_marker() -> "FT":
    return Div(
        Span(cls="h-px flex-1 bg-border"),
        Icon("check-circle", cls="w-4 h-4 text-muted-foreground/60"),
        Span(cls="h-px flex-1 bg-border"),
        cls="flex items-center gap-3 my-9",
    )


# ---------------------------------------------------------------------------
# Relationships section
# ---------------------------------------------------------------------------


def _relationships_section(uid: str) -> "FT":
    return Section(
        Div(
            "Relationships",
            id="rel-heading",
            cls="font-mono text-[11px] font-medium tracking-[0.09em] uppercase text-muted-foreground mb-3.5",
        ),
        EntityRelationshipsSection(entity_uid=EntityUID(uid), entity_type="ku"),
        cls="mb-9",
        role="region",
        **{"aria-labelledby": "rel-heading"},
    )


# ---------------------------------------------------------------------------
# Resources section
# ---------------------------------------------------------------------------


def _resources_section(resources: list[dict]) -> "FT":
    """Curated Resources this Ku cites (CITES_RESOURCE edges).

    Each chip links to the in-app Resource detail page (the citation click
    destination); the external source link lives there. Parity with the
    PathStep "Resources" section. See ui/library/resource_chip.
    """
    return Section(
        Div(
            "Resources",
            id="res-heading",
            cls="font-mono text-[11px] font-medium tracking-[0.09em] uppercase text-muted-foreground mb-3.5",
        ),
        Div(
            *[resource_chip(r) for r in resources if r.get("uid")],
            cls="flex flex-wrap gap-2",
        ),
        cls="mb-9",
        role="region",
        **{"aria-labelledby": "res-heading"},
    )


# ---------------------------------------------------------------------------
# Related concepts section (vector similarity — read-time lens)
# ---------------------------------------------------------------------------


def _related_placeholder(uid: str) -> "FT":
    """Lazy HTMX mount for the Related-concepts section.

    The fragment returns the full section (heading included) or an empty div,
    so an empty/failed lookup leaves no orphaned heading behind.
    """
    return Div(
        id="ku-related-fragment",
        **{
            "hx-get": f"/explore/ku/{uid}/related",
            "hx-trigger": "load",
            "hx-swap": "outerHTML",
        },
    )


def render_ku_related_concepts(related: "list[RelatedConceptChip]") -> "FT":
    """Related concepts — vector-similar Kus as reading-page chips.

    Read-time lens over embeddings: no edges exist or are created for these
    neighbours. Ordered by similarity (scores not shown); each chip links to
    the neighbour's reading page. Empty input collapses to an empty div so
    the section vanishes entirely rather than rendering a bare heading.
    """
    items = [r for r in related if r.get("uid")]
    if not items:
        return Div(id="ku-related-fragment")
    return Section(
        Div(
            "Related concepts",
            id="ku-related-heading",
            cls="font-mono text-[11px] font-medium tracking-[0.09em] uppercase text-muted-foreground mb-3.5",
        ),
        Div(
            *[
                A(
                    r.get("title") or r["uid"],
                    href=f"/explore/ku/{r['uid']}",
                    cls=(
                        "inline-flex items-center px-3 py-1.5 rounded-full border "
                        "border-border bg-muted/40 text-[13px] font-medium "
                        "text-foreground hover:bg-accent hover:text-accent-foreground"
                    ),
                )
                for r in items
            ],
            cls="flex flex-wrap gap-2",
        ),
        id="ku-related-fragment",
        cls="mb-9",
        role="region",
        **{"aria-labelledby": "ku-related-heading"},
    )


__all__ = ["render_ku_detail_content", "render_ku_not_found", "render_ku_related_concepts"]
