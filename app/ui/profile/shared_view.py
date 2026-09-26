"""The Shared page at ``/profile/shared`` — two sides (Submit & Share arc R3, R6, R7).

**Shared with you** lists what the share links name the viewer for — a
classmate's entry shared with them directly or through a group they belong
to, and form submissions as before — as the R6 card: title, description,
from, date, the "Shared with you" badge, the via chips and a link to open
it. Never feedback: reports, revision requests and activity reports live in
the GradeBook (R3). A FilterBar (Type · Shared by · Via) narrows the cards
server-side through the ``/profile/shared/list-fragment`` HTMX fragment.

**Your wall** lists the viewer's own entries that are shared, one row per
entry with an audience chip per person and group, each with × Stop sharing
(``POST /api/user-entries/{uid}/unshare``, which swaps the row). Your wall
is visible to its owner only (R7).

Data shapes: ``SharedWithMeItem`` rows from
``UnifiedSharingService.get_shared_with_me`` and ``SharedByMeItem`` rows from
``get_shared_by_me``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from fasthtml.common import H2, H4, A, Button, Div, P, Span

from core.models.user_entry.audience import GROUP_PREFIX, USER_PREFIX

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fasthtml.common import FT

    from core.ports.query_types import SharedByMeItem, SharedWithMeItem

from core.ports.query_types import VIA_DIRECT
from ui.activities.filter_bar import ActivityFilterBar, FilterBarConfig, FilterSelect
from ui.components import ButtonT, Card, CardBody, Icon
from ui.feedback import Badge, BadgeT
from ui.gradebook.recipient_card import SHARED_WITH_YOU_LABEL
from ui.gradebook.review_badges import review_badges
from ui.layout import Size
from ui.patterns.empty_state import EmptyState
from ui.patterns.entity_links import entity_detail_href
from ui.patterns.page_header import PageHeader
from ui.patterns.relative_time import format_relative_time
from ui.primitives import ButtonLink

SHARED_LIST_ID = "shared-with-me-list"
WALL_ID = "your-wall"
LIST_FRAGMENT_URL = "/profile/shared/list-fragment"
SHARED_PAGE_TITLE = "Shared"
SHARED_WITH_YOU_SUBTITLE = "Work classmates and groups have shared with you."
YOUR_WALL_SUBTITLE = "What you have shared, and with whom. Stop sharing takes a share back."

_ALL = "all"
_DIRECT_LABEL = "Shared with me directly"


#: The wall row's marker. Stop-sharing chips target ``closest [data-wall-row]``
#: — never an id selector: a periodic uid (``ue:daily:…``) or an authored one
#: (``ku.ns.slug``) carries ``:`` / ``.``, which a CSS selector reads as a
#: pseudo-class / class, so ``#wall-<uid>`` would find nothing and the request
#: would never be sent.
WALL_ROW_ATTR = "data-wall-row"


# ============================================================================
# SHARED WITH YOU
# ============================================================================


def _via_chips(item: SharedWithMeItem) -> FT | str:
    """How the item reached the viewer: "directly" and/or each group."""
    chips: list[FT] = []
    if item["via_direct"]:
        chips.append(Badge("directly", variant=BadgeT.neutral, size=Size.sm))
    chips.extend(
        Badge(g["name"] or g["uid"], variant=BadgeT.neutral, size=Size.sm)
        for g in item["via_groups"]
    )
    if not chips:
        return ""
    return Div(
        Span("via", cls="text-xs text-muted-foreground"),
        *chips,
        cls="flex flex-wrap items-center gap-1 mt-2",
    )


def SharedItemCard(item: SharedWithMeItem) -> Any:
    """One shared entity as the R6 card — title, description, from, date, badges, link.

    The badges are the fixed "Shared with you" and the entry's derived
    review standing (``review_badges``: "Revised after feedback",
    "Reviewed · Teacher/AI") — what review the work went through, never the
    verdict.
    """
    entity = item["entity"]
    title = entity.title or entity.uid
    href = entity_detail_href(entity.entity_type.value, entity.uid)
    shared_by = item.get("shared_by") or ""
    when = format_relative_time(item.get("shared_at"))
    description = entity.description or ""

    meta_bits: list[str] = []
    if shared_by:
        meta_bits.append(f"From {shared_by}")
    if when:
        meta_bits.append(when)
    meta_line = " · ".join(meta_bits)

    return Card(
        CardBody(
            H4(title, cls="text-sm font-medium line-clamp-2"),
            # Badges on their own row under the title: beside it they squeeze a
            # phone-width card's title to nothing.
            Div(
                *review_badges(item["review"]),
                Badge(SHARED_WITH_YOU_LABEL, variant=BadgeT.outline, size=Size.sm),
                cls="flex flex-wrap items-center gap-1 mt-1",
            ),
            P(description, cls="text-xs text-muted-foreground mt-2 mb-0 line-clamp-3")
            if description
            else "",
            Div(
                Badge(entity.entity_type.get_display_name(), size=Size.sm),
                P(meta_line, cls="text-xs text-muted-foreground mb-0") if meta_line else "",
                cls="flex items-center gap-2 mt-2",
            ),
            _via_chips(item),
            (
                Div(
                    ButtonLink("Open", href=href, cls=ButtonT.primary, size="xs"),
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
    """ "All" + the entity types actually present, alphabetical."""
    seen: dict[str, str] = {}
    for item in items:
        entity_type = item["entity"].entity_type
        seen.setdefault(entity_type.value, entity_type.get_display_name())
    return [
        ("All", _ALL),
        *sorted(((label, value) for value, label in seen.items()), key=_option_label_key),
    ]


def _sharer_options(items: Sequence[SharedWithMeItem]) -> list[tuple[str, str]]:
    """ "All" + the sharers actually present, labeled by display name, keyed by uid."""
    seen: dict[str, str] = {}
    for item in items:
        sharer_uid = item.get("sharer_uid")
        if sharer_uid:
            seen.setdefault(sharer_uid, item.get("shared_by") or sharer_uid)
    return [
        ("All", _ALL),
        *sorted(((label, uid) for uid, label in seen.items()), key=_option_label_key),
    ]


def _via_options(items: Sequence[SharedWithMeItem]) -> list[tuple[str, str]]:
    """ "All" + "directly" (when any item is) + each group present, keyed by uid."""
    options: list[tuple[str, str]] = [("All", _ALL)]
    if any(item["via_direct"] for item in items):
        options.append((_DIRECT_LABEL, VIA_DIRECT))
    seen: dict[str, str] = {}
    for item in items:
        for g in item["via_groups"]:
            seen.setdefault(g["uid"], g["name"] or g["uid"])
    options.extend(sorted(((label, uid) for uid, label in seen.items()), key=_option_label_key))
    return options


def shared_filter_bar(items: Sequence[SharedWithMeItem]) -> FT:
    """Type · Shared by · Via FilterBar, options derived from the unfiltered list.

    The bar persists across fragment swaps (only ``#shared-with-me-list`` is
    the HTMX target), so it is built once from the full page load's items.
    """
    config = FilterBarConfig(
        fragment_url=LIST_FRAGMENT_URL,
        list_target_id=SHARED_LIST_ID,
        filters=[
            FilterSelect(name="entity_type", label="Type", options=_type_options(items)),
            FilterSelect(name="sharer", label="Shared by", options=_sharer_options(items)),
            FilterSelect(name="via", label="Via", options=_via_options(items)),
        ],
    )
    return ActivityFilterBar(config)


def shared_items_content(items: Sequence[SharedWithMeItem], filtered: bool = False) -> FT:
    """The card grid, or the state matching WHY it is empty."""
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
            "When a classmate shares their work with you, or with a group you belong to, "
            "it will appear here."
        ),
        icon="📥",
    )


# ============================================================================
# YOUR WALL
# ============================================================================


def _stop_sharing_chip(entry_uid: str, value: str, label: str) -> Span:
    """One audience chip with its × Stop sharing control."""
    return Span(
        label,
        Button(
            Icon("x", size=12),
            type="button",
            # Both dynamic parts percent-encoded: a username may carry URL
            # syntax (`&`, `+`, `#`), which would otherwise rewrite the query
            # and unshare nothing.
            hx_post=(
                f"/api/user-entries/{quote(entry_uid, safe='')}/unshare"
                f"?audience={quote(value, safe='')}"
            ),
            hx_target=f"closest [{WALL_ROW_ATTR}]",
            hx_swap="outerHTML",
            hx_disabled_elt="this",
            cls=(
                "inline-flex items-center justify-center w-4 h-4 rounded-full "
                "text-muted-foreground hover:text-foreground hover:bg-accent"
            ),
            aria_label=f"Stop sharing with {label}",
            title="Stop sharing",
        ),
        cls=(
            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border "
            "border-border bg-muted/40 text-xs font-medium text-foreground"
        ),
    )


def WallRow(item: SharedByMeItem) -> Div:
    """One of the viewer's shared entries with its review badges and audience chips."""
    entity = item["entity"]
    uid = entity.uid
    title = entity.title or uid
    when = format_relative_time(item.get("last_shared_at"))
    badges = review_badges(item["review"])
    chips: list[Span] = [
        _stop_sharing_chip(uid, f"{GROUP_PREFIX}{g['uid']}", g["name"] or g["uid"])
        for g in item["groups"]
    ]
    chips.extend(
        _stop_sharing_chip(
            uid,
            f"{USER_PREFIX}{u['username']}",
            u["display_name"] or u["username"] or u["uid"],
        )
        for u in item["users"]
        if u["username"]
    )
    return Div(
        Div(
            A(title, href=f"/gradebook/{uid}", cls="text-sm font-medium hover:underline"),
            Span(when, cls="text-xs text-muted-foreground") if when else "",
            cls="flex items-baseline justify-between gap-2",
        ),
        Div(*badges, cls="flex flex-wrap gap-1 mt-1") if badges else "",
        Div(*chips, cls="flex flex-wrap gap-1.5 mt-2") if chips else "",
        cls="py-3 border-b border-border last:border-b-0",
        **{WALL_ROW_ATTR: uid},
    )


