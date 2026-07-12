"""Shared canon sources block — the citation-DRY seam (ADR-076/ADR-077).

One renderer, two callers: the journal follow-up (canon-summoned discussion,
ADR-076) and the Askesis assistant message (PS-scoped readings grounding,
ADR-077). Both surfaces render plain text, so a markdown link would show as
literal `[text](url)` — this renders a real anchor per book to its Resource
page (the citation's "point to the raw" destination) with the in-book
locations the passages came from.
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Div, Li, Span, Ul

from ui.components import Icon

if TYPE_CHECKING:
    from core.services.canon import CanonSource


def CanonSourcesBlock(sources: "tuple[CanonSource, ...]", cls: str = "") -> Any:
    """Clickable "Sources" block for a canon-grounded response.

    ``cls`` carries caller-specific placement (margins/alignment) — the journal
    aligns under the AI bubble past the avatar; Askesis sits inside the message
    content column. The core citation styling is shared.
    """
    items = []
    for s in sources:
        where = f" — {'; '.join(s.locators)}" if s.locators else ""
        items.append(
            Li(
                A(
                    Icon("book-open", size=13, cls="inline-block mr-1 align-[-2px]"),
                    s.book_title,
                    href=f"/library/resources/get?uid={s.resource_uid}",
                    cls="text-primary hover:underline font-medium no-underline",
                ),
                Span(where, cls="text-muted-foreground"),
                cls="text-[13px] leading-relaxed",
            )
        )
    return Div(
        Span(
            "Sources",
            cls="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground",
        ),
        Ul(*items, cls="mt-1 space-y-1 list-none pl-0"),
        cls=f"border-l-2 border-border pl-3 {cls}".strip(),
    )
