"""Shared With Me view — type-aware inbox of entities shared via SHARES_WITH.

Renders whatever the SHARES_WITH edge points at (today: ADR-040 auto-shared
EntryReports/RevisedExercises and manually shared FormSubmissions) as one
card shape: title, entity-type badge, sharer attribution, share date, a
subject-context line ("on *{exercise}* · in *{path step}*", linked) when the
item has a resolved exercise subject, and a detail link resolved per-type via
``entity_detail_href``. Group shares are deliberately absent — they surface
on the /groups hub.

Data shape: ``SharedWithMeItem`` rows from
``UnifiedSharingService.get_shared_with_me`` — entity DTO + share-edge
metadata + ``subject_*`` context columns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import H4, A, Div, Em, P

if TYPE_CHECKING:
    from collections.abc import Sequence

    from core.ports.query_types import SharedWithMeItem

from ui.components import ButtonT, Card, CardBody
from ui.enum_helpers import get_status_badge_class
from ui.feedback import Badge
from ui.layout import Size
from ui.patterns.empty_state import EmptyState
from ui.patterns.entity_links import entity_detail_href
from ui.patterns.page_header import PageHeader
from ui.patterns.relative_time import format_relative_time
from ui.primitives import ButtonLink


def _subject_link(title: str, entity_type: str, uid: str | None) -> Any:
    """Italicized subject reference, linked when a detail page exists."""
    href = entity_detail_href(entity_type, uid) if uid else None
    if not href:
        return Em(title)
    return A(Em(title), href=href, cls="underline decoration-dotted hover:text-foreground")


def _subject_context_line(item: SharedWithMeItem) -> Any:
    """The "on *{exercise}* · in *{path step}*" line, or "" without a subject."""
    ex_title = item.get("subject_exercise_title")
    if not ex_title:
        return ""
    children: list[Any] = [
        "on ",
        _subject_link(ex_title, "exercise", item.get("subject_exercise_uid")),
    ]
    ps_title = item.get("subject_ps_title")
    if ps_title:
        children += [
            " · in ",
            _subject_link(ps_title, "path_step", item.get("subject_ps_uid")),
        ]
    return P(*children, cls="text-xs text-muted-foreground mt-2 mb-0")


def SharedItemCard(item: SharedWithMeItem) -> Any:
    """One shared entity as a card — works for any EntityType."""
    entity = item["entity"]
    title = entity.title or entity.uid
    href = entity_detail_href(entity.entity_type.value, entity.uid)
    shared_by = item.get("shared_by") or ""
    when = format_relative_time(item.get("shared_at"))

    meta_bits: list[str] = []
    if shared_by:
        meta_bits.append(f"From {shared_by}")
    if when:
        meta_bits.append(when)
    meta_line = " · ".join(meta_bits)

    return Card(
        CardBody(
            Div(
                H4(title, cls="text-sm font-medium line-clamp-2"),
                Badge(
                    str(entity.status.value),
                    variant=None,
                    size=Size.sm,
                    cls=get_status_badge_class(str(entity.status.value)),
                ),
                cls="flex items-start justify-between gap-2",
            ),
            _subject_context_line(item),
            Div(
                Badge(entity.entity_type.get_display_name(), size=Size.sm),
                P(meta_line, cls="text-xs text-muted-foreground mb-0") if meta_line else "",
                cls="flex items-center gap-2 mt-2",
            ),
            (
                Div(
                    ButtonLink("View", href=href, cls=ButtonT.primary, size="xs"),
                    cls="mt-3",
                )
                if href
                else ""
            ),
            cls="p-4",
        ),
        cls="bg-muted shadow-sm hover:shadow-md transition-shadow",
    )


def SharedWithMeView(items: Sequence[SharedWithMeItem]) -> Div:
    """Full Shared With Me page content: header + card grid or empty state."""
    return Div(
        PageHeader(
            "Shared With Me",
            subtitle="Feedback and content shared directly with you.",
        ),
        (
            Div(
                *[SharedItemCard(item) for item in items],
                cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
            )
            if items
            else EmptyState(
                title="Nothing shared with you yet",
                description=(
                    "Teacher feedback, revised exercises, and form submissions "
                    "shared with you will appear here."
                ),
                icon="📥",
            )
        ),
    )


__all__ = ["SharedItemCard", "SharedWithMeView"]
