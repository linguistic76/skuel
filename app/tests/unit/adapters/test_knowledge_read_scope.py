"""Knowledge reads must mean KNOWLEDGE — not "every node in the graph".

Five queries named themselves after knowledge (``find_ready_to_learn``,
``find_knowledge_hubs``, …) while matching a bare ``(ku:Entity)``, which matches
EVERY entity type. On the live corpus ``find_ready_to_learn`` returned 370 rows
of which only 123 were Kus; 91 were tasks and 71 were UserEntries.

That made it a SECURITY defect rather than a tidy-up. The queries carry no
ownership predicate and project ``title``/``summary``, so one user's "what am I
ready to learn" handed back 24 of another user's 25 owned entities, by title —
crossing the line CLAUDE.md draws for UserEntry ("REQUIRES user_uid … refused
unscoped").

The guard is the same shape as the publication-gate suite: build each query for
real and assert the composed clause is present with its params threaded, since a
dropped param is a runtime error and an unbuilt f-string is a ValueError.
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.persistence.neo4j.query.cypher import (
    build_knowledge_read_clause,
    build_publication_clause,
)
from core.models.enums import EntityType, SearchVisibility
from core.utils.result_simplified import Result

# boundary: Neo4j params are heterogeneous; assertions here are on query text.
QueryParams = dict[str, Any]


class _Capture:
    """Records the (query, params) a backend method hands to its executor."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, QueryParams]] = []

    async def execute_query(
        self, query: str, params: QueryParams | None = None
    ) -> Result[list[QueryParams]]:
        self.calls.append((query, params or {}))
        return Result.ok([])


async def _capture(
    # boundary: a backend mixin CLASS built via __new__ to skip a driver-hungry
    # __init__; `type` does not describe that.
    cls: Any,
    method: str,
    *args: Any,
) -> tuple[str, QueryParams]:
    cap = _Capture()
    obj = cls.__new__(cls)
    obj.execute_query = cap.execute_query  # type: ignore[attr-defined]
    obj.executor = cap  # type: ignore[attr-defined]
    await getattr(obj, method)(*args)
    assert cap.calls, f"{cls.__name__}.{method} issued no query"
    return cap.calls[0]


def _assert_knowledge_scoped(query: str, params: QueryParams, alias: str) -> None:
    fragment, expected = build_knowledge_read_clause(alias)
    assert fragment in query, (
        f"expected the composed knowledge-read clause on alias {alias!r} — "
        f"compose build_knowledge_read_clause({alias!r}), never a hand-written "
        f"entity_type list.\nQuery was:\n{query}"
    )
    for key, value in expected.items():
        assert params.get(key) == value, (
            f"parameter {key!r} was not threaded (a dropped param is a runtime "
            f"error, not a silent no-op). Got: {sorted(params)}"
        )


def _knowledge_context() -> type:
    from adapters.persistence.neo4j._knowledge_context_mixin import _KnowledgeContextMixin

    return _KnowledgeContextMixin


def _semantic() -> type:
    from adapters.persistence.neo4j._semantic_mixin import _SemanticMixin

    return _SemanticMixin


def _cross_domain() -> type:
    from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend

    return CrossDomainBackend


KNOWLEDGE_READS: list[tuple[str, Any, str, tuple[Any, ...], str]] = [
    ("find_ready_to_learn", _knowledge_context, "find_ready_to_learn", ([], None, 5), "ku"),
    (
        "find_learning_recommendations",
        _knowledge_context,
        "find_learning_recommendations",
        ("u1", None, 5),
        "candidate",
    ),
    (
        "query_foundational_knowledge",
        _semantic,
        "query_foundational_knowledge",
        (None, 3, 5),
        "ku",
    ),
    ("compute_hub_scores", _semantic, "compute_hub_scores", (), "ku"),
    (
        "find_knowledge_hubs",
        _cross_domain,
        "find_knowledge_hubs",
        ("", {"min_confidence": 0.0, "min_connections": 1, "limit": 5}),
        "ku",
    ),
    (
        "find_learning_clusters",
        _cross_domain,
        "find_learning_clusters",
        ("", {"min_density": 0.0, "limit": 5}),
        "ku",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "factory", "method", "args", "alias"),
    KNOWLEDGE_READS,
    ids=[row[0] for row in KNOWLEDGE_READS],
)
async def test_knowledge_read_is_type_scoped(
    label: str, factory: Any, method: str, args: tuple[Any, ...], alias: str
) -> None:
    """Every knowledge-named query restricts to knowledge entity types."""
    query, params = await _capture(factory(), method, *args)
    _assert_knowledge_scoped(query, params, alias)


