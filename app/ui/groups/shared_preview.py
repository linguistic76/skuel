"""HTMX fragment renderer for 'Recent Shares' inside a group tab.

Each tile is a link to the read-only peer detail view at
``/groups/{group_uid}/entries/{entry_uid}`` — the same Cypher guard
(MEMBER_OF + SHARED_WITH_GROUP) enforces access there. Tiles show the
entry title and an attribution line ("by <author> · <relative-when>").
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import A, Div, P, Span

from ui.patterns.relative_time import format_relative_time


def _preview_tile(record: dict[str, Any], group_uid: str) -> A:
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
        href=f"/groups/{group_uid}/entries/{entry_uid}",
        cls=(
            "flex flex-col gap-1 p-2.5 rounded-lg border border-border "
            "bg-muted/30 hover:bg-muted/60 hover:border-primary/30 transition-colors "
            "min-h-[60px] no-underline"
        ),
    )


def GroupSharedPreviewList(records: list[dict[str, Any]], group_uid: str) -> Div:
    """Render the preview list for one group's Recent Shares block.

    Args:
        records: Payloads from
            ``UnifiedSharingService.get_user_entries_shared_with_group``.
        group_uid: UID of the group whose tab this list belongs to. Threaded
            into each tile's href so clicking a tile reaches
            ``/groups/{group_uid}/entries/{entry_uid}``.
    """
    return Div(
        *[_preview_tile(r, group_uid=group_uid) for r in records],
        cls="grid grid-cols-2 sm:grid-cols-3 gap-2",
    )


__all__ = ["GroupSharedPreviewList"]
