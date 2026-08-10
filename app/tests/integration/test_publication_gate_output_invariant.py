"""The publication gate, measured at the OUTPUT rather than in the query text.

**Why this exists alongside the unit-level gate tests.** ``publication_state``
has been applied per-surface three times, and each pass was enumerated by hand
(#1006 → four Codex rounds; #1008 → sixteen more surfaces, then six further
defects across three rounds). Categorising those last six is what shaped this
module: three were surfaces the census never SAW, and three were surfaces it saw
and classified WRONGLY —

* the wrong alias: ``get_paths_by_knowledge`` gated ``lp`` and not the bridging
  ``ps``, so a published path reachable only through a draft step still
  advertised the KU it "teaches";
* the wrong half: ``get_prioritized_steps`` gated a mixed catalogue/user-state
  surface without yielding to the learner's own progress;
* the wrong channel: ``find_ready_to_learn`` withheld the draft node and then
  named its uid inside a ``collect()``.

The existing unit guard asserts ``build_publication_clause(alias)``'s fragment
is a SUBSTRING of the built query. That is a proxy, and it cannot express any of
the three: it does not know which alias carries the claim, where in the query
the predicate landed, or whether an identity escaped through a collected list.
The matched pair in ``_knowledge_context_mixin`` makes the point exactly —
``find_ready_to_learn`` and ``find_learning_gaps`` both ``collect(prereq.uid)``,
one leaked and one never did, and the only difference is whether that list
appears in the ``RETURN``.

So the criterion here is the invariant itself: **no draft IDENTITY reaches the
caller**, checked by walking the returned structure to any depth. It is
indifferent to how the query is written, which is what makes it survive an
unlabelled binding, an anonymous bridge, or a gate buried in a ``CASE WHEN``.

Identity, specifically — not "no draft influenced this result". A withheld
prerequisite still COUNTS in ``find_ready_to_learn``; dropping it from the count
would raise readiness and recommend a blocked KU as more ready. Arithmetic sees
every prerequisite; only the returned list is filtered.

**Every gated surface is asserted in BOTH directions.** With the gate composed,
no draft identity may appear. With the predicate neutralised to ``true`` — same
code path, same params, same query shape — the surface MUST leak. Without that
second half a fixture that returns no rows passes silently, and a gate with zero
measured effect is unproven rather than verified. Surfaces whose leak cannot be
measured this way are listed in ``UNMEASURABLE`` with the reason, never omitted.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol, runtime_checkable

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.persistence.neo4j.backends.curriculum_backends import KuBackend, LpBackend, PsBackend
from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.enums.neo_labels import NeoLabel
from core.models.ku.ku import Ku
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.path_step import PathStep
from core.utils.result_simplified import Result

# Sibling-module import: scripts/ has no __init__.py and tests/unit/scripts/
# shadows the name under pytest, so a package-qualified import is not stable
# across a full-suite run.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from publication_gate_registry import (  # type: ignore[import-not-found]
    SURFACES,
    Disposition,
    gated_surfaces,
)

# No module-level asyncio mark: two of these tests are sync (they assert on the
# registry, not the graph), and a blanket mark makes pytest warn on each.

# --------------------------------------------------------------------------
# Fixture corpus.
#
# `publication_state` is ABSENT on the published nodes rather than set to
# 'published'. That is the load-bearing case: ingestion never writes absent
# frontmatter keys, so the entire pre-publication_state corpus carries no such
# property and a bare `= 'published'` test would hide all of it. Setting the
# property on the published half would make a broken NULL-tolerant predicate
# pass here while hiding the real corpus in production.
# --------------------------------------------------------------------------
USER = "user_gate_probe"
GOAL = "goal.gate-probe"

LP_PUBLISHED = "lp.gate-published"  # no publication_state — the NULL-tolerant case
LP_DRAFT = "lp.gate-draft"
STEP_PUBLISHED = "ps.gate-published-step"
STEP_DRAFT = "ps.gate-draft-step"  # inside the PUBLISHED path
STEP_STANDALONE_DRAFT = "ps.gate-standalone-draft"
KU_VIA_DRAFT_ONLY = "ku.gate-only-via-draft"  # reachable only through STEP_DRAFT
KU_SHARED = "ku.gate-shared"  # reachable through both steps
KU_DRAFT = "ku.gate-draft"
# Drafts the learner has ALREADY engaged. The mixed catalogue/user-state
# surfaces must keep showing these — the gate yields to progress, so a draft is
# UNLISTED, not forbidden. Without them both mixed surfaces exercise only their
# catalogue branch, and a gate made unconditional (erasing a learner's own
# progress) would still pass every other assertion here (Codex P2, #1012).
STEP_DRAFT_IN_PROGRESS = "ps.gate-draft-in-progress"
LP_DRAFT_ENROLLED = "lp.gate-draft-enrolled"

# A published bridge concept plus a DRAFT neighbour in a different domain:
# discover_semantic_bridges requires source.domain <> target.domain and the
# same relationship type on both hops, so a single-domain corpus measures it
# not at all.
KU_BRIDGE = "ku.gate-bridge"
KU_FAR_DRAFT = "ku.gate-far-draft"

DRAFT_UIDS = frozenset(
    {
        LP_DRAFT,
        STEP_DRAFT,
        STEP_STANDALONE_DRAFT,
        KU_DRAFT,
        KU_FAR_DRAFT,
        STEP_DRAFT_IN_PROGRESS,
        LP_DRAFT_ENROLLED,
    }
)

USER_STATE_EXEMPT: dict[tuple[str, str], frozenset[str]] = {
    (
        "adapters.persistence.neo4j.backends.curriculum_backends",
        "PsBackend.get_prioritized_steps",
    ): frozenset({STEP_DRAFT_IN_PROGRESS}),
    (
        "adapters.persistence.neo4j._lp_progress_mixin",
        "_LpProgressMixin.get_user_paths_prioritized",
    ): frozenset({LP_DRAFT_ENROLLED}),
}
"""Drafts a given surface may legitimately return, because the learner holds them.

