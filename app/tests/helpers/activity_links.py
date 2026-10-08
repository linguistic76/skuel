"""The Activity links the relationship registry declares — derived, never hand-listed.

ADR-090 §1 and §2. Shared by the invariant (tests/unit/test_activity_link_invariant.py)
and the page tests (tests/integration/routes/test_activity_page_links.py), so the
pairs a page test walks are exactly the links the invariant checks.

Each config is read once (``Lesson`` / ``Ls`` / ``Lp`` are aliases of the PathStep and
LearningPath configs), curriculum configs included: they are what gives an edge type
more than one kind of source. A shared-neighbour definition (its type is a
placeholder), a ``both`` definition and a lateral type (their own system) are not
views of a link and are left out.
"""

from collections.abc import Mapping
from typing import NamedTuple

from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import (
    LABEL_CONFIGS,
    DomainRelationshipConfig,
    UnifiedRelationshipDefinition,
)

ACTIVITY_LABELS = frozenset(
    NeoLabel.from_entity_type(entity_type)
    for entity_type in EntityType
    if entity_type.is_activity()
)

Declaration = tuple[NeoLabel, UnifiedRelationshipDefinition]


class Link(NamedTuple):
    """An edge type joining two labels, as the registry declares it."""

    source: NeoLabel
    edge: RelationshipName
    target: NeoLabel


def configs(
    label_configs: Mapping[str, DomainRelationshipConfig],
) -> dict[NeoLabel, DomainRelationshipConfig]:
    """Each config once, under the first label it is registered with."""
    found: dict[NeoLabel, DomainRelationshipConfig] = {}
    for label, config in label_configs.items():
        if not any(config is seen for seen in found.values()):
            found[NeoLabel(label)] = config
    return found


def declarations(label_configs: Mapping[str, DomainRelationshipConfig]) -> list[Declaration]:
    """Every definition that is a view of a link, with its config's label."""
    return [
        (label, definition)
        for label, config in configs(label_configs).items()
        for definition in config.relationships
        if definition.shared_neighbor_config is None
        and definition.direction != "both"
        and not definition.relationship.is_lateral_relationship()
    ]


def far_ends(
    definition: UnifiedRelationshipDefinition, declared: list[Declaration]
) -> set[NeoLabel]:
    """The labels a definition's far end stands for: its own, or each opposite declarer's."""
    far_end = NeoLabel(definition.target_label)
    if far_end != NeoLabel.ENTITY:
        return {far_end}
    opposite = "incoming" if definition.direction == "outgoing" else "outgoing"
    return {
        label
        for label, other in declared
        if other.relationship == definition.relationship and other.direction == opposite
    }


def links(declared: list[Declaration]) -> set[Link]:
    found: set[Link] = set()
    for label, definition in declared:
        for far_end in far_ends(definition, declared):
            if definition.direction == "outgoing":
                found.add(Link(label, definition.relationship, far_end))
            else:
                found.add(Link(far_end, definition.relationship, label))
    return found


def views_of(
    declared: list[Declaration],
    at: NeoLabel,
    direction: str,
    edge: RelationshipName,
    far_end: NeoLabel,
) -> list[UnifiedRelationshipDefinition]:
    """``at``'s unfiltered views of ``edge`` toward ``far_end``.

    A view filtered on an edge property (a tier view such as ``essential_habits``)
    lists only the edges that carry its value, so it does not read the link.
    """
    return [
        definition
        for label, definition in declared
        if label == at
        and definition.direction == direction
        and definition.relationship == edge
        and definition.target_label in (far_end, NeoLabel.ENTITY)
        and definition.filter_property is None
    ]


def reads(
    declared: list[Declaration],
    at: NeoLabel,
    direction: str,
    edge: RelationshipName,
    far_end: NeoLabel,
) -> bool:
    """Whether ``at`` holds an unfiltered view of ``edge`` toward ``far_end``."""
    return bool(views_of(declared, at, direction, edge, far_end))


def shows(
    declared: list[Declaration],
    at: NeoLabel,
    direction: str,
    edge: RelationshipName,
    far_end: NeoLabel,
) -> bool:
    """Whether ``at``'s page shows the link: one of its views of it carries a heading."""
    return any(
        definition.page_heading is not None
        for definition in views_of(declared, at, direction, edge, far_end)
    )


def activity_links(label_configs: Mapping[str, DomainRelationshipConfig]) -> set[Link]:
    """Every edge type joining two DIFFERENT Activity domains (same-type: R8, later)."""
    return {
        link
        for link in links(declarations(label_configs))
        if link.source != link.target and {link.source, link.target} <= ACTIVITY_LABELS
    }


def links_read_at_both_ends(
    label_configs: Mapping[str, DomainRelationshipConfig] = LABEL_CONFIGS,
) -> list[Link]:
    """The Activity links both ends read, sorted — the page tests' pair list."""
    declared = declarations(label_configs)
    return sorted(
        link
        for link in activity_links(label_configs)
        if reads(declared, link.source, "outgoing", link.edge, link.target)
        and reads(declared, link.target, "incoming", link.edge, link.source)
    )


def heading_at(
    at: NeoLabel,
    direction: str,
    edge: RelationshipName,
    far_end: NeoLabel,
    label_configs: Mapping[str, DomainRelationshipConfig] = LABEL_CONFIGS,
) -> str:
    """The heading ``at``'s page shows the link under (the first headed view of it)."""
    for definition in views_of(declarations(label_configs), at, direction, edge, far_end):
        if definition.page_heading is not None:
            return definition.page_heading
    raise AssertionError(f"{at} shows no {direction} {edge} toward {far_end}")


def undeclared_edge(index: int = 0) -> RelationshipName:
    """An edge type no config declares — a control built on it cannot be moved by a later PR.

    ``index`` picks another such type, for a control that needs two different ones.
    """
    declared = {
        definition.relationship
        for config in LABEL_CONFIGS.values()
        for definition in config.relationships
    }
    return [
        edge
        for edge in RelationshipName
        if edge not in declared and not edge.is_lateral_relationship()
    ][index]
