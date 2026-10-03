"""Every parameter a generated context statement references is one it returns.

``generate_context_query`` assembles a statement from registry relationships a caller
may include one at a time. A predicate composed into any clause (confidence, an edge
filter, the far-node fragment's publication parameter) must hand its parameters back
with the statement, whichever subset of clauses was asked for — a statement that
references a parameter it does not return fails at run time with ``ParameterMissing``.
"""

from __future__ import annotations

import re

import pytest

from adapters.persistence.neo4j.query.cypher.context_query_generator import (
    generate_context_query,
    get_available_relationships,
)
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_registry import LABEL_CONFIGS

_PARAMETER = re.compile(r"\$(\w+)")
# The caller supplies the anchored uid (``context_query_raw``).
_CALLER_SUPPLIED = {"uid"}

# The registry also keys configs by names that are not Neo4j labels; the generator
# refuses those before it builds a statement, so there is nothing to measure.
_LABELS = [label for label in LABEL_CONFIGS if label in set(NeoLabel)]

_CASES = [
    pytest.param(label, field, id=f"{label}-{field}")
    for label in _LABELS
    for field in [None, *get_available_relationships(label)]
]


@pytest.mark.parametrize(("label", "field"), _CASES)
def test_statement_returns_every_parameter_it_references(
    label: NeoLabel, field: str | None
) -> None:
    query, params = generate_context_query(
        label, include_relationships=None if field is None else [field]
    )

    referenced = set(_PARAMETER.findall(query)) - _CALLER_SUPPLIED
    assert referenced - set(params) == set()


def test_a_shared_neighbour_clause_alone_carries_its_far_node_parameter() -> None:
    query, params = generate_context_query(NeoLabel.TASK, include_relationships=["related_tasks"])

    assert "related0" in query
    assert "$publication_draft" in query
    assert params["publication_draft"] == "draft"
