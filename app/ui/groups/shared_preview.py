"""HTMX fragment renderer for 'Recent Shares' inside a group tab.

Each tile links to ``/gradebook/{entry_uid}`` — the one detail page for a
UserEntry, which renders the recipient card for a viewer who is not the
owner (Submit & Share arc R6). The rows are ``SharedWithMeItem``s from the
one *Shared with you* reader narrowed to this group (``via=group_uid``), so
whatever is listed can be opened. Tiles show the entry title and an
attribution line ("by <owner> · <relative-when>").
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fasthtml.common import A, Div, P, Span

from ui.patterns.relative_time import format_relative_time

if TYPE_CHECKING:
    from collections.abc import Sequence

    from core.ports.query_types import SharedWithMeItem


def _preview_tile(item: SharedWithMeItem) -> A:
    entity = item["entity"]
    title = entity.title or "Untitled entry"
    author = item.get("shared_by") or ""
    when = format_relative_time(item.get("shared_at"))

    meta_bits: list[str] = []
    if author:
        meta_bits.append(f"by {author}")
    if when:
        meta_bits.append(when)
    meta_line = " \u00b7 ".join(meta_bits)

    return A(
        Span(
            title,
            cls="text-xs font-medium text-foreground line-clamp-2 leading-snug",
        ),
        P(meta_line, cls="text-11 text-muted-foreground mt-1") if meta_line else "",
        href=f"/gradebook/{entity.uid}",
        cls=(
            "flex flex-col gap-1 p-2.5 rounded-lg border border-border "
            "bg-muted/30 hover:bg-muted/60 hover:border-primary/30 transition-colors "
            "min-h-[60px] no-underline"
        ),
    )


def GroupSharedPreviewList(records: Sequence[SharedWithMeItem]) -> Div:
    """Render the preview list for one group's Recent Shares block.

    Args:
        records: ``SharedWithMeItem`` rows from
            ``UnifiedSharingService.get_shared_with_me(via=group_uid)``.
    """
    return Div(
        *[_preview_tile(r) for r in records],
        cls="grid grid-cols-2 sm:grid-cols-3 gap-2",
    )


__all__ = ["GroupSharedPreviewList"]
