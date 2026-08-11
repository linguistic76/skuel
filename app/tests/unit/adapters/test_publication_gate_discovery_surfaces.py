"""Publication-gate coverage for every curriculum DISCOVERY surface.

Follow-up to PR #1006, which gated nine surfaces reactively — four Codex rounds
each surfaced a new one. This module pins the CLOSED set: each surface below
was classified against the #1006 criterion ("does this let a user FIND
curriculum they did not already reference?") and gated.

Why these tests execute the query BUILDER rather than asserting on a constant
string: #1006 shipped ``find_similar_knowledge`` as an f-string whose
pre-existing Cypher map literal ``{uid: $uid}`` was never escaped. Python reads
that as a format field and raises ``ValueError: Invalid format specifier`` — on
EVERY call. It survived 8485 unit tests, full mypy and three Codex rounds
because nothing ever executed the line that builds the string.

So the guard here is: build each query for real, then assert the gate is in the
built text AND that the parameter it introduces was threaded. A dropped param
is a runtime error the same way; both failure modes are invisible to a test
that only inspects a module-level constant.

Cypher SYNTAX (as opposed to Python string construction) is covered against a
live database in tests/integration/ — `RETURN DISTINCT lp.uid ... ORDER BY
lp.created_at` is valid Python and invalid Cypher, and that one shipped too.
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.persistence.neo4j.query.cypher import build_publication_clause
from core.models.enums.curriculum_enums import PublicationState
from core.utils.result_simplified import Result

# boundary: Neo4j record rows are genuinely heterogeneous property maps; the
# assertions here are on the QUERY TEXT and its params, never on row shape.
QueryParams = dict[str, Any]


def _identity(records: object) -> object:
    """Stand-in for the backends' record→model converters (SKUEL012: no lambdas).

    These tests assert on the query, so conversion is irrelevant — but the
    methods call it, so the slot must be filled.
    """
    return records


class _Capture:
    """Stands in for the backend's query executor, recording what it is handed."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, QueryParams]] = []

    async def execute_query(
        self, query: str, params: QueryParams | None = None
    ) -> Result[list[QueryParams]]:
        self.calls.append((query, params or {}))
        return Result.ok([])


async def _capture(
    # boundary: a backend mixin CLASS, constructed via __new__ to skip an
    # __init__ that demands a live driver. `type` does not describe that.
    cls: Any,
    method: str,
    # boundary: per-surface query arguments — uids, limits, filter fragments.
    *args: Any,
) -> tuple[str, QueryParams]:
    """Build (not run) one backend query; return its Cypher and parameters."""
    cap = _Capture()
    obj = cls.__new__(cls)  # bypasses __init__ — no driver needed to BUILD a query
    obj.execute_query = cap.execute_query  # type: ignore[attr-defined]
    obj.executor = cap  # type: ignore[attr-defined]
    obj._records_to_paths = _identity  # type: ignore[attr-defined]
    obj._records_to_steps = _identity  # type: ignore[attr-defined]
    await getattr(obj, method)(*args)
    assert cap.calls, f"{cls.__name__}.{method} issued no query"
    return cap.calls[0]


def _assert_gated(query: str, params: QueryParams, alias: str) -> None:
    """The composed predicate must be present verbatim, and its param threaded."""
    fragment, expected = build_publication_clause(alias)
    assert fragment in query, (
        f"expected the composed publication clause on alias {alias!r}.\n"
        f"Hand-written equivalents are not accepted — compose "
        f"build_publication_clause({alias!r}).\nQuery was:\n{query}"
    )
    for key, value in expected.items():
        assert params.get(key) == value, (
            f"parameter {key!r} was not threaded into the query params "
            f"(a dropped param is a runtime error, not a silent no-op). "
            f"Got: {sorted(params)}"
        )


def _lp_progress() -> type:
    from adapters.persistence.neo4j._lp_progress_mixin import _LpProgressMixin

    return _LpProgressMixin


def _knowledge_context() -> type:
    from adapters.persistence.neo4j._knowledge_context_mixin import _KnowledgeContextMixin

    return _KnowledgeContextMixin