Kept as a per-surface allowance rather than by dropping these uids from
DRAFT_UIDS: every OTHER surface must still withhold them, and a blanket
exclusion would silently stop checking that."""

SEED = """
CREATE (u:User {uid: $user, username: 'gate-probe'})
CREATE (g:Goal:Entity {uid: $goal, entity_type: 'goal', title: 'Gate probe goal',
                       user_uid: $user})

CREATE (lp_pub:Entity:LearningPath {uid: $lp_published, entity_type: 'learning_path',
                                    title: 'Published path', created_at: '2026-01-01'})
CREATE (lp_draft:Entity:LearningPath {uid: $lp_draft, entity_type: 'learning_path',
                                      title: 'Draft path', created_at: '2026-01-02',
                                      publication_state: 'draft'})

CREATE (s_pub:Entity:PathStep {uid: $step_published, entity_type: 'path_step',
                               title: 'Published step', sequence: 1,
                               created_at: '2026-01-01'})
CREATE (s_draft:Entity:PathStep {uid: $step_draft, entity_type: 'path_step',
                                 title: 'Draft step', sequence: 2,
                                 created_at: '2026-01-02', publication_state: 'draft'})
CREATE (s_alone:Entity:PathStep {uid: $step_standalone_draft, entity_type: 'path_step',
                                 title: 'Standalone draft step', sequence: 1,
                                 created_at: '2026-01-03', publication_state: 'draft'})

// `aliases` is populated because search_by_alias matches on it; without the
// property the query returns nothing and its gate cannot be measured at all.
CREATE (ku_draft_only:Entity:Ku {uid: $ku_via_draft_only, entity_type: 'ku',
                                 title: 'Reachable only via a draft step',
                                 domain: 'probe', created_at: '2026-01-01',
                                 aliases: ['gate probe draft-only']})
CREATE (ku_shared:Entity:Ku {uid: $ku_shared, entity_type: 'ku', title: 'Shared KU',
                             domain: 'probe', created_at: '2026-01-01',
                             aliases: ['gate probe shared']})
CREATE (ku_d:Entity:Ku {uid: $ku_draft, entity_type: 'ku', title: 'Draft KU',
                        domain: 'probe', created_at: '2026-01-01',
                        publication_state: 'draft',
                        aliases: ['gate probe draft']})

CREATE (lp_pub)-[:HAS_STEP]->(s_pub)
CREATE (lp_pub)-[:HAS_STEP]->(s_draft)
CREATE (lp_draft)-[:HAS_STEP]->(s_pub)

CREATE (s_draft)-[:USES_KU]->(ku_draft_only)
CREATE (s_draft)-[:USES_KU]->(ku_shared)
CREATE (s_pub)-[:USES_KU]->(ku_shared)
CREATE (s_pub)-[:CONTAINS_KNOWLEDGE]->(ku_shared)
CREATE (s_draft)-[:CONTAINS_KNOWLEDGE]->(ku_draft_only)

CREATE (ku_bridge:Entity:Ku {uid: $ku_bridge, entity_type: 'ku', title: 'Bridge concept',
                             domain: 'probe', created_at: '2026-01-01',
                             aliases: ['gate probe bridge']})