def wall_content(items: Sequence[SharedByMeItem]) -> FT:
    """The wall's rows, or its empty state."""
    if items:
        return Div(*[WallRow(item) for item in items])
    return P(
        "You have not shared anything yet. Share from an entry's page in the GradeBook.",
        cls="text-sm text-muted-foreground py-4",
    )


# ============================================================================
# PAGE
# ============================================================================


def SharedPage(items: Sequence[SharedWithMeItem], wall: Sequence[SharedByMeItem]) -> Div:
    """Full Shared page content: header, Shared with you (filter bar + grid), Your wall."""
    return Div(
        PageHeader(SHARED_PAGE_TITLE, subtitle=SHARED_WITH_YOU_SUBTITLE),
        H2("Shared with you", cls="text-base font-semibold mb-3"),
        shared_filter_bar(items) if items else "",
        Div(shared_items_content(items), id=SHARED_LIST_ID),
        Div(
            H2("Your wall", cls="text-base font-semibold mb-1"),
            P(YOUR_WALL_SUBTITLE, cls="text-sm text-muted-foreground mb-3"),
            wall_content(wall),
            id=WALL_ID,
            cls="mt-10",
        ),
    )


__all__ = [
    "LIST_FRAGMENT_URL",
    "SHARED_LIST_ID",
    "SHARED_PAGE_TITLE",
    "SHARED_WITH_YOU_SUBTITLE",
    "VIA_DIRECT",
    "WALL_ID",
    "WALL_ROW_ATTR",
    "SharedItemCard",
    "SharedPage",
    "WallRow",
    "shared_filter_bar",
    "shared_items_content",
    "wall_content",
]
