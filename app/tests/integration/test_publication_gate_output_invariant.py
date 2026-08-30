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

from adapters.persistence.neo4j.backends.curriculum_backends import (
    KnowledgeHealthBackend,
    KuBackend,
    LpBackend,
    PsBackend,
)
from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.neo4j_schema_manager import Neo4jSchemaManager
from adapters.persistence.neo4j.vector_search_backend import VectorSearchBackend
from core.models.enums import EntityType, PublicationState
from core.models.enums.metadata_enums import SearchVisibility
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

SurfaceCall = Callable[[], Awaitable[Result[Payload]]]
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
    """Seed the fixture corpus; tear it down whatever the test does.

    Fulltext indexes are synced through the real schema manager — the same call
    the composition root makes at boot — because ``query_fulltext_index`` is
    measured here and ``db.index.fulltext.queryNodes`` errors on a name that
    does not resolve. Indexes are idempotent and survive the node teardown.
    """
    sync_result = await Neo4jSchemaManager(neo4j_driver).sync_fulltext_indexes()
    assert sync_result.is_ok, f"fulltext index sync failed: {sync_result}"

    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid STARTS WITH 'lp.gate-' OR n.uid STARTS WITH 'ps.gate-' "
            "OR n.uid STARTS WITH 'ku.gate-' OR n.uid IN [$user, $goal] DETACH DELETE n",
            {"user": USER, "goal": GOAL},
        )
        await session.run(SEED, SEED_PARAMS)
        # Fulltext indexes are eventually consistent: without this the seeded
        # rows may not be searchable yet and the surface reads clean vacuously.
        await session.run("CALL db.awaitIndexes(120)")
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


def _payload(result: Result[Payload], label: str) -> Payload:
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


