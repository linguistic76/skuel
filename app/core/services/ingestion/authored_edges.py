"""
Authored-Edge Fingerprint
=========================

The edge set a file's registered frontmatter fields declare, in the form the
file's ``IngestionMetadata`` row stores and the refresh pass diffs.

A re-ingest MERGEs every edge the file declares; the fingerprint recorded at
the previous ingest is what makes a *dropped* declaration visible. The diff
``prior - current`` is exactly the set of edges this file authored but omits
from its current frontmatter — and nothing else: an edge of the same type
written by an app door (lateral routes, prerequisite approval, exercise
curriculum links) is not in the file's fingerprint and is never touched. An
edge MERGEd by both a file and an app door is one edge; the file's retraction
deletes it — the vault is the author (ADR-070 Decision 10).

Scope is the entity's registered relationship fields
(``EntityIngestionConfig.relationship_config``) — the same fields the
relationship template reads, so the fingerprint and the write cannot drift.

Key form: ``{rel_type}|{direction}|{target_uid}``. ``|`` is not part of any
uid or relationship type (separator grammar), so the key splits unambiguously.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.ingestion.ingestion_types import AuthoredEdge, EdgeDirection
from core.models.relationship_names import RelationshipName
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from core.ingestion.ingestion_types import RelationshipConfig

logger = get_logger("skuel.services.ingestion.authored_edges")

_KEY_SEPARATOR = "|"
_DIRECTIONS: frozenset[str] = frozenset({"incoming", "outgoing"})


def _edge_direction(rel_info: RelationshipConfig) -> EdgeDirection:
    """The pattern the relationship template writes for this field."""
    return "incoming" if rel_info.get("direction") == "incoming" else "outgoing"


def _declared_targets(value: object) -> list[str]:
    """The target uids a prepared field value can create edges for.

    Mirrors the relationship template's read of the same value: a string is one
    target, a list its elements. A non-string element or an empty string can
    match no node and authors nothing.
    """
    if isinstance(value, str):
        candidates: list[object] = [value]
    elif isinstance(value, list | tuple | set):
        candidates = list(value)
    else:
        return []
    return [target for target in candidates if isinstance(target, str) and target]


def authored_edge_fingerprint(
    entity_data: Mapping[str, object],
    relationship_config: Mapping[str, RelationshipConfig] | None,
) -> list[str]:
    """Sorted, de-duplicated keys for every edge the prepared entity declares.

    Computed from the prepared ``entity_data`` over the registered relationship
    fields only — the precondition (a field is registered) is the guard, not a
    list of types. Two declarations of one target are one edge (MERGE), so the
    key set is a set.
    """
    if not relationship_config:
        return []
    keys: set[str] = set()
    for field_name, rel_info in relationship_config.items():
        direction = _edge_direction(rel_info)
        for target_uid in _declared_targets(entity_data.get(field_name)):
            keys.add(_KEY_SEPARATOR.join((rel_info["rel_type"], direction, target_uid)))
    return sorted(keys)


def parse_authored_edge(key: str) -> AuthoredEdge | None:
    """Decode one fingerprint key; ``None`` when it names no edge the template
    writes (unknown relationship type or direction) — such a key can address
    no edge, so the caller skips it rather than failing the sync."""
    parts = key.split(_KEY_SEPARATOR, 2)
    if len(parts) != 3 or not all(parts):
        return None
    rel_type_name, direction, target_uid = parts
    rel_type = RelationshipName.from_string(rel_type_name)
    if rel_type is None or direction not in _DIRECTIONS:
        return None
    return AuthoredEdge(
        rel_type=rel_type,
        direction="incoming" if direction == "incoming" else "outgoing",
        target_uid=target_uid,
    )


def retracted_edges(prior: Iterable[str], current: Iterable[str]) -> list[AuthoredEdge]:
    """The edges the previous ingest authored that the current declaration
    drops — decoded for the delete primitive, in key order.

    A dropped key that names no edge is skipped with a warning: the edge it once
    recorded is not retracted, and the caller re-stamps the row without the key, so
    the warning is the only trace that a stored edge of a retired type may remain.
    """
    dropped = sorted(set(prior) - set(current))
    edges: list[AuthoredEdge] = []
    for key in dropped:
        edge = parse_authored_edge(key)
        if edge is None:
            logger.warning(
                "Authored-edge key names no edge the ingestion writes; "
                "the edge it recorded is not retracted",
                extra={"authored_edge_key": key},
            )
            continue
        edges.append(edge)
    return edges


def goals_losing_contributions(edges: Iterable[AuthoredEdge]) -> list[str]:
    """The goals a retraction takes a contribution from — its outgoing CONTRIBUTES_TO_GOAL targets.

    Only a task or an event authors that edge outgoing, so every target is a goal
    whose tally the retraction changes; the caller announces them, since nothing
    can find them from the contributor once the edge is gone.
    """
    return [
        edge.target_uid
        for edge in edges
        if edge.rel_type is RelationshipName.CONTRIBUTES_TO_GOAL and edge.direction == "outgoing"
    ]


__all__ = [
    "authored_edge_fingerprint",
    "goals_losing_contributions",
    "parse_authored_edge",
    "retracted_edges",
]
