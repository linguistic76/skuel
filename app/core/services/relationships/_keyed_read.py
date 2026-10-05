"""
Keyed Read
==========

What a registry key asks the backend for. A keyed reader names a definition by its
``method_key``; the definition decides the edge type, the direction, the tier (an
edge-property filter) and the far end's kind (``target_label``). All three keyed
readers on ``UnifiedRelationshipService`` resolve the key here, so none of them can
carry part of the definition and drop the rest.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_registry import (
    DomainRelationshipConfig,
    UnifiedRelationshipDefinition,
)
from core.models.type_hints import Neo4jProperties
from core.utils.result_simplified import Errors, Result


@dataclass(frozen=True)
class KeyedRead:
    """A definition and the two filters a read of it carries to the backend."""

    spec: UnifiedRelationshipDefinition
    properties: Neo4jProperties | None
    target_label: NeoLabel | None


def _edge_filter(spec: UnifiedRelationshipDefinition) -> Neo4jProperties | None:
    """The definition's tier as an edge-property filter, or ``None`` when untiered.

    GOALS_CONFIG's ``essential_habits`` reads only the ``SUPPORTS_GOAL`` edges whose
    ``essentiality`` is ``"essential"``.
    """
    if spec.filter_property is None:
        return None
    return {spec.filter_property: spec.filter_value}


def far_end_label(spec: UnifiedRelationshipDefinition) -> NeoLabel | None:
    """The far end's kind, or ``None`` when the definition reads every kind.

    ``Entity`` names no kind: it is every domain node's base label, and labelling the
    far node with it would only drop the nodes outside it (a User, a Group).
    """
    label = NeoLabel(spec.target_label)
    return None if label is NeoLabel.ENTITY else label


def resolve_keyed_read(
    config: DomainRelationshipConfig, relationship_key: str
) -> Result[KeyedRead]:
    """Resolve a registry key into the read its definition describes.

    Refuses a key the config does not declare, and a shared-neighbour definition: its
    ``relationship`` is the first hop of a two-hop pattern, so a one-hop read of it
    would return the shared neighbours (the Kus), not the related peers it names.
    """
    spec = config.get_relationship_by_method(relationship_key)
    if spec is None:
        return Result.fail(
            Errors.validation(
                f"Unknown relationship key '{relationship_key}' for {config.entity_label}"
            )
        )
    if spec.shared_neighbor_config is not None:
        return Result.fail(
            Errors.validation(
                f"Relationship key '{relationship_key}' for {config.entity_label} is read "
                "through shared neighbours, not by a keyed read"
            )
        )
    return Result.ok(KeyedRead(spec, _edge_filter(spec), far_end_label(spec)))