def build_surfaces(driver: AsyncDriver) -> dict[tuple[str, str], SurfaceCall]:
    """Every covered surface as a zero-arg callable, keyed by its registry key.

    Keyed by the full ``(module, qualname)`` tuple, not the bare method name:
    two modules can expose the same method name, and a name-keyed map would run
    one surface twice while leaving the other untested — with the coverage audit
    still green, because that compares tuples (Codex P2, #1012).
    """
    ku = KuBackend(driver, NeoLabel.KU, Ku, base_label=NeoLabel.ENTITY)
    ps = PsBackend(driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    lp = LpBackend(driver, NeoLabel.LEARNING_PATH, LearningPath, base_label=NeoLabel.ENTITY)
    xd = CrossDomainBackend(Neo4jQueryExecutor(driver))
    vs = VectorSearchBackend(Neo4jQueryExecutor(driver))
    hub_params = {"min_confidence": 0.0, "min_connections": 0, "limit": LIMIT}

    return {
        (
            "adapters.persistence.neo4j.backends.curriculum_backends",
            "KuBackend.search_by_alias",
        ): partial(ku.search_by_alias, "gate"),
        (
            "adapters.persistence.neo4j.backends.curriculum_backends",
            "KuBackend.get_learning_path_uids",
        ): partial(ku.get_learning_path_uids, KU_VIA_DRAFT_ONLY),
        (
            "adapters.persistence.neo4j.backends.curriculum_backends",
            "PsBackend.get_standalone_steps",
        ): partial(ps.get_standalone_steps, LIMIT),
        (
            "adapters.persistence.neo4j.backends.curriculum_backends",
            "PsBackend.get_prioritized_steps",
        ): partial(ps.get_prioritized_steps, USER, LIMIT),
        # order_field is caller-prefixed (`s.{order_by}` in PsCoreService.list_steps);
        # a bare name is out of scope after the query's `WITH s, knowledge_uids`.
        (
            "adapters.persistence.neo4j.backends.curriculum_backends",
            "PsBackend.list_steps_raw",
        ): partial(ps.list_steps_raw, None, LIMIT, 0, "s.created_at", "ASC"),
        (
            "adapters.persistence.neo4j._knowledge_context_mixin",
            "_KnowledgeContextMixin.find_learning_paths_teaching_ku",
        ): partial(ps.find_learning_paths_teaching_ku, KU_VIA_DRAFT_ONLY, LIMIT),
        (
            "adapters.persistence.neo4j._knowledge_context_mixin",
            "_KnowledgeContextMixin.find_ready_to_learn",
        ): partial(ps.find_ready_to_learn, [], None, LIMIT),
        # Converted from UNMEASURABLE, which claimed the CONTAINS_KNOWLEDGE shape
        # exists nowhere so the surface returns zero rows and cannot be measured.
        # The corpus seeds it (s_pub->ku_shared, s_draft->ku_draft_only), so the
        # gate IS measurable here. The live-graph half of that claim is a real,
        # separate defect — live CONTAINS_KNOWLEDGE runs path_step->path_step, so
        # this surface returns nothing in production — but a dead surface's gate
        # still has to be right for when the edge shape is fixed, and "cannot be
        # measured" was not true of this fixture.
        (
            "adapters.persistence.neo4j._knowledge_context_mixin",
            "_KnowledgeContextMixin.find_path_steps_containing_ku",
        ): partial(ps.find_path_steps_containing_ku, KU_VIA_DRAFT_ONLY, LIMIT),
        (
            "adapters.persistence.neo4j._knowledge_context_mixin",
            "_KnowledgeContextMixin.find_learning_gaps",
        ): partial(ps.find_learning_gaps, [GOAL], [], LIMIT),
        (
            "adapters.persistence.neo4j._knowledge_context_mixin",
            "_KnowledgeContextMixin.get_ku_lateral_edges",
        ): partial(ps.get_ku_lateral_edges, [KU_SHARED], LIMIT),
        (
            "adapters.persistence.neo4j._knowledge_context_mixin",
            "_KnowledgeContextMixin.find_learning_recommendations",
        ): partial(ps.find_learning_recommendations, USER, None, LIMIT),
        (
            "adapters.persistence.neo4j._semantic_mixin",
            "_SemanticMixin.discover_semantic_bridges",
        ): partial(ps.discover_semantic_bridges, KU_SHARED, None, LIMIT),
        (
            "adapters.persistence.neo4j._lp_progress_mixin",
            "_LpProgressMixin.get_paths_aligned_with_goal",
        ): partial(lp.get_paths_aligned_with_goal, GOAL, LIMIT),
        (
            "adapters.persistence.neo4j._lp_progress_mixin",
            "_LpProgressMixin.get_paths_by_knowledge",
        ): partial(lp.get_paths_by_knowledge, KU_SHARED, LIMIT),
        (
            "adapters.persistence.neo4j._lp_progress_mixin",
            "_LpProgressMixin.get_user_paths_prioritized",
        ): partial(lp.get_user_paths_prioritized, USER, LIMIT),
        (
            "adapters.persistence.neo4j._lp_step_mixin",
            "_LpStepMixin.list_all_paths_with_steps",
        ): partial(lp.list_all_paths_with_steps, LIMIT, 0),
        (
            "adapters.persistence.neo4j._lp_intelligence_mixin",
            "_LpIntelligenceMixin.get_optimal_path_recommendations",
        ): partial(lp.get_optimal_path_recommendations, USER, None),
        (
            "adapters.persistence.neo4j.cross_domain_backend",
            "CrossDomainBackend.find_knowledge_hubs",
        ): partial(xd.find_knowledge_hubs, "", hub_params),
        (
            "adapters.persistence.neo4j.cross_domain_backend",
            "CrossDomainBackend.find_learning_clusters",
        ): partial(xd.find_learning_clusters, "", {"min_density": 0.0, "limit": LIMIT}),
        (
            "adapters.persistence.neo4j.cross_domain_backend",
            "CrossDomainBackend.find_similar_knowledge",
        ): partial(xd.find_similar_knowledge, KU_SHARED, 0.0, LIMIT),
        # The fulltext half of hybrid search. Unlike its vector twin (UNMEASURABLE
        # — needs an embedding this container has no model for), Lucene ranks the
        # seeded titles directly: "ku" matches Shared KU, Draft KU and Far draft KU,
        # so the withheld pair is a real, measurable delta.
        (
            "adapters.persistence.neo4j.vector_search_backend",
            "VectorSearchBackend.query_fulltext_index",
        ): partial(vs.query_fulltext_index, NeoLabel.fulltext_index_name(NeoLabel.KU), "ku", LIMIT),
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
    ("adapters.persistence.neo4j.zpd_backend", "<module>:_ZONE_PUBLICATION_CLAUSE"): (
        "the zone query needs a learner with mastery/engagement evidence across a "
        "prerequisite frontier, which this corpus does not build. NOTE the "
        "previous reason here was misattributed: both facts it stated (built at "
        "import time, issued through ZPDBackend's own driver) are TRUE but "
        "neither makes the surface output-unmeasurable — the harness could hold a "
        "ZPDBackend as easily as a PsBackend. It also cited "
        "test_publication_gate_discovery_surfaces.py as coverage, which is the "
        "substring proxy this module's own docstring rejects"
    ),
    ("adapters.persistence.neo4j._search_raw_mixin", "_SearchRawMixin.faceted_search_raw"): (
        "every facet is a PARAMETER (search_fields, graph_enrichment_patterns, "
        "property_filters), so the corpus needs nothing — what is missing is a "
        "DomainConfig-shaped argument set, and hand-assembling one here would "
        "measure a configuration no domain declares. Publication rides on "
        "build_search_visibility_clause. The previous reason claimed the corpus "
        "lacked a facet configuration, which was false"
    ),
    ("adapters.persistence.neo4j._organizes_mixin", "_OrganizesMixin.list_root_organizers"): (
        "requires an ORGANIZES/MOC root, which this fixture corpus does not "
        "build. CONVERTIBLE: one ORGANIZES pair would cover it, deliberately not "
        "added here because new edges change what the OTHER surfaces return — "
        "discover_semantic_bridges walks an unconstrained [r1]"
    ),
    (
        "adapters.persistence.neo4j._lp_intelligence_mixin",
        "_LpIntelligenceMixin.get_recommended_path_steps",
    ): (
        "needs an ENABLES_KNOWLEDGE edge onto a draft, which this corpus does not "
        "build. The previous reason said 'per-step user progress edges', which was "
        "false — the corpus DOES build one, (u)-[:IN_PROGRESS]->(s_prog). "
        "CONVERTIBLE, on the same cascade caveat as list_root_organizers"
    ),
    (CRUD_QUERIES, "build_text_search_query"): _BUILDER_RESIDUAL,
    (CRUD_QUERIES, "build_graph_aware_search_query"): _BUILDER_RESIDUAL,
    (CRUD_QUERIES, "build_array_any_match_query"): _BUILDER_RESIDUAL,
    (CRUD_QUERIES, "build_array_contains_query"): _BUILDER_RESIDUAL,
    (CRUD_QUERIES, "build_relationship_traversal_query"): _BUILDER_RESIDUAL,
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
    (
        "adapters.persistence.neo4j.vector_search_backend",
        "VectorSearchBackend._chunk_visibility_clause",
    ): (
        "composes into semantic_search_chunks, which needs a populated chunk "
        "vector index and a query embedding — the same gap as its vector twin "
        "above; calling it here on an empty index would read vacuously clean. "
        "The draft-withholding invariant IS measured end-to-end, on a seeded "
        "index, by tests/integration/test_chunk_retrieval_visibility.py::"
        "test_draft_curriculum_and_private_notes_never_surface"
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
        "_KnowledgeContextMixin.find_path_steps_containing_ku",
    ),
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
    (
        "adapters.persistence.neo4j.vector_search_backend",
        "VectorSearchBackend.query_fulltext_index",
    ),
)


@pytest.mark.asyncio
@pytest.mark.parametrize("key", _COVERED_KEYS, ids=[q for _, q in _COVERED_KEYS])
async def test_no_draft_identity_reaches_the_caller(
    gate_graph: AsyncDriver, key: tuple[str, str]
) -> None:
    """The invariant: a gated surface returns no draft uid, at any depth."""
    qualname = key[1]
    surface = build_surfaces(gate_graph)[key]
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
    surface = build_surfaces(gate_graph)[key]
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
async def test_audience_scoped_by_uid_read_still_returns_a_draft(
    gate_graph: AsyncDriver,
) -> None:
    """The ANCHORED disposition, asserted against the graph rather than the label.

    ``get_visible_to_user`` is THE by-UID carve-out — the method five comments
    called ``get_visible_by_uid``, a name that has never existed here. It
    composes ``build_search_visibility_clause`` with
    ``apply_publication_gate=False``, so it scopes the AUDIENCE and deliberately
    returns a draft: the caller named the entity, and an author opens their own
    unfinished work.

    It sat in the GATED set for two PRs with a reason describing a *list*, which
    is why ANCHORED stood at zero entries. Nothing asserted its behaviour: the
    sibling ``test_by_uid_read_still_returns_a_draft`` exercises plain ``get()``,
    a different method that composes no helper at all.

    VACUITY GUARD. "The draft came back" passes trivially for a method that
    returns everything, so the same call is made twice, differing only in the
    audience declaration. Under PUBLIC the draft must come back; under
    OWNER_ONLY the very same uid must NOT, because a PathStep carries no
    ``user_uid``. That is a DELTA on one surface (#1012's rule), and it proves
    the method is capable of withholding — without which the first assertion
    says nothing about the carve-out.
    """
    ps = PsBackend(gate_graph, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)

    visible = await ps.get_visible_to_user(STEP_DRAFT, USER, SearchVisibility.PUBLIC)
    assert not visible.is_error, f"audience-scoped by-uid read failed: {visible.expect_error()}"
    assert visible.value is not None, (
        "the audience-scoped by-UID read withheld a draft. It is ANCHORED: the "
        "caller named the entity, so withholding here is worse than the leak — "
        "it hides an author's own unfinished work from them."
    )
    assert visible.value.uid == STEP_DRAFT

    withheld = await ps.get_visible_to_user(STEP_DRAFT, USER, SearchVisibility.OWNER_ONLY)
    assert not withheld.is_error, f"owner-scoped read failed: {withheld.expect_error()}"
    assert withheld.value is None, (
        "the audience predicate did not bite: a PathStep has no user_uid, so an "
        "OWNER_ONLY declaration must withhold it. Without this the assertion "
        "above is vacuous — a method that returns everything would pass it."
    )


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


@pytest.mark.asyncio
async def test_authoring_gauge_reports_drafts_instead_of_subtracting_them(
    gate_graph: AsyncDriver,
) -> None:
    """The REPORTS_DRAFTS disposition, asserted against the graph.

    The knowledge-health gauge takes ``build_publication_clause``'s PARAMS only,
    so the draft vocabulary keeps one definition while the gauge COUNTS drafts —
    an authoring instrument should show its author unfinished work, and
    subtracting them would silently move the ADR-080 baseline. Nothing asserted
    that; the disposition was a label with no behaviour behind it.

    Every number is compared against ground truth read from the same graph in
    the same test, never against a literal: ``gate_graph`` deletes only its own
    ``gate-`` nodes, so the gauge — which measures the whole corpus — has no
    deterministic absolute counts in a shared container.

    VACUITY GUARD, two parts. ``draft_curriculum_count`` must be non-zero, or
    "drafts are reported" is a claim about an empty set. And the corpus must
    hold at least one draft PathStep, or `total_path_steps` agreeing with the
    all-inclusive count cannot distinguish COUNTING drafts from there being no
    draft to subtract.
    """
    raw_result = await KnowledgeHealthBackend(
        Neo4jQueryExecutor(gate_graph)
    ).measure_knowledge_subgraph()
    assert not raw_result.is_error, f"gauge failed: {raw_result.expect_error()}"
    raw = raw_result.value
    assert raw is not None

    # Every discriminator is a PARAMETER sourced from the enum, never a literal.
    # A ground-truth query that hard-codes vocabulary drifts silently: production
    # follows the enum, this query keeps asking about the old spelling, and the
    # comparison still "passes" while counting the wrong nodes. `lint_skuel.py`
    # does not scan tests/, so SKUEL014 cannot catch it here (Codex P1) — the
    # same blind spot that let a lambda through on #1008.
    async with gate_graph.session() as session:
        rows = await session.run(
            """
            CALL () {
                MATCH (n:Entity) WHERE n.entity_type = $ps
                RETURN count(n) AS all_steps
            }
            CALL () {
                MATCH (n:Entity) WHERE n.entity_type = $ps
                  AND n.publication_state = $draft
                RETURN count(n) AS draft_steps
            }
            CALL () {
                MATCH (n:Entity) WHERE n.entity_type IN $curriculum_types
                  AND n.publication_state = $draft
                RETURN count(n) AS draft_curriculum
            }
            RETURN all_steps, draft_steps, draft_curriculum
            """,
            {
                "ps": EntityType.PATH_STEP.value,
                "draft": PublicationState.DRAFT.value,
                "curriculum_types": [
                    EntityType.KU.value,
                    EntityType.PATH_STEP.value,
                    EntityType.LEARNING_PATH.value,
                    EntityType.EXERCISE.value,
                ],
            },
        )
        truth = await rows.single()
    assert truth is not None

    assert truth["draft_steps"] > 0, (
        "the corpus holds no draft PathStep, so the totals assertion below "
        "cannot tell 'drafts are counted' from 'there was nothing to subtract'"
    )
    assert raw["draft_curriculum_count"] == truth["draft_curriculum"], (
        "the gauge under-reports drafts. It exists to REPORT them — "
        f"graph says {truth['draft_curriculum']}, gauge says "
        f"{raw['draft_curriculum_count']}."
    )
    assert raw["draft_curriculum_count"] > 0, (
        "no drafts reported at all, so this test asserts nothing about the "
        "REPORTS_DRAFTS disposition"
    )
    assert raw["total_path_steps"] == truth["all_steps"], (
        "the gauge SUBTRACTED drafts from its totals. It must count them: an "
        "authoring gauge that hides unfinished work reports a corpus its author "
        f"does not have. graph={truth['all_steps']} gauge={raw['total_path_steps']}"
    )


@pytest.mark.asyncio
async def test_writer_does_not_inherit_the_readers_gate(gate_graph: AsyncDriver) -> None:
    """``compute_hub_scores`` must SCORE drafts, not skip them.

    A writer that skipped drafts would leave freshly-published content with no
    cached score, because nothing recomputes on publish — the value would still
    be missing the moment the content became visible.

    Asserted against the graph rather than against the registry label. An
    earlier revision only checked that the WRITER disposition was unchanged,
    which is a tautology: if ``compute_hub_scores`` started composing
    ``build_knowledge_read_clause`` WITHOUT ``apply_publication_gate=False``,
    drafts would silently stop being scored and the test would still pass
    (Codex P2, #1012). Checking the registry is checking that we did not change
    our minds; this checks what the code does.
    """
    ps = PsBackend(gate_graph, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    result = await ps.compute_hub_scores()
    assert not result.is_error, f"compute_hub_scores failed: {result.expect_error()}"

    async with gate_graph.session() as session:
        rows = await session.run(
            "MATCH (n:Entity) WHERE n.uid IN $uids RETURN n.uid AS uid, n.hub_score AS score",
            {"uids": [KU_DRAFT, KU_SHARED]},
        )
        scored = {r["uid"]: r["score"] async for r in rows}

    assert scored.get(KU_DRAFT) is not None, (
        "the draft KU received no hub_score — the writer inherited a reader's "
        "publication gate. Nothing recomputes on publish, so this content would "
        "still have no score the moment it became visible."
    )
    assert scored.get(KU_SHARED) is not None, (
        "the published KU received no hub_score either, so the assertion above "
        "proves nothing about drafts — the writer is not scoring at all"
    )

    # The NEGATIVE half its reader siblings have. Scoring a draft only means
    # "exempt from the gate" if the gate is live and BITING on that same node
    # right now; otherwise this passes on a corpus where nothing is withheld
    # from anyone. So pair it with a gated READER over the same KU: the writer
    # must score what the reader refuses to name.
    ku = KuBackend(gate_graph, NeoLabel.KU, Ku, base_label=NeoLabel.ENTITY)
    reader = await ku.search_by_alias("gate")
    # Walked with fixture_identities rather than by reading a "uid" key: this
    # surface RETURNs whole nodes, so the row is {"ku": <Node>} and a hand-rolled
    # row["uid"] finds nothing — which made the withheld-draft assertion below
    # pass vacuously until the KU_SHARED guard caught it.
    reader_uids = fixture_identities(_payload(reader, "search_by_alias"))
    assert KU_SHARED in reader_uids, (
        "the gated reader returned nothing at all, so the next assertion would "
        "hold vacuously — an empty result withholds the draft for the wrong reason"
    )
    assert KU_DRAFT not in reader_uids, (
        "a gated reader RETURNED the draft KU, so the publication gate is not "
        "biting on this node and 'the writer scored it anyway' says nothing — "
        "the writer's exemption is only observable against a live gate"
    )

    writers = [s for s in SURFACES if s.disposition is Disposition.WRITER]
    assert [s.qualname for s in writers] == ["_SemanticMixin.compute_hub_scores"], (
        "the WRITER set changed — adding a reader's gate to a maintenance pass "
        "is a behavioural change that needs its own argument"
    )
