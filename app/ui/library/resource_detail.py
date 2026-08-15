"""
Library Resource Detail — Reading-First Design
==============================================

Per-Resource descriptor card at /library/resources/get?uid=...

The citation click destination (PR 1 of the Resources reference-library arc):
a cited-Resource chip on any PathStep/Ku detail page links here, and THIS page
carries the prominent "Open source →" external link. SKUEL holds a pointer, not
the book's body — it points you at the source so you go read it.

Matches the /explore/ku and /explore/ps reading-first language (calm centered
column, hero descriptor card). No async, no service calls — receives a
pre-fetched Resource entity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import H1, H2, A, Div, P, Section, Span

from ui.components import Icon
from ui.library.media_badge import media_badge
from ui.patterns.detail_nav import (
    detail_back_link,
    detail_footer_nav,
    render_entity_not_found,
)
from ui.primitives import safe_external_url, section_label

if TYPE_CHECKING:
    from fasthtml.common import FT

_COLUMN_CLS = "mx-auto max-w-[760px] px-5 pt-8 pb-20"


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def render_resource_not_found(uid: str) -> Div:
    """Render the not-found state for a Resource detail page."""
    return render_entity_not_found(
        entity_label="Resource",
        uid=uid,
        back_href="/library/resources",
        back_label="Resources",
        column_cls=_COLUMN_CLS,
    )


def render_resource_detail(resource: Any, cited_by: tuple | list = ()) -> Div:
    """Rich descriptor card for one curated Resource — the citation destination.

    Args:
        resource: A ``Resource`` entity (title, media_type, author, publisher,
            publication_year, isbn, resource_duration_minutes, description, tags,
            source_url).
        cited_by: Flat rows (uid, title, entity_type, locator) for the Kus /
            PathSteps that cite this Resource — the reciprocal of the citation
            chip. Empty renders no "Cited by" section.
    """
    title = getattr(resource, "title", "") or resource.uid
    media_type = getattr(resource, "media_type", None)
    # Annotation falls back description → content → summary, mirroring
    # Resource.get_summary(): ingestion only requires `title` and puts descriptor
    # bodies into `content`, so a body-backed annotation must still surface here.
    annotation = (
        getattr(resource, "description", None)
        or getattr(resource, "content", None)
        or getattr(resource, "summary", None)
        or ""
    )
    tags = getattr(resource, "tags", ()) or ()
    # Scheme-allowlisted: a javascript:/data: source_url renders as no button.
    source_url = safe_external_url(getattr(resource, "source_url", None))

    return Div(
        detail_back_link("Resources", "/library/resources"),
        Section(
            # Accent rail
            Div(cls="h-1 bg-strength-core"),
            Div(
                Div(media_badge(media_type), cls="mb-[18px]"),
                H1(
                    title,
                    id="resource-title",
                    cls="text-3xl font-extrabold leading-[1.12] tracking-[-0.02em]",
                ),
                _attribution_line(resource),
                _meta_chips(resource),
                _open_source_button(source_url),
                cls="px-8 pt-[30px] pb-[26px]",
            ),
            cls="bg-card border border-border rounded-[12px] shadow-[0_1px_3px_rgba(0,0,0,0.04)] overflow-hidden",
            role="region",
            **{"aria-labelledby": "resource-title"},
        ),
        _annotation_section(annotation),
        _cited_by_section(cited_by),
        _tags_section(tags),
        detail_footer_nav("Back to Resources", "/library/resources"),
        cls=_COLUMN_CLS,
    )


# ---------------------------------------------------------------------------
# Descriptor card sections
# ---------------------------------------------------------------------------


def _attribution_line(resource: Any) -> "FT":
    """Author · publisher · year, joined with middots."""
    author = getattr(resource, "author", None)
    publisher = getattr(resource, "publisher", None)
    year = getattr(resource, "publication_year", None)
    parts = [p for p in (author, publisher, str(year) if year else None) if p]
    if not parts:
        return Div()
    return P(
        " · ".join(parts),
        cls="mt-[13px] text-15 font-medium text-foreground/75",
    )


def _meta_chips(resource: Any) -> "FT":
    """ISBN + duration chips (only the present ones)."""
    isbn = getattr(resource, "isbn", None)
    duration = getattr(resource, "resource_duration_minutes", None)
    chip_cls = "inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground"
    items: list[Any] = []

    if duration:
        items.append(Span(Icon("clock", cls="w-3.5 h-3.5"), f" {duration} min", cls=chip_cls))
    if isbn:
        items.append(Span(Icon("hash", cls="w-3.5 h-3.5"), f" ISBN {isbn}", cls=chip_cls))

    if not items:
        return Div()
    return Div(*items, cls="flex items-center gap-3.5 flex-wrap mt-[14px]")


def _open_source_button(source_url: str | None) -> "FT":
    """Prominent external link — SKUEL points you at the source."""
    if not source_url:
        return Div()
    return Div(
        A(
            Span("Open source"),
            Icon("arrow-up-right", cls="w-[15px] h-[15px]"),
            href=source_url,
            target="_blank",
            rel="noopener noreferrer",
            cls=(
                "inline-flex items-center gap-2 px-[18px] py-[9px] rounded-lg "
                "bg-primary text-primary-foreground text-13 font-semibold hover:opacity-90"
            ),
        ),
        cls="mt-[24px]",
    )


def _annotation_section(description: str) -> "FT":
    """The curator's short annotation (Resource.description)."""
    if not description:
        return Div()
    return Section(
        section_label("About", tag=H2, id="resource-about-h"),
        P(description, cls="text-base leading-[1.6] text-foreground/80"),
        cls="mt-[30px]",
        role="region",
        **{"aria-labelledby": "resource-about-h"},
    )