# (label, class factory, method, args, gated alias)
DISCOVERY_SURFACES: list[tuple[str, Any, str, tuple[Any, ...], str]] = [
    ("get_paths_aligned_with_goal", _lp_progress, "get_paths_aligned_with_goal", ("g1", 5), "lp"),
    ("get_paths_by_knowledge", _lp_progress, "get_paths_by_knowledge", ("ku.x", 5), "lp"),
    ("get_user_paths_prioritized", _lp_progress, "get_user_paths_prioritized", ("u1", 5), "lp"),
    (
        "find_path_steps_containing_ku",
        _knowledge_context,
        "find_path_steps_containing_ku",
        ("ku.x", 5),
        "ps",
    ),
    (
        "find_learning_paths_teaching_ku",
        _knowledge_context,
        "find_learning_paths_teaching_ku",
        ("ku.x", 5),
        "lp",
    ),
    ("find_ready_to_learn", _knowledge_context, "find_ready_to_learn", ([], None, 5), "ku"),
    ("find_learning_gaps", _knowledge_context, "find_learning_gaps", (["g1"], [], 5), "ku"),
    (
        "find_learning_recommendations",
        _knowledge_context,
        "find_learning_recommendations",
        ("u1", None, 5),
        "candidate",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "factory", "method", "args", "alias"),
    DISCOVERY_SURFACES,
    ids=[row[0] for row in DISCOVERY_SURFACES],
)
async def test_discovery_surface_is_publication_gated(
    label: str, factory: Any, method: str, args: tuple[Any, ...], alias: str
) -> None:
    """Each classified discovery surface composes the gate and threads its param."""
    query, params = await _capture(factory(), method, *args)
    _assert_gated(query, params, alias)


@pytest.mark.asyncio
async def test_ku_to_path_surfaces_gate_the_bridging_step_too() -> None:
    """ "This path teaches that KU" is a claim carried by the bridging STEP.

    Both KU→path surfaces walk `ku <- ps <- lp`. Gating only `lp` would still
    advertise a published path whose ONLY route to the KU is a draft step —
    true of lp.mindfulness-101 for six KUs on the live graph (Codex P1, #1008).
    """
    query, params = await _capture(_lp_progress(), "get_paths_by_knowledge", "ku.x", 5)
    for alias in ("ps", "lp"):
        _assert_gated(query, params, alias)

    query, params = await _capture(
        _knowledge_context(), "find_learning_paths_teaching_ku", "ku.x", 5
    )
    for alias in ("ps", "lp"):
        _assert_gated(query, params, alias)

    # The third sibling hid the pattern behind an anonymous `(:Entity)` bridge
    # (Codex round 2, #1008). Its HAS_STEP arm is gated; its direct
    # REQUIRES_KNOWLEDGE arm has no bridge and must stay ungated on the step.
    from adapters.persistence.neo4j.backends.curriculum_backends import KuBackend

    query, params = await _capture(KuBackend, "get_learning_path_uids", "ku.x")
    for alias in ("step", "lp"):
        _assert_gated(query, params, alias)
    assert "HAS_STEP]->(:" not in query, (
        "the bridging step must be NAMED so it can be gated — an anonymous "
        "`(:Entity)` bridge is how this arm escaped the first fix"
    )


@pytest.mark.asyncio
async def test_ku_lateral_edges_gates_the_far_end_only() -> None:
    """Either endpoint may be the anchor, so the gate is 'held OR published'.

    Gating both ends unconditionally would hide a draft KU's own edges from the
    author who asked for them by UID — the carve-out get_visible_to_user makes.
    """
    query, params = await _capture(_knowledge_context(), "get_ku_lateral_edges", ["ku.x"], 5)
    for alias in ("a", "b"):
        _assert_gated(query, params, alias)
        fragment, _ = build_publication_clause(alias)
        assert f"({alias}.uid IN $ku_uids OR {fragment})" in query, (
            f"alias {alias!r} must be gated only when it is NOT the anchor"
        )


