"""Lateral relationship management list — flat, directly-editable edge list.

The authoring counterpart to the read-only visualisations (blocking chain,
alternatives grid, graph): a flat list of an entity's *direct* lateral edges
(BLOCKS / PREREQUISITE_FOR / ALTERNATIVE_TO / COMPLEMENTARY_TO, both
directions), each row carrying a delete affordance that drives the existing
``DELETE /api/{domain}/{uid}/lateral/{type}/{target_uid}`` route.

Writes (delete) use ``hx_swap="none"`` and rely on the ``relationships-changed``
event (emitted as ``HX-Trigger`` by the lateral write routes) to refresh both
this list and the graph — the single event that keeps every relationship
surface in sync. See LATERAL_RELATIONSHIPS_VISUALIZATION.md § Authoring.
"""

from __future__ import annotations

from fasthtml.common import Button, Div, Span

from core.models.relationship_names import RelationshipName
from core.ports.query_types import LateralRelationshipItem
from ui.activities._shared import safe_id
from ui.feedback import Badge, BadgeT

__all__ = [
    "LateralManageContainer",
    "lateral_manage_container_id",
    "render_lateral_manage_fragment",
]

# RelationshipName value → the route path segment the delete/create routes use.
_TYPE_TO_SEGMENT: dict[str, str] = {
    RelationshipName.BLOCKS.value: "blocks",
    RelationshipName.PREREQUISITE_FOR.value: "prerequisites",
    RelationshipName.ALTERNATIVE_TO.value: "alternatives",
    RelationshipName.COMPLEMENTARY_TO.value: "complementary",
}

# The four primary (canonical, non-inverse) lateral types this surface authors.
MANAGEABLE_TYPES: tuple[RelationshipName, ...] = (
    RelationshipName.BLOCKS,
    RelationshipName.PREREQUISITE_FOR,
    RelationshipName.ALTERNATIVE_TO,
    RelationshipName.COMPLEMENTARY_TO,
)

# (RelationshipName value, direction) → human label shown on the row.
_DIRECTIONAL_LABELS: dict[tuple[str, str], str] = {
    (RelationshipName.BLOCKS.value, "outgoing"): "Blocks",
    (RelationshipName.BLOCKS.value, "incoming"): "Blocked by",
    (RelationshipName.PREREQUISITE_FOR.value, "outgoing"): "Prerequisite for",
    (RelationshipName.PREREQUISITE_FOR.value, "incoming"): "Requires",
    (RelationshipName.ALTERNATIVE_TO.value, "outgoing"): "Alternative to",
    (RelationshipName.ALTERNATIVE_TO.value, "incoming"): "Alternative to",
    (RelationshipName.COMPLEMENTARY_TO.value, "outgoing"): "Complementary to",
    (RelationshipName.COMPLEMENTARY_TO.value, "incoming"): "Complementary to",
}


def lateral_manage_container_id(entity_uid: str) -> str:
    """DOM id for the manage-list container (safe for HTMX targeting)."""
    return f"lateral-manage-{safe_id(entity_uid)}"


def LateralManageContainer(entity_uid: str, entity_type: str) -> Div:
    """HTMX container that lazy-loads the flat edit list and refreshes on change.

    Reloads on ``load`` and on every ``relationships-changed`` event dispatched
    on ``body`` (fired by both the add modal's writes and this list's deletes).
    """
    from ui.patterns.skeleton import SkeletonLines

    return Div(
        SkeletonLines(count=2),
        id=lateral_manage_container_id(entity_uid),
        hx_get=f"/api/{entity_type}/{entity_uid}/lateral/manage",
        hx_trigger="load, relationships-changed from:body",
        hx_swap="innerHTML",
    )


def _row(entity_uid: str, entity_type: str, item: LateralRelationshipItem) -> Div:
    label = _DIRECTIONAL_LABELS.get(
        (item["type"], item.get("direction", "outgoing")),
        item["type"].replace("_", " ").title(),
    )
    delete_url = f"/api/{entity_type}/{_delete_src_tgt(entity_uid, item)}"
    return Div(
        Div(
            Badge(label, variant=BadgeT.secondary, cls="mr-2 shrink-0"),
            Span(item.get("target_title") or item["target_uid"], cls="font-medium truncate"),
            cls="flex items-center gap-2 min-w-0",
        ),
        Button(
            "×",
            type="button",
            hx_delete=delete_url,
            hx_swap="none",
            hx_confirm="Remove this relationship?",
            **{"aria-label": f"Remove {label} {item.get('target_title') or item['target_uid']}"},
            cls=(
                "text-muted-foreground hover:text-destructive text-xl leading-none "
                "px-2 cursor-pointer shrink-0"
            ),
        ),
        cls="flex items-center justify-between gap-3 py-2 border-b border-border last:border-0",
    )


def _delete_src_tgt(entity_uid: str, item: LateralRelationshipItem) -> str:
    """Return the ``{src}/lateral/{segment}/{tgt}`` tail, direction-oriented."""
    segment = _TYPE_TO_SEGMENT[item["type"]]
    target_uid = item["target_uid"]
    if item.get("direction") == "incoming":
        src, tgt = target_uid, entity_uid
    else:
        src, tgt = entity_uid, target_uid
    return f"{src}/lateral/{segment}/{tgt}"


def render_lateral_manage_fragment(
    entity_uid: str,
    entity_type: str,
    relationships: list[LateralRelationshipItem],
) -> Div:
    """Render the flat, deletable list of an entity's direct lateral edges."""
    if not relationships:
        return Div(
            "No relationships yet. Use “Add relationship” to create one.",
            cls="text-muted-foreground text-sm py-2",
        )
    return Div(
        *[_row(entity_uid, entity_type, item) for item in relationships],
        cls="divide-y divide-border",
    )
