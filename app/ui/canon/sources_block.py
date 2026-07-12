"""Shared canon sources block — the citation-DRY seam (ADR-076/ADR-077).

One renderer, two callers: the journal follow-up (canon/vault-summoned
discussion, ADR-076 + canon P3) and the Askesis assistant message (PS-scoped
readings grounding, ADR-077). Both surfaces render plain text, so a markdown
link would show as literal `[text](url)` — this renders a real anchor per
source: a CANON book links to its Resource page, a VAULT note to its
owner-verified `/gradebook/{uid}` detail (each kind's "point to the raw"
destination), with the in-source locations the passages came from.
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Div, Li, Span, Ul

from ui.components import Icon

if TYPE_CHECKING:
    from core.services.canon import CanonSource


def CanonSourcesBlock(sources: "tuple[CanonSource, ...]", cls: str = "") -> Any:
    """Clickable "Sources" block for a grounded response — kind-aware links.

    ``cls`` carries caller-specific placement (margins/alignment) — the journal
    aligns under the AI bubble past the avatar; Askesis sits inside the message
    content column. The core citation styling is shared.
    """
    from core.services.canon import SourceKind

    items = []
    for s in sources:
        if s.source_kind is SourceKind.VAULT:
            href = f"/gradebook/{s.resource_uid}"
            icon = "file-text"
        else:
            href = f"/library/resources/get?uid={s.resource_uid}"
            icon = "book-open"
        where = f" — {'; '.join(s.locators)}" if s.locators else ""
        items.append(
            Li(
                A(
                    Icon(icon, size=13, cls="inline-block mr-1 align-[-2px]"),
                    s.book_title,
                    href=href,
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