@pytest.mark.asyncio
async def test_ready_to_learn_scopes_prerequisites_too() -> None:
    """The prerequisite hop is a second projection, and leaks the same way.

    ``prereq_uids`` reaches the caller via ``blocking_reasons``, so it needs the
    same scope as the candidate — but the COUNT must still see every
    prerequisite, or readiness rises for a KU blocked by hidden work.
    """
    query, params = await _capture(_knowledge_context(), "find_ready_to_learn", [], None, 5)
    _assert_knowledge_scoped(query, params, "prereq")
    assert "all_prereq_uids" in query and "visible_prereq_uids" in query, (
        "the maths must read ALL prerequisites while only the returned list is "
        "filtered — collapsing the two would inflate readiness"
    )
    assert "size([p IN all_prereq_uids WHERE p IN $mastered_uids])" in query, (
        "satisfied_prereqs must be computed from the UNFILTERED list"
    )


def test_hub_score_writer_and_reader_share_the_scope() -> None:
    """Filtering the read alone would leave the score stamped on Tasks.

    ``compute_hub_scores`` WRITES ``hub_score``; ``query_foundational_knowledge``
    ranks by it. Scoping only the reader is half a fix — the pair moves together.
    """
    import inspect

    from adapters.persistence.neo4j import _semantic_mixin

    writer = inspect.getsource(_semantic_mixin._SemanticMixin.compute_hub_scores)
    reader = inspect.getsource(_semantic_mixin._SemanticMixin.query_foundational_knowledge)
    for name, src in (("writer", writer), ("reader", reader)):
        assert "build_knowledge_read_clause" in src, (
            f"the hub_score {name} must compose the knowledge scope"
        )


def test_knowledge_scope_is_sourced_from_the_enum() -> None:
    """One definition of "knowledge" — EntityType.is_knowledge(), not a literal list."""
    _, params = build_knowledge_read_clause("n")
    assert params["knowledge_entity_types"] == sorted(
        t.value for t in EntityType if t.is_knowledge()
    )
    # PathStep belongs here alongside Ku (ADR-046); Task plainly does not.
    assert EntityType.KU.value in params["knowledge_entity_types"]
    assert EntityType.PATH_STEP.value in params["knowledge_entity_types"]
    assert EntityType.TASK.value not in params["knowledge_entity_types"]
    assert EntityType.USER_ENTRY.value not in params["knowledge_entity_types"]


def test_knowledge_scope_carries_the_publication_gate() -> None:
    """Publication rides inside the visibility clause — no separate call to forget."""
    fragment, params = build_knowledge_read_clause("ku")
    published, published_params = build_publication_clause("ku")
    assert published in fragment
    assert published_params.items() <= params.items()


def test_knowledge_scope_delegates_audience_rather_than_hand_writing_it() -> None:
    """Ownership is EMPTY today because knowledge is PUBLIC — deliberately so.

    Composing the shared visibility mechanism (rather than skipping it because
    it currently adds nothing) is what makes a future change to curriculum
    visibility reach every caller without revisiting them.
    """
    from adapters.persistence.neo4j.query.cypher import build_search_visibility_clause

    visibility = build_search_visibility_clause(
        SearchVisibility.PUBLIC, entity_alias="ku", has_user=False
    )
    assert visibility is not None
    fragment, _ = visibility
    assert fragment in build_knowledge_read_clause("ku")[0]
