"""
Connection-Fetch Backend
========================

Below-the-boundary backend for the links an Activity Domain page shows (ADR-044):
the detail page's Connections section and the list card. Implements
``ConnectionFetchOperations``.

What a page shows is the domain's page views in the relationship registry — the
definitions that carry a ``page_heading`` (ADR-090 §2). One batched, parameterized
statement per page reads every edge of those types in both directions, behind the
far-node wall (``build_far_node_clause``); each row is then placed under the view
that reads it, by edge type, direction and far-end label. Also resolves an
activity's source PathStep.

Does NOT extend UniversalNeo4jBackend — takes a QueryExecutor directly, like
CrossDomainBackend / InsightBackend.

See: /docs/decisions/ADR-090-one-link-per-fact-a-view-per-domain.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from adapters.persistence.neo4j.query.cypher import (
    build_far_node_clause,
    build_owner_uids_expression,
    build_publication_clause,
)
from adapters.persistence.neo4j.query.cypher._helpers import validate_label
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import get_config_by_label
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.models.relationship_registry import UnifiedRelationshipDefinition
    from core.ports.base_protocols import QueryExecutor
    from core.ports.query_types import EntityConnection

logger = get_logger("skuel.persistence.connection_fetch")


class _LinkRow(TypedDict):
    """One edge the page statement read, as its RETURN projects it."""

    entity_uid: str
    rel_type: str
    outgoing: bool  # the anchor is the edge's start node
    far_labels: list[str]
    connected_uid: str
    title: str
    connected_type: str


def _link_row(record: dict[str, Any]) -> _LinkRow | None:  # boundary: neo4j driver record
    """The typed row, or None for an anchor the OPTIONAL MATCH found no edge for."""
    if record.get("rel_type") is None:
        return None
    connected_uid = str(record.get("connected_uid") or "")
    return {
        "entity_uid": str(record["entity_uid"]),
        "rel_type": str(record["rel_type"]),
        "outgoing": bool(record["outgoing"]),
        "far_labels": [str(label) for label in record.get("far_labels") or []],
        "connected_uid": connected_uid,
        "title": str(record.get("title") or connected_uid),
        "connected_type": str(record.get("connected_type") or ""),
    }


def _view_of(
    views: tuple[UnifiedRelationshipDefinition, ...], row: _LinkRow
) -> UnifiedRelationshipDefinition | None:
    """The page view that reads this edge, or None when no view does.

    The registry holds at most one per edge type, direction and far-end label
    (tests/unit/test_activity_link_invariant.py § no double listing).
    """
    direction = "outgoing" if row["outgoing"] else "incoming"
    for view in views:
        if (
            view.relationship.value == row["rel_type"]
            and view.direction == direction
            and (view.target_label == NeoLabel.ENTITY or view.target_label in row["far_labels"])
        ):
            return view
    return None


class ConnectionFetchBackend:
    """Fetch the page links + curriculum origin of activities.

    Implements ``ConnectionFetchOperations`` (core/ports/connection_fetch_protocols.py).
    """

    def __init__(self, executor: QueryExecutor) -> None:
        self._executor = executor

    async def fetch_entity_connections(
        self, label: NeoLabel, entity_uids: list[str]
    ) -> dict[str, list[EntityConnection]]:
        """Batch-fetch the page links of ``label`` entities, both directions.

        Returns ``entity_uid -> rows`` (``heading``, ``rel_type``, ``connected_uid``,
        ``title``, ``connected_type``), ordered by the domain's page views and then
        by title. A far end shown under two views that share a heading (one link
        stored under two names) is listed once under it.

        A connected entity is the entity owner's own or published shared content
        (``build_far_node_clause``): another user's node, or a draft, at the far end
        of an edge is left out as if the edge were absent.
        """
        config = get_config_by_label(label)
        views = config.page_views() if config is not None else ()
        if not entity_uids or not views:
            return {}

        # Enum-typed seams — validated before interpolation (ADR-044).
        validate_label(label)
        rel_types = sorted({RelationshipName(view.relationship).value for view in views})
        far_node, far_node_params = build_far_node_clause("other", "anchor_owners")
        query = f"""
        MATCH (n:{NeoLabel.ENTITY.value}:{label.value})
        WHERE n.uid IN $uids
        WITH n, {build_owner_uids_expression("n")} AS anchor_owners
        OPTIONAL MATCH (n)-[r:{"|".join(rel_types)}]-(other:{NeoLabel.ENTITY.value})
        WHERE {far_node}
        RETURN n.uid AS entity_uid,
               type(r) AS rel_type,
               startNode(r) = n AS outgoing,
               labels(other) AS far_labels,
               other.uid AS connected_uid,
               other.title AS title,
               other.entity_type AS connected_type
        """

        try:
            result = await self._executor.execute_query(
                query, {"uids": entity_uids, **far_node_params}
            )
        except Exception:  # safety-net: Neo4j query failure shouldn't break the page
            logger.warning("Failed to fetch %s connections", label.value, exc_info=True)
            return {}

        if result.is_error:
            return {}

        # A heading's place is its first view's — two views sharing it list as one.
        rank: dict[str, int] = {}
        for index, page_view in enumerate(views):
            rank.setdefault(page_view.page_heading or "", index)

        placed: dict[str, list[EntityConnection]] = {}
        seen: set[tuple[str, str, str]] = set()
        for record in result.value:
            row = _link_row(record)
            if row is None:
                continue
            view = _view_of(views, row)
            if view is None:
                continue
            heading = view.page_heading or ""
            key = (row["entity_uid"], heading, row["connected_uid"])
            if key in seen:
                continue
            seen.add(key)
            placed.setdefault(row["entity_uid"], []).append(
                {
                    "heading": heading,
                    "rel_type": row["rel_type"],
                    "connected_uid": row["connected_uid"],
                    "title": row["title"],
                    "connected_type": row["connected_type"],
                }
            )

        def page_order(row: EntityConnection) -> tuple[int, str]:
            return rank[row["heading"]], row["title"]

        return {entity_uid: sorted(rows, key=page_order) for entity_uid, rows in placed.items()}

    async def fetch_source_pathstep(self, ps_uid: str, owner_uid: str) -> dict[str, str] | None:
        """Resolve a spawned activity's ``source_path_step_uid`` to its PathStep title.

        Returns ``{"uid", "title"}`` or ``None`` if the PathStep is missing or the
        lookup fails. A single primary-key lookup — cheap enough for a cold detail
        render. Surfaces the curriculum origin of activities spawned by PathStep
        engagement (their ``source_path_step_uid``).

        The match is bound to ``:PathStep`` — shared curriculum. The property is a
        plain uid any writer can set (a vault file writes it verbatim), so a uid that
        names anything else — another user's task or journal — renders nothing,
        exactly as a uid that names no node does.

        A draft step resolves only for an owner who has engaged it: a learner who
        started a step keeps seeing where their activity came from after the step is
        unpublished, and a uid written into a vault file is not engagement. The
        predicate is ``build_publication_clause``.

        Args:
            ps_uid: the activity's ``source_path_step_uid``.
            owner_uid: the activity's owner — the user the detail route verified.
        """
        if not ps_uid:
            return None

        published, params = build_publication_clause("ps")
        query = f"""
        MATCH (ps:{NeoLabel.PATH_STEP.value} {{uid: $uid}})
        WHERE {published}
           OR EXISTS {{
               MATCH (:{NeoLabel.USER.value} {{uid: $owner_uid}})
                     -[:{RelationshipName.ENGAGED_WITH.value}]->(ps)
           }}
        RETURN ps.uid AS uid, ps.title AS title
        """
        try:
            result = await self._executor.execute_query(
                query, {**params, "uid": ps_uid, "owner_uid": owner_uid}
            )
        except Exception:  # safety-net: a missing source PathStep shouldn't break the page
            logger.warning("Failed to fetch source PathStep %s", ps_uid, exc_info=True)
            return None

        if result.is_error or not result.value:
            return None

        record = result.value[0]
        return {"uid": record["uid"], "title": record.get("title") or record["uid"]}


__all__ = ["ConnectionFetchBackend"]
