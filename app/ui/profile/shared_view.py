"""Shared With Me view — the reviewing inbox of entities shared via SHARES_WITH.

Renders whatever the SHARES_WITH edge points at (today: ADR-040 auto-shared
EntryReports/RevisedExercises and manually shared FormSubmissions) as one
card shape: title, entity-type badge, sharer attribution, share date, a
subject-context line ("on *{exercise}* · in *{path step}*", linked) when the
item has a resolved exercise subject, and a detail link resolved per-type via
``entity_detail_href``. A FilterBar (Type · Shared by, options derived from
the live inbox) narrows the cards server-side through the
``/profile/shared/list-fragment`` HTMX fragment (arc 2 C4 — the FilterBar
convention: no client-side filter logic). Group shares are deliberately
absent — they surface on the /groups hub.

Data shape: ``SharedWithMeItem`` rows from
``UnifiedSharingService.get_shared_with_me`` — entity DTO + share-edge
metadata + ``subject_*`` context columns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import H4, A, Div, Em, P

from core.models.enums.entity_enums import EntityType

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fasthtml.common import FT

    from core.ports.query_types import SharedWithMeItem

from ui.activities.filter_bar import ActivityFilterBar, FilterBarConfig, FilterSelect
from ui.components import ButtonT, Card, CardBody
from ui.enum_helpers import get_status_badge_class
from ui.feedback import Badge
from ui.layout import Size
from ui.patterns.empty_state import EmptyState
from ui.patterns.entity_links import entity_detail_href
from ui.patterns.page_header import PageHeader
from ui.patterns.relative_time import format_relative_time
from ui.primitives import ButtonLink

SHARED_LIST_ID = "shared-with-me-list"
LIST_FRAGMENT_URL = "/profile/shared/list-fragment"
SHARED_WITH_ME_SUBTITLE = "Work and feedback shared with you for your attention."

_ALL = "all"


def _subject_link(title: str, entity_type: str, uid: str | None) -> FT:
    """Italicized subject reference, linked when a detail page exists."""
    href = entity_detail_href(entity_type, uid) if uid else None
    if not href:
        return Em(title)
    return A(Em(title), href=href, cls="underline decoration-dotted hover:text-foreground")


def _subject_context_line(item: SharedWithMeItem) -> FT | str:
    """The "on *{exercise}* · in *{path step}*" line, or "" without a subject."""
    ex_title = item.get("subject_exercise_title")
    if not ex_title:
        return ""
    # The exercise subject links into the exchange thread (C5) — the shared
    # item IS one artifact of that exchange — not the exercise detail page.
    ex_uid = item.get("subject_exercise_uid")
    exercise_ref: FT = (
        A(
            Em(ex_title),
            href=f"/exchange?exercise={ex_uid}",
            cls="underline decoration-dotted hover:text-foreground",
        )
        if ex_uid
        else Em(ex_title)
    )
    children: list[FT | str] = ["on ", exercise_ref]
    ps_title = item.get("subject_ps_title")
    if ps_title:
        children += [
            " · in ",
            _subject_link(ps_title, EntityType.PATH_STEP.value, item.get("subject_ps_uid")),
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
        cls="bg-muted shadow-xs hover:shadow-md transition-shadow",
    )


def _option_label_key(pair: tuple[str, str]) -> str:
    """Case-insensitive sort key on an option's display label."""
    return pair[0].lower()


def _type_options(items: Sequence[SharedWithMeItem]) -> list[tuple[str, str]]:
    """ "All" + the entity types actually present in the inbox, alphabetical."""
    seen: dict[str, str] = {}
    for item in items:
        entity_type = item["entity"].entity_type
        seen.setdefault(entity_type.value, entity_type.get_display_name())
    return [
        ("All", _ALL),
        *sorted(((label, value) for value, label in seen.items()), key=_option_label_key),
    ]


def _sharer_options(items: Sequence[SharedWithMeItem]) -> list[tuple[str, str]]:
    """ "All" + the sharers actually present, labeled by display name, keyed by uid.

    Items with no resolvable sharer (``created_by`` absent) contribute no
    option — they stay visible under "All".
    """
    seen: dict[str, str] = {}
    for item in items:
        sharer_uid = item.get("sharer_uid")
        if sharer_uid:
            seen.setdefault(sharer_uid, item.get("shared_by") or sharer_uid)
    return [
        ("All", _ALL),
        *sorted(((label, uid) for uid, label in seen.items()), key=_option_label_key),
    ]


def shared_filter_bar(items: Sequence[SharedWithMeItem]) -> FT:
    """Type · Shared-by FilterBar, options derived from the unfiltered inbox.

    The bar persists across fragment swaps (only ``#shared-with-me-list`` is
    the HTMX target), so it is built once from the full page load's items.
    """
    config = FilterBarConfig(
        fragment_url=LIST_FRAGMENT_URL,
        list_target_id=SHARED_LIST_ID,
        filters=[
            FilterSelect(name="entity_type", label="Type", options=_type_options(items)),
            FilterSelect(name="sharer", label="Shared by", options=_sharer_options(items)),
        ],
    )
    return ActivityFilterBar(config)


def shared_items_content(items: Sequence[SharedWithMeItem], filtered: bool = False) -> FT:
    """The card grid, or the state matching WHY it is empty.

    ``filtered`` distinguishes "nothing shared at all" (full EmptyState) from
    "nothing matches this filter" (muted line — the inbox itself isn't empty).
    """
    if items:
        return Div(
            *[SharedItemCard(item) for item in items],
            cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
        )
    if filtered:
        return P(
            "Nothing shared matches this filter.",
            cls="text-sm text-muted-foreground py-4 text-center",
        )
    return EmptyState(
        title="Nothing shared with you yet",
        description=(
            "When someone shares work or feedback for your attention — "
            "teacher feedback, revised exercises, form submissions — "
            "it will appear here."
        ),
        icon="📥",
    )


def SharedWithMeView(items: Sequence[SharedWithMeItem]) -> Div:
    """Full Shared With Me page content: header + filter bar + card grid.

    The filter bar renders only when there is something to narrow; the list
    wrapper keeps its id either way so the fragment always has a swap target.
    """
    return Div(
        PageHeader("Shared With Me", subtitle=SHARED_WITH_ME_SUBTITLE),
        shared_filter_bar(items) if items else "",
        Div(shared_items_content(items), id=SHARED_LIST_ID),
    )


__all__ = [
    "LIST_FRAGMENT_URL",
    "SHARED_LIST_ID",
    "SHARED_WITH_ME_SUBTITLE",
    "SharedItemCard",
    "SharedWithMeView",
    "shared_filter_bar",
    "shared_items_content",
]