CREATE (ku_far:Entity:Ku {uid: $ku_far_draft, entity_type: 'ku', title: 'Far draft KU',
                          domain: 'probe-far', created_at: '2026-01-01',
                          publication_state: 'draft', aliases: ['gate probe far']})
CREATE (ku_shared)-[:RELATED_TO {confidence: 0.9}]->(ku_bridge)
CREATE (ku_far)-[:RELATED_TO {confidence: 0.9}]->(ku_bridge)

// find_learning_recommendations opens on the user's MASTERED set; with no
// such edge the first MATCH yields nothing and the whole query is empty.
CREATE (u)-[:MASTERED]->(ku_shared)

// Engaged drafts: the gate must yield to the learner's own progress/enrolment.
CREATE (s_prog:Entity:PathStep {uid: $step_draft_in_progress, entity_type: 'path_step',
                                title: 'Draft step already started', sequence: 3,
                                created_at: '2026-01-04', publication_state: 'draft'})
CREATE (lp_enrolled:Entity:LearningPath {uid: $lp_draft_enrolled,
                                         entity_type: 'learning_path',
                                         title: 'Draft path already joined',
                                         created_at: '2026-01-04',
                                         publication_state: 'draft'})
CREATE (u)-[:IN_PROGRESS]->(s_prog)
CREATE (u)-[:ENROLLED_IN]->(lp_enrolled)

CREATE (ku_shared)-[:RELATED_TO {confidence: 0.9}]->(ku_d)
CREATE (ku_shared)-[:RELATED_TO {confidence: 0.9}]->(ku_draft_only)
CREATE (ku_d)-[:PREREQUISITE_FOR]->(ku_shared)

