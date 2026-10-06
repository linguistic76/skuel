"""Search enrichment builds no one-hop pattern from a shared-neighbour definition.

A shared-neighbour definition's relationship type is a placeholder for a two-hop walk
(``(entity)-[:R]->(shared)<-[:R]-(related)``). ``generate_graph_enrichment`` builds
one-hop ``OPTIONAL MATCH`` patterns, so the placeholder would list the shared
neighbour itself — a goal, a principle, a Ku — under a "related" key: a choice's
``related_choices`` would hold the goals it affects. Every config's enrichment is
exactly its definitions that are not shared-neighbour ones.
"""

from __future__ import annotations

import pytest

from core.models.relationship_registry import LABEL_CONFIGS, generate_graph_enrichment

LABELS = sorted(LABEL_CONFIGS)
SHARED_NEIGHBOUR_LABELS = sorted(
    label
    for label, config in LABEL_CONFIGS.items()
    if any(rel.shared_neighbor_config is not None for rel in config.relationships)
)


def test_the_census_has_shared_neighbour_definitions_to_leave_out() -> None:
    """The premise: the parametrization below is not vacuous."""
    assert {"Choice", "Habit", "Principle"} <= set(SHARED_NEIGHBOUR_LABELS)


@pytest.mark.parametrize("label", LABELS)
def test_the_enrichment_is_every_definition_but_the_shared_neighbour_ones(label: str) -> None:
    config = LABEL_CONFIGS[label]

    assert generate_graph_enrichment(label) == [
        rel.to_graph_enrichment_tuple()
        for rel in config.relationships
        if rel.shared_neighbor_config is None
    ]


@pytest.mark.parametrize("label", SHARED_NEIGHBOUR_LABELS)
def test_no_shared_neighbour_context_field_is_enriched(label: str) -> None:
    shared = {
        rel.context_field_name
        for rel in LABEL_CONFIGS[label].relationships
        if rel.shared_neighbor_config is not None
    }

    enriched = {
        context_field for _type, _label, context_field, _dir in generate_graph_enrichment(label)
    }

    assert not shared & enriched, shared & enriched


def test_a_choices_enrichment_has_no_related_choices() -> None:
    assert "related_choices" not in {pattern[2] for pattern in generate_graph_enrichment("Choice")}


def test_a_choices_informers_are_enriched_by_kind() -> None:
    """The choice's two incoming INFORMS_CHOICE views each name their kind."""
    informers = {
        (target_label, context_field)
        for rel_type, target_label, context_field, direction in generate_graph_enrichment("Choice")
        if rel_type == "INFORMS_CHOICE" and direction == "incoming"
    }

    assert informers == {
        ("Principle", "informing_principles"),
        ("Habit", "informing_habits"),
    }
