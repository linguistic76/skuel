"""Per-group full list page — all peer UserEntries shared with one group.

Rendered by ``GET /groups/{group_uid}``. Access is already gated server-side
by the Cypher `MEMBER_OF` match in
``UnifiedSharingService.get_user_entries_shared_with_group``; this module is
pure presentation.

Distinct from ``ui/groups/shared_preview.py`` (the HTMX preview fragment
embedded in the hub tab) and ``ui/groups/peer_entry.py`` (read-only detail
view for a single entry).
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import Div, P
from monsterui.franken import ButtonT

from ui.groups.shared_preview import GroupSharedPreviewList
from ui.patterns.error_banner import render_inline_error
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink


def GroupSharesPage(
    group_name: str,
    records: list[dict[str, Any]],
    group_uid: str,
) -> Div:
    """Full list of peer shares for one group.

    Args:
        group_name: Display name for the header subtitle.
        records: Payloads from
            ``UnifiedSharingService.get_user_entries_shared_with_group``.
        group_uid: UID of the group — threaded into each tile's href so
            clicks route to ``/groups/{group_uid}/entries/{entry_uid}``.
    """
    body: Div
    if records:
        body = GroupSharedPreviewList(records, group_uid=group_uid)
    else:
        body = Div(
            P(
                "No classmates have shared anything with this group yet.",
                cls="text-sm text-muted-foreground text-center py-8",
            )
        )

    return Div(
        PageHeader(group_name, subtitle="Shared with this group"),
        body,
        Div(
            ButtonLink(
                "\u2190 Back to Groups",
                href=f"/groups?group={group_uid}",
                cls=ButtonT.ghost,
            ),
            cls="mt-6",
        ),
        cls="max-w-5xl mx-auto",
    )


def GroupSharesNotAvailable() -> Div:
    """404-equivalent view — the viewer isn't a member or the group is gone.

    Same surface whether the group uid is wrong, the group is deactivated, or
    the viewer isn't a member — we don't want to distinguish these cases on
    the client.
    """
    return Div(
        PageHeader(
            "Group not available",
            subtitle="This group is either gone or no longer visible to you.",
        ),
        render_inline_error("Ask a teacher to add you, or head back to the Groups hub."),
        Div(
            ButtonLink("\u2190 Back to Groups", href="/groups", cls=ButtonT.ghost),
            cls="mt-4",
        ),
        cls="max-w-3xl mx-auto",
    )


__all__ = ["GroupSharesNotAvailable", "GroupSharesPage"]
