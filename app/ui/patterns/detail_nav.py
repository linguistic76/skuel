"""Detail-page navigation pattern — the back link + footer nav pair.

One canonical style for the "← back to the listing" navigation on detail pages
(Ku / PathStep / Resource), replacing per-page copies that had drifted in
classes and HTMX attributes. Pages that navigate via HTMX (push-url swaps)
pass ``htmx=True``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Div

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