def test_zone_query_substitutes_the_publication_sentinel() -> None:
    """The ZPD proximal zone is a recommendation — the purest discovery surface.

    The zone query is a plain-string template with sentinel substitution (17
    Cypher brace pairs make f-strings error-prone), so the risk here is a
    sentinel that never gets replaced and ships as literal text.
    """
    from adapters.persistence.neo4j.zpd_backend import _ZONE_QUERY, _ZONE_QUERY_PARAMS

    assert "zpd_publication_gate" not in _ZONE_QUERY, (
        "the publication sentinel was never substituted — it would ship as "
        "literal Cypher text and fail at runtime"
    )
    fragment, expected = build_publication_clause("cand")
    assert fragment in _ZONE_QUERY
    assert expected == _ZONE_QUERY_PARAMS


def test_zone_query_gates_proximal_but_not_the_current_zone() -> None:
    """Only the PROXIMAL zone is discovery; the current zone is user-state.

    The current zone is what the user has already engaged — withholding a draft
    from it would erase their own history, not hide unfinished curriculum.
    """
    from adapters.persistence.neo4j.zpd_backend import _ZONE_QUERY

    body = "\n".join(line for line in _ZONE_QUERY.splitlines() if not line.strip().startswith("//"))
    # Anchor on executable Cypher, not on comment prose: the step headings are
    # all `//` lines and get stripped, so they cannot delimit anything here.
    dedup = body.index("CALL (candidate_uids_raw")
    assert "publication_state" not in body[:dedup], (
        "the gate must not appear before the proximal dedup subquery — "
        "the current zone is what the user has ALREADY engaged (user-state), "
        "and gating it would erase their own history"
    )
    assert body.count("publication_state") == 2, (
        "expected exactly the two references of one composed clause "
        "(IS NULL / <> $publication_draft), inside the dedup subquery"
    )


@pytest.mark.asyncio
async def test_cross_domain_discovery_surfaces_build_and_gate() -> None:
    """The three CrossDomainBackend surfaces, including the one #1006 broke.

    ``find_similar_knowledge`` is the regression anchor: merely CALLING it
    raised ValueError before this change, because the f-string #1006 introduced
    left a Cypher map literal unescaped. Building it here is the whole point.
    """
    from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend

    hub_params = {"min_confidence": 0.0, "min_connections": 1, "limit": 5}
    query, params = await _capture(CrossDomainBackend, "find_knowledge_hubs", "", dict(hub_params))
    _assert_gated(query, params, "ku")

    # The caller-supplied domain_filter may already carry a WHERE; the gate must
    # survive both shapes rather than colliding with it.
    query, params = await _capture(
        CrossDomainBackend,
        "find_knowledge_hubs",
        "WHERE ku.domain = $domain",
        {**hub_params, "domain": "sel"},
    )
    _assert_gated(query, params, "ku")

    query, params = await _capture(
        CrossDomainBackend, "find_learning_clusters", "", {"min_density": 0.0, "limit": 5}
    )
    _assert_gated(query, params, "ku")

    query, params = await _capture(CrossDomainBackend, "find_similar_knowledge", "ku.x", 0.1, 5)
    _assert_gated(query, params, "ku2")
    assert "{uid: $uid}" in query, (
        "the Cypher map literal must survive f-string formatting intact — "
        "an unescaped brace here is a ValueError on every call"
    )


@pytest.mark.asyncio
async def test_curriculum_catalogue_surfaces_are_gated() -> None:
    """The PathStep/Ku catalogue and search surfaces on the curriculum backends."""
    from adapters.persistence.neo4j.backends.curriculum_backends import KuBackend, PsBackend

    query, params = await _capture(PsBackend, "get_standalone_steps", 5)
    _assert_gated(query, params, "ps")

    query, params = await _capture(PsBackend, "get_prioritized_steps", "u1", 5)
    _assert_gated(query, params, "ps")

    query, params = await _capture(KuBackend, "search_by_alias", "x")
    _assert_gated(query, params, "ku")

    query, params = await _capture(KuBackend, "get_learning_path_uids", "ku.x")
    _assert_gated(query, params, "lp")


def test_publication_clause_is_null_tolerant() -> None:
    """Load-bearing: ingestion never writes absent frontmatter keys.

    The entire pre-publication_state corpus carries no such property, so a bare
    `= 'published'` test would hide every node. Withhold only explicit drafts.
    """
    fragment, params = build_publication_clause("n")
    assert "IS NULL" in fragment
    assert "<>" in fragment and "=" not in fragment.replace("<>", "")
    assert params == {"publication_draft": PublicationState.DRAFT.value}
