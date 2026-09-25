"""HTMX fragment renderer for 'Recent Shares' inside a group tab.

Each tile links to ``/gradebook/{entry_uid}`` — the one detail page for a
UserEntry, which renders the recipient card for a viewer who is not the
owner (Submit & Share arc R6). Its read composes the same audience fragment
this list is gated by (MEMBER_OF / OWNS of an active group + SHARED_WITH_GROUP),
so whatever is listed can be opened. Tiles show the entry title and an
attribution line ("by <author> · <relative-when>").
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import A, Div, P, Span

from ui.patterns.relative_time import format_relative_time


def _preview_tile(record: dict[str, Any]) -> A:
    entity = record.get("entity") or {}
    title = entity.get("title") or "Untitled entry"
    author = record.get("author_name") or ""
    when = format_relative_time(record.get("shared_at"))
    entry_uid = entity.get("uid") or ""

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
        href=f"/gradebook/{entry_uid}",
        cls=(
            "flex flex-col gap-1 p-2.5 rounded-lg border border-border "
            "bg-muted/30 hover:bg-muted/60 hover:border-primary/30 transition-colors "
            "min-h-[60px] no-underline"
        ),
    )


def GroupSharedPreviewList(records: list[dict[str, Any]]) -> Div:
    """Render the preview list for one group's Recent Shares block.

    Args:
        records: Payloads from
            ``UnifiedSharingService.get_user_entries_shared_with_group``.
    """
    return Div(
        *[_preview_tile(r) for r in records],
        cls="grid grid-cols-2 sm:grid-cols-3 gap-2",
    )


__all__ = ["GroupSharedPreviewList"]