# entity_type → (detail-page url prefix, display label). Only Ku/PathStep cite
# today, but the reverse traversal can in principle hit any :Entity — an unknown
# type falls back to a plain non-linked label (never a broken href).
_CITER_ROUTES: dict[str, tuple[str, str]] = {
    "ku": ("/explore/ku/", "Ku"),
    "path_step": ("/explore/ps/", "PathStep"),
}


def _cited_by_section(cited_by: tuple | list) -> "FT":
    """Reciprocal of the citation chip — the Kus / PathSteps that cite this Resource.

    Each row links to the citer's detail page and shows the citation locator
    ("· ch. 4") when the edge carries one. Empty renders no section.
    """
    rows = list(cited_by)
    if not rows:
        return Div()
    return Section(
        section_label("Cited by", tag=H2, id="resource-cited-by-h"),
        Div(
            *[_cited_by_row(row) for row in rows],
            cls="flex flex-col gap-2",
        ),
        cls="mt-[24px]",
        role="region",
        **{"aria-labelledby": "resource-cited-by-h"},
    )


def _cited_by_row(row: dict) -> "FT":
    """One citer as a reference row — links to its detail page, shows the locator."""
    uid = row.get("uid") or ""
    title = row.get("title") or uid
    entity_type = row.get("entity_type") or ""
    locator = row.get("locator")
    route = _CITER_ROUTES.get(entity_type)

    inner = [
        Icon("book-open", cls="w-3.5 h-3.5 shrink-0"),
        Span(title, cls="font-medium"),
        Span(f"· {route[1]}", cls="text-muted-foreground") if route else None,
        Span(f"· {locator}", cls="text-muted-foreground") if locator else None,
    ]
    chip_cls = (
        "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border "
        "border-border bg-muted/40 text-13 text-foreground"
    )
    if route:
        return A(
            *inner,
            Icon("arrow-right", cls="w-3 h-3 shrink-0 text-muted-foreground"),
            href=f"{route[0]}{uid}",
            cls=f"{chip_cls} hover:bg-accent hover:text-accent-foreground",
        )
    # Unknown citer type — render a plain, non-linked label (never a broken href).
    return Span(*inner, cls=chip_cls)


def _tags_section(tags: tuple | list) -> "FT":
    tag_list = list(tags)[:8]
    if not tag_list:
        return Div()
    return Section(
        section_label("Tags", tag=H2, id="resource-tags-h"),
        Div(
            *[
                Span(
                    Span(cls="w-1.5 h-1.5 rounded-full bg-strength-core"),
                    f" {tag}",
                    cls="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-border bg-muted/40 text-13 font-medium text-foreground/85",
                )
                for tag in tag_list
            ],
            cls="flex flex-wrap gap-2",
        ),
        cls="mt-[24px]",
        role="region",
        **{"aria-labelledby": "resource-tags-h"},
    )


__all__ = ["render_resource_detail", "render_resource_not_found"]
