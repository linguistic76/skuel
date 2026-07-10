"""
Adaptive-mixin Cypher vocabulary guard.

The queries in ``_adaptive_mixin.py`` are hand-authored strings — nothing
validates their edge types at runtime. The original practice read matched
``(Event)-[:PRACTICES]->(ku)``, an edge no code path ever wrote (2026-07-10
writer audit), so every event completion silently found zero KUs to practice.

Same failure mode and same guard shape as the Smart-Filter fragments
(``test_relationship_filter_vocabulary.py``): every edge type referenced by
the module MUST be a registered ``RelationshipName`` value, and the known-dead
vocabulary must never return. Registration doesn't prove a write path exists,
but it blocks inventing an edge name wholesale.
"""

import inspect
import re

from adapters.persistence.neo4j import _adaptive_mixin
from core.models.relationship_names import RelationshipName

_EDGE_TOKEN = re.compile(r"\[\s*\w*\s*:([A-Z_0-9|]+)\]")

# HAS_PREFERENCE (query_learning_preferences) predates the RelationshipName
# registry and has no writer either — a separate pre-existing gap, tracked
# outside this guard so it doesn't mask NEW unregistered vocabulary.
_KNOWN_UNREGISTERED = {"HAS_PREFERENCE"}


def _module_edge_tokens() -> set[str]:
    source = inspect.getsource(_adaptive_mixin)
    used: set[str] = set()
    for match in _EDGE_TOKEN.finditer(source):
        used.update(match.group(1).split("|"))
    return used


def test_edge_types_are_registered_relationship_names() -> None:
    used = _module_edge_tokens()
    assert used, "expected the adaptive mixin to reference at least one edge type"

    valid_values = {member.value for member in RelationshipName}
    unregistered = sorted(used - valid_values - _KNOWN_UNREGISTERED)
    assert not unregistered, (
        f"_adaptive_mixin references edge types missing from RelationshipName: {unregistered}. "
        "Either use a registered edge with a real write path, or add the new edge "
        "to core/models/relationship_names.py first."
    )


def test_practice_read_uses_the_canonical_event_ku_edge() -> None:
    """The practice read must match the edge the Event writers actually write."""
    source = inspect.getsource(_adaptive_mixin._AdaptiveMixin.find_kus_practiced_by_event)
    assert RelationshipName.APPLIES_KNOWLEDGE.value in source


def test_dead_practices_vocabulary_never_returns() -> None:
    """PRACTICES was writer-less (2026-07-10 audit) — it must never come back."""
    assert "PRACTICES" not in _module_edge_tokens()