CREATE (g)-[:REQUIRES_KNOWLEDGE]->(ku_shared)
CREATE (g)-[:REQUIRES_KNOWLEDGE]->(ku_d)
CREATE (lp_pub)-[:ALIGNED_WITH_GOAL]->(g)
CREATE (lp_draft)-[:ALIGNED_WITH_GOAL]->(g)
"""

SEED_PARAMS = {
    "user": USER,
    "goal": GOAL,
    "lp_published": LP_PUBLISHED,
    "lp_draft": LP_DRAFT,
    "step_published": STEP_PUBLISHED,
    "step_draft": STEP_DRAFT,
    "step_standalone_draft": STEP_STANDALONE_DRAFT,
    "ku_via_draft_only": KU_VIA_DRAFT_ONLY,
    "ku_shared": KU_SHARED,
    "ku_draft": KU_DRAFT,
    "ku_bridge": KU_BRIDGE,
    "step_draft_in_progress": STEP_DRAFT_IN_PROGRESS,
    "lp_draft_enrolled": LP_DRAFT_ENROLLED,
    "ku_far_draft": KU_FAR_DRAFT,
}

# A limit far above the fixture corpus: a small LIMIT masks the delta, because
# the withheld rows fall off the end either way.
LIMIT = 500


# Modules that resolve `build_publication_clause` from their own globals at call
# time. The neutralising control patches each one — patching only the defining
# module would miss every `from ... import` binding, which is all of them.
@runtime_checkable
class _HasUid(Protocol):
    """Anything carrying an entity identity.

    A Protocol rather than ``hasattr`` (SKUEL011): the walkers below meet
    PathStep, LearningPath and Ku as typed models, plus raw property maps, and
    an attribute probe would narrow none of them for the type checker.
    """

    @property
    def uid(self) -> str: ...


# boundary: a Neo4j row is a genuinely heterogeneous property map, and these
# surfaces return nodes, scalars, and nested lists of both. Naming a concrete
# union here would be a fiction — the whole point of the walker is that it does
# not know the shape in advance.
Payload = Any

ClauseBuilder = Callable[..., tuple[str, dict[str, str]]]
"""The shape of ``build_publication_clause`` — what the control swaps out."""

SurfaceCall = Callable[[], Awaitable[Result[Any]]]
"""A gated surface bound to its arguments: zero-arg, returns a ``Result``."""

GATE_ATTR = "build_publication_clause"

GATE_CONSUMERS = (
    "adapters.persistence.neo4j.backends.curriculum_backends",
    "adapters.persistence.neo4j._knowledge_context_mixin",
    "adapters.persistence.neo4j._lp_progress_mixin",
    "adapters.persistence.neo4j._lp_intelligence_mixin",
    "adapters.persistence.neo4j._lp_step_mixin",
    "adapters.persistence.neo4j._organizes_mixin",
    "adapters.persistence.neo4j._semantic_mixin",
    "adapters.persistence.neo4j.cross_domain_backend",
    "adapters.persistence.neo4j.vector_search_backend",
    "adapters.persistence.neo4j.query.cypher.crud_queries",
)


def _neutralised_clause(entity_alias: str = "n") -> tuple[str, dict[str, str]]:
    """The gate's shape with none of its effect.

    Replacing the PREDICATE rather than removing the call keeps the code path,
    the param threading and the query shape identical, so a before/after diff
    measures the gate and nothing else.
    """
    return ("true", {"publication_draft": "draft"})


@contextmanager
def neutralised_gates() -> Iterator[None]:
    """Swap every publication predicate for ``true`` inside the block.

    A context manager rather than a fixture so one test can measure the SAME
    surface both ways; comparing across two tests would depend on ordering and
    on module-level state surviving between them.
    """
    from adapters.persistence.neo4j.query.cypher import crud_queries

    # getattr/setattr rather than attribute syntax: these are ModuleType handles
    # from importlib, so the binding is invisible to the type checker.
    originals: list[tuple[ModuleType, ClauseBuilder]] = []
    for name in GATE_CONSUMERS:
        module = importlib.import_module(name)
        original = getattr(module, GATE_ATTR, None)
        if original is not None:
            originals.append((module, original))
            setattr(module, GATE_ATTR, _neutralised_clause)
    # `build_knowledge_read_clause` reaches the predicate through
    # `build_search_visibility_clause`, both resolved inside crud_queries — so
    # patching that module's binding covers the whole chain.
    assert any(m is crud_queries for m, _ in originals), (
        "crud_queries was not patched — the knowledge/visibility chain would "
        "keep its real gate and the control would under-report"
    )
    try:
        yield
    finally:
        for module, original in originals:
            setattr(module, GATE_ATTR, original)


@pytest_asyncio.fixture(loop_scope="session")
async def gate_graph(neo4j_driver: AsyncDriver) -> AsyncGenerator[AsyncDriver]:
    """Seed the fixture corpus; tear it down whatever the test does."""
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid STARTS WITH 'lp.gate-' OR n.uid STARTS WITH 'ps.gate-' "
            "OR n.uid STARTS WITH 'ku.gate-' OR n.uid IN [$user, $goal] DETACH DELETE n",
            {"user": USER, "goal": GOAL},
        )
        await session.run(SEED, SEED_PARAMS)
    yield neo4j_driver
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid STARTS WITH 'lp.gate-' OR n.uid STARTS WITH 'ps.gate-' "
            "OR n.uid STARTS WITH 'ku.gate-' OR n.uid IN [$user, $goal] DETACH DELETE n",
            {"user": USER, "goal": GOAL},
        )


def find_draft_identities(
    payload: Payload, path: str = "", allowed: frozenset[str] = frozenset()
) -> list[str]:
    """Every draft uid reachable in ``payload``, at any depth, with its route.

    Depth-unlimited and container-agnostic on purpose: the leak that shipped in
    ``find_ready_to_learn`` travelled as a string inside a list inside a row
    dict, and one in ``get_optimal_path_recommendations`` sits four levels down
    under ``recommendations.recommended_paths[i].path.uid``. Anything that only
    inspected top-level row keys would call both of those clean.
    """
    hits: list[str] = []
    if isinstance(payload, str):
        if payload in DRAFT_UIDS and payload not in allowed:
            hits.append(f"{path or '<root>'} = {payload}")
    elif isinstance(payload, dict):
        for key, value in payload.items():
            hits.extend(find_draft_identities(value, f"{path}.{key}", allowed))
    elif isinstance(payload, (list, tuple, set)):
        for index, value in enumerate(payload):
            hits.extend(find_draft_identities(value, f"{path}[{index}]", allowed))
    elif isinstance(payload, _HasUid):  # a domain model (PathStep, LearningPath, Ku)
        hits.extend(find_draft_identities(payload.uid, f"{path}.uid", allowed))
    return hits


FIXTURE_UIDS = frozenset(SEED_PARAMS[k] for k in SEED_PARAMS)


def fixture_identities(payload: Payload) -> frozenset[str]:
    """Which seeded entities this payload names, at any depth.

    Scoped to the seeded corpus so the comparison is exact — a free-text scan
    for "things that look like a uid" would drift with unrelated fixture data.
    """
    found = set()

    def walk(node: Payload) -> None:
        if isinstance(node, str):
            if node in FIXTURE_UIDS:
                found.add(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple, set)):
            for value in node:
                walk(value)
        elif isinstance(node, _HasUid):
            walk(node.uid)

    walk(payload)
    return frozenset(found)


def _payload(result: Result[Any], label: str) -> Payload:
    """Unwrap a ``Result``, refusing to silently walk the wrapper.

    Guarded because the wrapper is exactly what makes this harness vacuous: a
    ``Result`` is not a str/dict/list and exposes no ``uid``, so
    ``find_draft_identities`` walks straight past it and every surface reads
    clean. An early revision of this file did precisely that, and the tell was
    every surface reporting one row.
    """
    assert not result.is_error, f"{label} failed: {result.expect_error()}"
    payload = result.value
    assert not isinstance(payload, Result), f"{label}: still a Result — the harness is vacuous"
    return payload


def build_surfaces(driver: AsyncDriver) -> dict[str, SurfaceCall]:
    """Every covered surface as a zero-arg callable, keyed by registry qualname."""
    ku = KuBackend(driver, NeoLabel.KU, Ku, base_label=NeoLabel.ENTITY)
    ps = PsBackend(driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    lp = LpBackend(driver, NeoLabel.LEARNING_PATH, LearningPath, base_label=NeoLabel.ENTITY)
    xd = CrossDomainBackend(Neo4jQueryExecutor(driver))
    hub_params = {"min_confidence": 0.0, "min_connections": 0, "limit": LIMIT}

    return {
        "KuBackend.search_by_alias": partial(ku.search_by_alias, "gate"),
        "KuBackend.get_learning_path_uids": partial(ku.get_learning_path_uids, KU_VIA_DRAFT_ONLY),
        "PsBackend.get_standalone_steps": partial(ps.get_standalone_steps, LIMIT),
        "PsBackend.get_prioritized_steps": partial(ps.get_prioritized_steps, USER, LIMIT),
        # order_field is caller-prefixed (`s.{order_by}` in PsCoreService.list_steps);
        # a bare name is out of scope after the query's `WITH s, knowledge_uids`.
        "PsBackend.list_steps_raw": partial(
            ps.list_steps_raw, None, LIMIT, 0, "s.created_at", "ASC"
        ),
        "_KnowledgeContextMixin.find_learning_paths_teaching_ku": partial(
            ps.find_learning_paths_teaching_ku, KU_VIA_DRAFT_ONLY, LIMIT
        ),
        "_KnowledgeContextMixin.find_ready_to_learn": partial(
            ps.find_ready_to_learn, [], None, LIMIT
        ),
        "_KnowledgeContextMixin.find_learning_gaps": partial(
            ps.find_learning_gaps, [GOAL], [], LIMIT
        ),
        "_KnowledgeContextMixin.get_ku_lateral_edges": partial(
            ps.get_ku_lateral_edges, [KU_SHARED], LIMIT
        ),
        "_KnowledgeContextMixin.find_learning_recommendations": partial(
            ps.find_learning_recommendations, USER, None, LIMIT
        ),
        "_SemanticMixin.discover_semantic_bridges": partial(
            ps.discover_semantic_bridges, KU_SHARED, None, LIMIT
        ),
        "_LpProgressMixin.get_paths_aligned_with_goal": partial(
            lp.get_paths_aligned_with_goal, GOAL, LIMIT
        ),
        "_LpProgressMixin.get_paths_by_knowledge": partial(
            lp.get_paths_by_knowledge, KU_SHARED, LIMIT
        ),
        "_LpProgressMixin.get_user_paths_prioritized": partial(
            lp.get_user_paths_prioritized, USER, LIMIT
        ),
        "_LpStepMixin.list_all_paths_with_steps": partial(lp.list_all_paths_with_steps, LIMIT, 0),
        "_LpIntelligenceMixin.get_optimal_path_recommendations": partial(
            lp.get_optimal_path_recommendations, USER, None
        ),
        "CrossDomainBackend.find_knowledge_hubs": partial(xd.find_knowledge_hubs, "", hub_params),
        "CrossDomainBackend.find_learning_clusters": partial(
            xd.find_learning_clusters, "", {"min_density": 0.0, "limit": LIMIT}
        ),
        "CrossDomainBackend.find_similar_knowledge": partial(
            xd.find_similar_knowledge, KU_SHARED, 0.0, LIMIT
        ),
    }


# Gated surfaces this module does NOT measure, and why. Listed rather than
# omitted: a coverage gap that is not written down reads as coverage.
CRUD_QUERIES = "adapters.persistence.neo4j.query.cypher.crud_queries"
_BUILDER_RESIDUAL = (
    "a query BUILDER returns a Cypher string, not rows, so there is no output "
    "for an output invariant to inspect; its publication half rides on "
    "build_search_visibility_clause and is covered by "
    "tests/unit/test_search_visibility_scoping.py"
)

UNMEASURABLE: dict[tuple[str, str], str] = {
    ("adapters.persistence.neo4j.backends.curriculum_backends", "_nous_subtopic_pairs_query"): (
        "returns facet vocabulary (nous/subtopic strings), not entity "
        "identities — there is no uid for an identity-based invariant to detect"
    ),
    ("adapters.persistence.neo4j.zpd_backend", "<module>"): (
        "the ZPD zone query is built at import time and issued through "
        "ZPDBackend's own driver path; covered structurally by "
        "tests/unit/adapters/test_publication_gate_discovery_surfaces.py"
    ),
    ("adapters.persistence.neo4j._crud_mixin", "_CrudMixin.get_visible_to_user"): (
        "generic audience-scoped list, not curriculum-specific; its publication "
        "half is covered by tests/unit/test_search_visibility_scoping.py"
    ),
    ("adapters.persistence.neo4j._search_raw_mixin", "_SearchRawMixin.faceted_search_raw"): (
        "faceted search requires a facet configuration this fixture corpus does "
        "not build; publication rides on build_search_visibility_clause"
    ),
    ("adapters.persistence.neo4j._organizes_mixin", "_OrganizesMixin.list_root_organizers"): (
        "requires an ORGANIZES/MOC root, which this fixture corpus does not build"
    ),
    (
        "adapters.persistence.neo4j._knowledge_context_mixin",
        "_KnowledgeContextMixin.find_path_steps_containing_ku",
    ): (
        "matches (ku)<-[:CONTAINS_KNOWLEDGE]-(ps:PathStep); no such edge shape "
        "exists on the live graph, so the surface returns zero rows on every "
        "call and its gate cannot be measured — tracked separately"
    ),
    (
        "adapters.persistence.neo4j._lp_intelligence_mixin",
        "_LpIntelligenceMixin.get_recommended_path_steps",
    ): ("requires per-step user progress edges this fixture corpus does not build"),
    (CRUD_QUERIES, "build_text_search_query"): _BUILDER_RESIDUAL,
    (CRUD_QUERIES, "build_graph_aware_search_query"): _BUILDER_RESIDUAL,
    (CRUD_QUERIES, "build_array_any_match_query"): _BUILDER_RESIDUAL,
    (CRUD_QUERIES, "build_distinct_values_query"): _BUILDER_RESIDUAL,
    ("adapters.persistence.neo4j._semantic_mixin", "_SemanticMixin.query_foundational_knowledge"): (
        "ranks by a cached hub_score written by compute_hub_scores; the fixture "
        "corpus carries no cached scores"
    ),
    (
        "adapters.persistence.neo4j.vector_search_backend",
        "VectorSearchBackend.query_vector_index",
    ): (
        "requires a populated Neo4j vector index and an embedding, neither of "
        "which the CORE-tier test container provides"
    ),
}


def test_the_walker_can_see_a_typed_domain_model() -> None:
    """``_HasUid`` must match the models these surfaces actually return.

    The walker's model arm is the one that goes silently blind: if the Protocol
    stopped matching, every surface returning typed models would read clean and
    the invariant would be vacuous again — the same failure as the ``Result``
    wrapper it already survived once. The delta control would catch it, but only
    indirectly; this says it outright.
    """
    step = PathStep(uid=STEP_DRAFT, title="Draft step")
    assert isinstance(step, _HasUid)
    assert find_draft_identities([step]) == [f"[0].uid = {STEP_DRAFT}"]
    assert find_draft_identities([{"rows": [{"nested": step}]}]) == [
        f"[0].rows[0].nested.uid = {STEP_DRAFT}"
    ]


def test_registry_and_coverage_agree() -> None:
    """Every GATED surface is either measured here or listed as unmeasurable.

    The point of the registry is that a new surface cannot be added silently.
    This is the half that keeps THIS file honest: a gated surface may not simply
    be absent from both the covered set and the stated residual.
    """
    covered = set(_COVERED_KEYS)
    gated = {(s.module, s.qualname) for s in gated_surfaces()}
    unaccounted = gated - covered - set(UNMEASURABLE)
    assert not unaccounted, (
        f"gated surfaces neither measured nor declared unmeasurable: "
        f"{sorted(unaccounted)}. Add them to build_surfaces() or to UNMEASURABLE "
        f"with a reason."
    )
    stale = set(UNMEASURABLE) - gated
    assert not stale, f"UNMEASURABLE names a surface that is no longer GATED: {sorted(stale)}"


_COVERED_KEYS = (
    ("adapters.persistence.neo4j.backends.curriculum_backends", "KuBackend.search_by_alias"),
    ("adapters.persistence.neo4j.backends.curriculum_backends", "KuBackend.get_learning_path_uids"),
    ("adapters.persistence.neo4j.backends.curriculum_backends", "PsBackend.get_standalone_steps"),
    ("adapters.persistence.neo4j.backends.curriculum_backends", "PsBackend.get_prioritized_steps"),
    ("adapters.persistence.neo4j.backends.curriculum_backends", "PsBackend.list_steps_raw"),
    (
        "adapters.persistence.neo4j._knowledge_context_mixin",
        "_KnowledgeContextMixin.find_learning_paths_teaching_ku",
    ),
    (
        "adapters.persistence.neo4j._knowledge_context_mixin",
        "_KnowledgeContextMixin.find_ready_to_learn",
    ),
    (
        "adapters.persistence.neo4j._knowledge_context_mixin",
        "_KnowledgeContextMixin.find_learning_gaps",
    ),
    (
        "adapters.persistence.neo4j._knowledge_context_mixin",
        "_KnowledgeContextMixin.get_ku_lateral_edges",
    ),
    (
        "adapters.persistence.neo4j._knowledge_context_mixin",
        "_KnowledgeContextMixin.find_learning_recommendations",
    ),
    ("adapters.persistence.neo4j._semantic_mixin", "_SemanticMixin.discover_semantic_bridges"),
    (
        "adapters.persistence.neo4j._lp_progress_mixin",
        "_LpProgressMixin.get_paths_aligned_with_goal",
    ),
    ("adapters.persistence.neo4j._lp_progress_mixin", "_LpProgressMixin.get_paths_by_knowledge"),
    (
        "adapters.persistence.neo4j._lp_progress_mixin",
        "_LpProgressMixin.get_user_paths_prioritized",
    ),
    ("adapters.persistence.neo4j._lp_step_mixin", "_LpStepMixin.list_all_paths_with_steps"),
    (
        "adapters.persistence.neo4j._lp_intelligence_mixin",
        "_LpIntelligenceMixin.get_optimal_path_recommendations",
    ),
    ("adapters.persistence.neo4j.cross_domain_backend", "CrossDomainBackend.find_knowledge_hubs"),
    (
        "adapters.persistence.neo4j.cross_domain_backend",
        "CrossDomainBackend.find_learning_clusters",
    ),
    (
        "adapters.persistence.neo4j.cross_domain_backend",
        "CrossDomainBackend.find_similar_knowledge",
    ),
)


@pytest.mark.asyncio
@pytest.mark.parametrize("key", _COVERED_KEYS, ids=[q for _, q in _COVERED_KEYS])
async def test_no_draft_identity_reaches_the_caller(
    gate_graph: AsyncDriver, key: tuple[str, str]
) -> None:
    """The invariant: a gated surface returns no draft uid, at any depth."""
    qualname = key[1]
    surface = build_surfaces(gate_graph)[qualname]
    payload = _payload(await surface(), qualname)
    leaks = find_draft_identities(payload, allowed=USER_STATE_EXEMPT.get(key, frozenset()))
    assert not leaks, (
        f"{qualname} returned draft identities to the caller:\n  "
        + "\n  ".join(leaks)
        + "\nThe gate must withhold the IDENTITY of draft curriculum, wherever "
        "in the returned structure it travels."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("key", _COVERED_KEYS, ids=[q for _, q in _COVERED_KEYS])
async def test_gate_is_measured_not_merely_present(
    gate_graph: AsyncDriver, key: tuple[str, str]
) -> None:
    """Neutralising the predicate MUST change what the surface returns.

    This is the half that makes the invariant mean something. A fixture that
    reaches no draft, or a query whose gate never bites on this corpus, passes
    the invariant trivially — so each surface has to demonstrate that removing
    the predicate changes the output.

    The assertion is a DELTA rather than "a draft uid appears", because for the
    KU->path surfaces the two are different things. Gating the bridging step
    withholds a PUBLISHED path — the one reachable only through a draft step —
    so the identity that disappears is not itself a draft. An
    identity-of-a-draft control would have called those surfaces unmeasurable
    and quietly dropped exactly the case Codex raised as P1 on #1008.
    """
    qualname = key[1]
    surface = build_surfaces(gate_graph)[qualname]
    gated = fixture_identities(_payload(await surface(), qualname))
    with neutralised_gates():
        ungated = fixture_identities(_payload(await surface(), f"{qualname} (neutralised)"))

    assert gated != ungated, (
        f"{qualname} returned the SAME identities with the publication "
        f"predicate replaced by `true` ({sorted(ungated)}). The gate is "
        f"therefore unproven on this corpus, not verified: either the fixture "
        f"never reaches withheld content, or the predicate has no effect here. "
        f"Extend the fixture, or move the surface to UNMEASURABLE with a reason."
    )
    assert gated < ungated, (
        f"{qualname}: the gated result must be a strict SUBSET of the ungated "
        f"one. A gate that ADDS rows is not withholding, it is changing the "
        f"query's meaning. gated={sorted(gated)} ungated={sorted(ungated)}"
    )


@pytest.mark.asyncio
async def test_mixed_surfaces_keep_a_draft_the_learner_already_engaged(
    gate_graph: AsyncDriver,
) -> None:
    """Drafts are UNLISTED, not forbidden — the gate yields to the learner's state.

    ``get_prioritized_steps`` and ``get_user_paths_prioritized`` enumerate the
    whole catalogue AND order by the learner's own progress/enrolment. The
    predicate lands after the progress match (``WHERE progress IS NOT NULL OR
    <published>``), so a step marked draft AFTER someone started it must not
    vanish from the very list that exists to prioritise it.

    Asserted because the no-leak direction cannot see it: a gate made
    unconditional here would erase a learner's own progress and every other
    test in this module would still pass (Codex P2, #1012).
    """
    ps = PsBackend(gate_graph, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    lp = LpBackend(gate_graph, NeoLabel.LEARNING_PATH, LearningPath, base_label=NeoLabel.ENTITY)

    steps = _payload(await ps.get_prioritized_steps(USER, LIMIT), "get_prioritized_steps")
    step_uids = fixture_identities(steps)
    assert STEP_DRAFT_IN_PROGRESS in step_uids, (
        "a draft step the learner has IN_PROGRESS was withheld — the gate must "
        "yield to progress, or starting a step then having it marked draft "
        "erases the learner's own work from their list"
    )
    assert STEP_DRAFT not in step_uids, (
        "an UNENGAGED draft step must still be withheld — the user-state branch "
        "is a carve-out, not an opt-out of the whole gate"
    )

    paths = _payload(await lp.get_user_paths_prioritized(USER, LIMIT), "get_user_paths_prioritized")
    path_uids = fixture_identities(paths)
    assert LP_DRAFT_ENROLLED in path_uids, (
        "a draft path the learner is ENROLLED_IN was withheld — same carve-out"
    )
    assert LP_DRAFT not in path_uids, "an unenrolled draft path must still be withheld"


@pytest.mark.asyncio
async def test_by_uid_read_still_returns_a_draft(gate_graph: AsyncDriver) -> None:
    """The carve-out, asserted in the opposite direction.

    Over- and under-withholding look identical from one side. The gate belongs
    to DISCOVERY: a draft stays unlisted, not forbidden, so an author can still
    open their own by UID.
    """
    ps = PsBackend(gate_graph, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    result = await ps.get(STEP_DRAFT)
    assert not result.is_error, f"by-uid read of a draft failed: {result.expect_error()}"
    assert result.value is not None, (
        "a by-UID read must still return a draft — the author opens their own "
        "unfinished work; withholding here would be worse than the leak"
    )
    assert result.value.uid == STEP_DRAFT


@pytest.mark.asyncio
async def test_null_publication_state_is_never_withheld(gate_graph: AsyncDriver) -> None:
    """NULL tolerance, load-bearing: the fixture's published nodes carry NO key.

    Ingestion does not write absent frontmatter keys, so the entire
    pre-``publication_state`` corpus has no such property. A bare
    ``= 'published'`` predicate would hide all of it, and every assertion above
    would still pass — withholding everything withholds the drafts too.
    """
    ps = PsBackend(gate_graph, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    result = await ps.list_steps_raw(None, LIMIT, 0, "s.created_at", "ASC")
    steps = _payload(result, "list_steps_raw")
    uids = {step.uid for step in steps}
    assert STEP_PUBLISHED in uids, (
        "a node with NO publication_state was withheld — the predicate is not "
        "NULL-tolerant, and it would hide the entire pre-existing corpus"
    )
    assert STEP_DRAFT not in uids


async def test_writer_does_not_inherit_the_readers_gate() -> None:
    """``compute_hub_scores`` is registered WRITER, and must stay one.

    A writer that skipped drafts would leave freshly-published content with no
    cached score, because nothing recomputes on publish — the value would still
    be missing the moment the content became visible.
    """
    writers = [s for s in SURFACES if s.disposition is Disposition.WRITER]
    assert [s.qualname for s in writers] == ["_SemanticMixin.compute_hub_scores"], (
        "the WRITER set changed — adding a reader's gate to a maintenance pass "
        "is a behavioural change that needs its own argument"
    )
