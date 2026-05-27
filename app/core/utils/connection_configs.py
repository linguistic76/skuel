"""Per-domain connection-fetch configurations (pure data).

Holds the :class:`ConnectionConfig` shape and the six per-domain config
constants that drive cross-domain connection fetching on Activity Domain
list/detail pages. These are pure data — no Cypher, no execution.

The Cypher that consumes a config lives below the hexagonal boundary in
``adapters/persistence/neo4j/connection_fetch_backend.py``
(``ConnectionFetchBackend``), behind the ``ConnectionFetchOperations`` port
(``core/ports/connection_fetch_protocols.py``). UI factories receive that
port and a config:

    connections_map = await connection_fetch_backend.fetch_entity_connections(
        TASK_CONNECTION_CONFIG, entity_uids
    )

The ``config_lookup_label`` is a :class:`NeoLabel` so the node-label seam the
backend interpolates is enum-typed at the source (ADR-044 seam typing).
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models.enums.neo_labels import NeoLabel


@dataclass(frozen=True)
class ConnectionConfig:
    """Per-domain configuration for connection fetching."""

    config_lookup_label: NeoLabel
    relationship_types: tuple[str, ...]
    direction: str = "outgoing"  # "outgoing" or "incoming"


# -- Per-domain configs -------------------------------------------------------

TASK_CONNECTION_CONFIG = ConnectionConfig(
    config_lookup_label=NeoLabel.TASK,
    relationship_types=(
        "FULFILLS_GOAL",
        "REINFORCES_HABIT",
        "APPLIES_KNOWLEDGE",
        "INFORMED_BY_PRINCIPLE",
        "RELATED_TO",
    ),
)

GOAL_CONNECTION_CONFIG = ConnectionConfig(
    config_lookup_label=NeoLabel.GOAL,
    direction="incoming",
    relationship_types=(
        "FULFILLS_GOAL",
        "SUPPORTS_GOAL",
        "CONTRIBUTES_TO_GOAL",
        "REINFORCES_GOAL",
        "APPLIES_KNOWLEDGE",
        "INFORMED_BY_GOAL",
        "RELATED_TO",
    ),
)

HABIT_CONNECTION_CONFIG = ConnectionConfig(
    config_lookup_label=NeoLabel.HABIT,
    relationship_types=(
        "REINFORCES_GOAL",
        "APPLIES_KNOWLEDGE",
        "REINFORCED_BY_PRINCIPLE",
        "RELATED_TO",
    ),
)

EVENT_CONNECTION_CONFIG = ConnectionConfig(
    config_lookup_label=NeoLabel.EVENT,
    relationship_types=(
        "REINFORCES_HABIT",
        "CELEBRATES_GOAL",
        "DEMONSTRATES_PRINCIPLE",
        "APPLIES_KNOWLEDGE",
        "RELATED_TO",
    ),
)

CHOICE_CONNECTION_CONFIG = ConnectionConfig(
    config_lookup_label=NeoLabel.CHOICE,
    relationship_types=(
        "INFORMS_GOAL_STRATEGY",
        "ENABLES_HABIT",
        "EXPRESSES_PRINCIPLE",
        "APPLIES_KNOWLEDGE",
        "RELATED_TO",
    ),
)

PRINCIPLE_CONNECTION_CONFIG = ConnectionConfig(
    config_lookup_label=NeoLabel.PRINCIPLE,
    direction="incoming",
    relationship_types=(
        "EXPRESSES_PRINCIPLE",
        "EMBODIES_PRINCIPLE",
        "ALIGNED_WITH_PRINCIPLE",
        "REINFORCED_BY_PRINCIPLE",
        "INFORMED_BY_PRINCIPLE",
        "DEMONSTRATES_PRINCIPLE",
        "RELATED_TO",
    ),
)


__all__ = [
    "CHOICE_CONNECTION_CONFIG",
    "EVENT_CONNECTION_CONFIG",
    "GOAL_CONNECTION_CONFIG",
    "HABIT_CONNECTION_CONFIG",
    "PRINCIPLE_CONNECTION_CONFIG",
    "TASK_CONNECTION_CONFIG",
    "ConnectionConfig",
]
