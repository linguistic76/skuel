"""Detail-page navigation pattern — the back link + footer nav pair.

One canonical style for the "← back to the listing" navigation on detail pages
(Ku / PathStep / Resource), replacing per-page copies that had drifted in
classes and HTMX attributes. Pages that navigate via HTMX (push-url swaps)
pass ``htmx=True``.

The not-found state of those same pages lives here too
(:func:`render_entity_not_found`) — it is back-link plus a bordered card, and
the three copies had drifted in both the card radius and the back link.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Div, P

from ui.components import Icon

if TYPE_CHECKING:
    from fasthtml.common import FT


def _htmx_attrs(href: str, htmx: bool) -> dict[str, Any]:
    return {"hx_get": href, "hx_push_url": "true"} if htmx else {}


def detail_back_link(label: str, href: str, *, htmx: bool = False) -> FT:
    """Compact top-of-page back link (e.g. "← Explore")."""
    return A(
        Icon("arrow-left", cls="w-[15px] h-[15px]"),
        f" {label}",
        href=href,
        cls=(
            "inline-flex items-center gap-1.5 text-[12.5px] font-semibold "
            "text-muted-foreground hover:text-foreground mb-[18px]"
        ),
        **_htmx_attrs(href, htmx),
    )


def render_entity_not_found(
    *,
    entity_label: str,
    uid: str,
    back_href: str,
    back_label: str,
    column_cls: str,
    content_id: str | None = None,
    uid_label: str | None = None,
) -> FT:
    """Not-found state for a detail page: back link + a bordered explanation card.

    Args:
        entity_label: Sentence-initial noun for the headline, e.g. ``"Path step"``
            → "Path step not found.".
        uid: The UID that was not found.
        back_href: Listing URL for both the top back link and the card's link.
        back_label: Listing name, e.g. ``"Explore"``.
        column_cls: The page's reading-column classes — these differ per page
            (Ku reads narrower than PathStep/Resource).
        content_id: Element id, for pages swapped in as an HTMX fragment.
        uid_label: Noun for the "No {x} with ID" line when it differs from a
            lowercased ``entity_label`` (e.g. "KU", not "knowledge unit").
    """
    attrs: dict[str, str] = {"id": content_id} if content_id is not None else {}
    attrs["cls"] = column_cls
    return Div(
        detail_back_link(back_label, back_href),
        Div(
            P(f"{entity_label} not found.", cls="text-[14px] font-semibold text-foreground"),
            P(
                f"No {uid_label or entity_label.lower()} with ID: {uid}",
                cls="text-[13px] text-muted-foreground mt-1",
            ),
            A(
                f"← Back to {back_label}",
                href=back_href,
                cls=(
                    "inline-flex items-center gap-1.5 text-[13px] font-medium "
                    "text-muted-foreground hover:text-foreground mt-4"
                ),
            ),
            cls="p-8 border border-border rounded-[12px] bg-card text-center",
        ),
        **attrs,
    )


def detail_footer_nav(label: str, href: str, *, htmx: bool = False) -> FT:
    """Bottom-of-page back navigation (e.g. "← Back to Explore")."""
    return Div(
        A(
            Icon("arrow-left", cls="w-4 h-4"),
            f" {label}",
            href=href,
            cls=(
                "inline-flex items-center gap-2 text-[13px] font-medium "
                "text-muted-foreground hover:text-foreground"
            ),
            **_htmx_attrs(href, htmx),
        ),
        cls="mt-9 flex items-center",
    )
