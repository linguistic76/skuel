"""
Cited-Resource Chip — shared
============================

Renders one CITES_RESOURCE target as a compact reference chip. Shared by the
PathStep "Resources" section and (PR 2) the Ku detail page so the citation
surface is identical wherever it appears.

The chip links to the in-app Resource detail page — the citation click
destination. SKUEL points you at the source; the prominent external "Open
source →" link lives on the detail page, not the chip. Every cited resource is
now clickable, including those with no ``source_url`` (a strict improvement over
the old source_url-only chip).

When the citation carries a ``locator`` (a free-string anchor on the
CITES_RESOURCE edge — "ch. 4", "pp. 210–214", the sailboat metaphor), the chip
appends it after the attribution, pointing at the exact spot the human should
read. Tier-1 only *displays* the locator; interpretation is left to the reader.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fasthtml.common import A, Span

from ui.components import Icon

if TYPE_CHECKING:
    from fasthtml.common import FT


def resource_chip(resource: dict) -> "FT":
    """One cited Resource as a reference chip linking to its detail page.

    Args:
        resource: Flattened Resource property dict (from ``get_cited_resources`` —
            ``r {.*}``); must carry a ``uid``. May carry an optional ``locator``
            (the citation's free-string edge anchor) merged in by the service.
    """
    author = resource.get("author") or ""
    year = resource.get("publication_year")
    attribution = f"{author}{f' ({year})' if year else ''}".strip()
    locator = resource.get("locator")
    uid = resource["uid"]

    return A(
        Icon("book-open", cls="w-3.5 h-3.5 shrink-0"),
        Span(resource.get("title") or uid, cls="font-medium"),
        Span(f"— {attribution}", cls="text-muted-foreground") if attribution else None,
        Span(f"· {locator}", cls="text-muted-foreground") if locator else None,
        Icon("arrow-right", cls="w-3 h-3 shrink-0 text-muted-foreground"),
        href=f"/library/resources/get?uid={uid}",
        cls=(
            "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border "
            "border-border bg-muted/40 text-13 text-foreground "
            "hover:bg-accent hover:text-accent-foreground"
        ),
    )


__all__ = ["resource_chip"]
