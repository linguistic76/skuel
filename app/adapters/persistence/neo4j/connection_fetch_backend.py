"""
Connection-Fetch Backend
========================

Below-the-boundary backend for cross-domain connection fetching on Activity
Domain list/detail pages (ADR-044). Authors + executes the parameterized Cypher
that ``core/utils/`` must not hold; implements ``ConnectionFetchOperations``.

Batch-fetches entity connections (outgoing or incoming) via a single
parameterized query and resolves an activity's source PathStep. The configs
(``ConnectionConfig`` + the six per-domain constants) stay in core as pure
data: core/utils/connection_configs.py.

Does NOT extend UniversalNeo4jBackend — takes a QueryExecutor directly, like
CrossDomainBackend / InsightBackend.

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.persistence.neo4j._backend_helpers import direction_clause
from adapters.persistence.neo4j.query.cypher import (
    build_far_node_clause,
    build_owner_uids_expression,
    build_publication_clause,
)
from adapters.persistence.neo4j.query.cypher._helpers import validate_label
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.ports.base_protocols import QueryExecutor
    from core.utils.connection_configs import ConnectionConfig

logger = get_logger("skuel.persistence.connection_fetch")


class ConnectionFetchBackend:
    """Fetch cross-domain connections + curriculum origin for activities.

    Implements ``ConnectionFetchOperations`` (core/ports/connection_fetch_protocols.py).
    """

    def __init__(self, executor: QueryExecutor) -> None:
        self._executor = executor

    async def fetch_entity_connections(
        self, config: ConnectionConfig, entity_uids: list[str]
    ) -> dict[str, list[dict[str, str]]]:
        """Batch-fetch cross-domain connections for a list of entities.

        Returns a map of entity_uid -> list of connection dicts, each with keys:
        ``rel_type``, ``connected_uid``, ``title``, ``connected_type``.

        For outgoing domains (Task, Habit, Event, Choice) the connected entity is
        the target. For incoming/gravity-well domains (Goal, Principle) it is the
        source. The dict keys are unified regardless of direction.

        A connected entity is the entity owner's own or published shared content
        (``build_far_node_clause``): another user's node, or a draft, at the far end
        of an edge is left out as if the edge were absent.
        """
        if not entity_uids:
            return {}

        # Enum-typed node-label seam — validate before interpolation (ADR-044).
        validate_label(config.config_lookup_label)
        label = config.config_lookup_label.value
        rel_list = list(config.relationship_types)

        # Historical behavior: any non-"outgoing" config traverses incoming
        # (the gravity-well domains Goal/Principle).
        arrow = direction_clause("outgoing" if config.direction == "outgoing" else "incoming")
        far_node, far_node_params = build_far_node_clause("other", "anchor_owners")
        query = f"""
        MATCH (n:Entity:{label})
        WHERE n.uid IN $uids
        WITH n, {build_owner_uids_expression("n")} AS anchor_owners
        OPTIONAL MATCH (n){arrow}(other:Entity)
        WHERE type(r) IN $rel_types AND {far_node}
        RETURN n.uid AS entity_uid,
               type(r) AS rel_type,
               other.uid AS connected_uid,
               other.title AS title,
               other.entity_type AS connected_type
        """

        try:
            result = await self._executor.execute_query(
                query, {"uids": entity_uids, "rel_types": rel_list, **far_node_params}
            )
        except Exception:  # safety-net: Neo4j query failure shouldn't break the page
            logger.warning("Failed to fetch %s connections", label, exc_info=True)
            return {}

        if result.is_error:
            return {}

        connections_map: dict[str, list[dict[str, str]]] = {}
        for record in result.value:
            entity_uid: str = record["entity_uid"]
            if record.get("rel_type") is None:
                continue
            if entity_uid not in connections_map:
                connections_map[entity_uid] = []
            connections_map[entity_uid].append(
                {
                    "rel_type": record["rel_type"],
                    "connected_uid": record.get("connected_uid", ""),
                    "title": record.get("title", ""),
                    "connected_type": record.get("connected_type", ""),
                }
            )
        return connections_map

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
