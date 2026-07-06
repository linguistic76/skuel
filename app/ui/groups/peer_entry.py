"""Peer UserEntry detail — read-only view for group-shared content.

Rendered by ``GET /groups/{group_uid}/entries/{entry_uid}``. Access is
already gated server-side by the Cypher query; this module is pure
presentation and must not perform its own access checks.
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import Div, P

from ui.components import ButtonT, Card, CardBody, CardHeader, CardTitle
from ui.patterns.error_banner import render_inline_error
from ui.patterns.page_header import PageHeader
from ui.patterns.relative_time import format_relative_time
from ui.primitives import ButtonLink


def _attribution(payload: dict[str, Any]) -> str:
    author = payload.get("author_name") or ""
    group_name = payload.get("group_name") or ""
    when = format_relative_time(payload.get("shared_at"))

    bits: list[str] = []
    if author:
        bits.append(f"by {author}")
    if group_name:
        bits.append(f"shared to {group_name}")
    if when:
        bits.append(when)
    return " \u00b7 ".join(bits)


def PeerEntryView(payload: dict[str, Any], group_uid: str) -> Div:
    """Render a read-only view of a peer's shared UserEntry."""
    entity = payload.get("entity") or {}
    title = entity.get("title") or "Untitled entry"
    body = entity.get("processed_content") or entity.get("content") or ""

    body_block = (
        P(body, cls="whitespace-pre-wrap text-sm leading-relaxed")
        if body
        else P(
            "This entry has no readable content yet.",
            cls="text-sm text-muted-foreground",
        )
    )

    return Div(
        PageHeader(title, subtitle=_attribution(payload)),
        Card(
            CardHeader(CardTitle("Shared content")),
            CardBody(
                Div(
                    body_block,
                    cls="p-4 bg-muted rounded-lg",
                    style="max-height: 600px; overflow-y: auto;",
                ),
                Div(
                    ButtonLink(
                        "\u2190 Back to group",
                        href=f"/groups?group={group_uid}",
                        cls=ButtonT.ghost,
                    ),
                    cls="mt-4",
                ),
            ),
        ),
        cls="max-w-3xl mx-auto",
    )


def PeerEntryNotFound() -> Div:
    """404-equivalent view — used when the entry is not visible to the viewer.

    Same surface whether the group is wrong, the entry is wrong, sharing was
    revoked, or the viewer isn't a member — we don't want to distinguish
    these cases on the client.
    """
    return Div(
        PageHeader(
            "Entry not available",
            subtitle="This shared entry is either gone or no longer visible to you.",
        ),
        render_inline_error("Ask a classmate to re-share it, or head back to the Groups hub."),
        Div(
            ButtonLink("\u2190 Back to Groups", href="/groups", cls=ButtonT.ghost),
            cls="mt-4",
        ),
        cls="max-w-3xl mx-auto",
    )


__all__ = ["PeerEntryNotFound", "PeerEntryView"]
