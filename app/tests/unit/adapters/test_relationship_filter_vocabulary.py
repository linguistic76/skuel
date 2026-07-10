"""
Smart-filter fragment vocabulary guard.

The Cypher fragments in ``relationship_filter_fragments.py`` are hand-authored
strings — nothing validates their edge types at runtime. The original
vocabulary included five edge types (PRACTICES, ADHERES_TO, EMBODIES_KNOWLEDGE,
ENABLES_LEARNING, PURSUING_GOAL-as-written) that no code path ever wrote,
silently turning six of the eleven /search Smart Filters into no-ops.

This guard fails closed: every relationship type referenced by any fragment
MUST be a registered ``RelationshipName`` value. Registration doesn't prove a
write path exists, but it blocks the original failure mode — inventing an edge
name wholesale.
"""

import re
from dataclasses import fields

from adapters.persistence.neo4j.query.cypher.relationship_filter_fragments import (
    build_relationship_filter_fragments,
)
from core.models.relationship_filters import RelationshipFilters
from core.models.relationship_names import RelationshipName

_EDGE_TOKEN = re.compile(r"\[\s*\w*\s*:([A-Z_0-9|]+)\]")


def _all_flags_on() -> RelationshipFilters:
    return RelationshipFilters(**{f.name: True for f in fields(RelationshipFilters)})


def test_every_flag_emits_a_fragment() -> None:
    filters = _all_flags_on()
    fragments = build_relationship_filter_fragments(filters)
    assert len(fragments) == len(fields(RelationshipFilters))


def test_fragment_edge_types_are_registered_relationship_names() -> None:
    fragments = build_relationship_filter_fragments(_all_flags_on())
    valid_values = {member.value for member in RelationshipName}

    used: set[str] = set()
    for fragment in fragments:
        for match in _EDGE_TOKEN.finditer(fragment):
            used.update(match.group(1).split("|"))

    assert used, "expected the fragments to reference at least one edge type"
    unregistered = sorted(used - valid_values)
    assert not unregistered, (
        f"Fragment(s) reference edge types missing from RelationshipName: {unregistered}. "
        "Either use a registered edge with a real write path, or add the new edge "
        "to core/models/relationship_names.py first."
    )


def test_no_fragment_uses_the_known_dead_vocabulary() -> None:
    """The five edges the 2026-07 audit found writer-less must never return."""
    dead = {"PRACTICES", "ADHERES_TO", "EMBODIES_KNOWLEDGE", "ENABLES_LEARNING", "PURSUING_GOAL"}
    fragments = build_relationship_filter_fragments(_all_flags_on())
    for fragment in fragments:
        for match in _EDGE_TOKEN.finditer(fragment):
            hit = dead & set(match.group(1).split("|"))
            assert not hit, f"dead edge vocabulary reintroduced: {sorted(hit)} in {fragment!r}"
