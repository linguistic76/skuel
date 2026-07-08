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
from ui.primitives import safe_external_url

if TYPE_CHECKING:
    from fasthtml.common import FT

_COLUMN_CLS = "mx-auto max-w-[760px] px-5 pt-8 pb-20"


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def render_resource_not_found(uid: str) -> Div:
    """Render the not-found state for a Resource detail page."""
    return Div(
        _back_link(),
        Div(
            P("Resource not found.", cls="text-[14px] font-semibold text-foreground"),
            P(f"No resource with ID: {uid}", cls="text-[13px] text-muted-foreground mt-1"),
            A(
                "← Back to Resources",
                href="/library/resources",
                cls="inline-flex items-center gap-1.5 text-[13px] font-medium text-muted-foreground hover:text-foreground mt-4",
            ),
            cls="p-8 border border-border rounded-[12px] bg-card text-center",
        ),
        cls=_COLUMN_CLS,
    )


def render_resource_detail(resource: Any) -> Div:
    """Rich descriptor card for one curated Resource — the citation destination.

    Args:
        resource: A ``Resource`` entity (title, media_type, author, publisher,
            publication_year, isbn, resource_duration_minutes, description, tags,
            source_url).
    """
    title = getattr(resource, "title", "") or resource.uid
    media_type = getattr(resource, "media_type", None)
    description = getattr(resource, "description", "") or ""
    tags = getattr(resource, "tags", ()) or ()
    # Scheme-allowlisted: a javascript:/data: source_url renders as no button.
    source_url = safe_external_url(getattr(resource, "source_url", None))

    return Div(
        _back_link(),
        Section(
            # Accent rail
            Div(cls="h-1 bg-strength-core"),
            Div(
                Div(media_badge(media_type), cls="mb-[18px]"),
                H1(
                    title,
                    id="resource-title",
                    cls="text-[30px] font-extrabold leading-[1.12] tracking-[-0.02em]",
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
        _annotation_section(description),
        _tags_section(tags),
        _footer_nav(),
        cls=_COLUMN_CLS,
    )


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


def _back_link() -> "FT":
    return A(
        Icon("arrow-left", cls="w-[15px] h-[15px]"),
        " Resources",
        href="/library/resources",
        cls="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-muted-foreground hover:text-foreground mb-[18px]",
    )


def _footer_nav() -> "FT":
    return Div(
        A(
            Icon("arrow-left", cls="w-4 h-4"),
            " Back to Resources",
            href="/library/resources",
            cls="inline-flex items-center gap-2 text-[13px] font-medium text-muted-foreground hover:text-foreground",
        ),
        cls="mt-9 flex items-center",
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
        cls="mt-[13px] text-[15px] font-medium text-foreground/75",
    )


def _meta_chips(resource: Any) -> "FT":
    """ISBN + duration chips (only the present ones)."""
    isbn = getattr(resource, "isbn", None)
    duration = getattr(resource, "resource_duration_minutes", None)
    chip_cls = "inline-flex items-center gap-1.5 text-[12.5px] font-medium text-muted-foreground"
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
                "bg-primary text-primary-foreground text-[13.5px] font-semibold hover:opacity-90"
            ),
        ),
        cls="mt-[24px]",
    )


def _annotation_section(description: str) -> "FT":
    """The curator's short annotation (Resource.description)."""
    if not description:
        return Div()
    return Section(
        H2(
            "About",
            id="resource-about-h",
            cls="block text-xs font-semibold uppercase tracking-[0.05em] text-muted-foreground mb-[9px]",
        ),
        P(description, cls="text-[16px] leading-[1.6] text-foreground/80"),
        cls="mt-[30px]",
        role="region",
        **{"aria-labelledby": "resource-about-h"},
    )


def _tags_section(tags: tuple | list) -> "FT":
    tag_list = list(tags)[:8]
    if not tag_list:
        return Div()
    return Section(
        H2(
            "Tags",
            id="resource-tags-h",
            cls="block text-xs font-semibold uppercase tracking-[0.05em] text-muted-foreground mb-[9px]",
        ),
        Div(
            *[
                Span(
                    Span(cls="w-1.5 h-1.5 rounded-full bg-strength-core"),
                    f" {tag}",
                    cls="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-border bg-muted/40 text-[13px] font-medium text-foreground/85",
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
