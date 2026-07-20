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
    unregistered = sorted(used - valid_values)
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


def test_dead_preference_vocabulary_never_returns() -> None:
    """HAS_PREFERENCE was writer-less too — its read went in SKUEL030 tranche 3.

    It used to sit in a known-unregistered exemption set here; the exemption is
    gone with the query, so the module now has to be fully registered.
    """
    assert "HAS_PREFERENCE" not in _module_edge_tokens()
