"""Real-Neo4j guard for the knowledge-health instrument (ADR-080 Horizon-1).

Builds a small, deterministic knowledge subgraph and asserts that
``KnowledgeHealthBackend.measure_knowledge_subgraph`` (the corpus Cypher) and the
``KnowledgeHealthService`` fold reproduce the constructed reality.

The load-bearing test is scoping: ``DEPENDS_ON`` is also the live Task-dependency
edge and ``RELATED_TO`` is a lateral edge on every activity domain, so an
UNSCOPED count would fold activity structure into a *knowledge* gauge. The
fixture plants a Task→Task ``DEPENDS_ON`` and ``RELATED_TO`` pair that MUST NOT
appear in the prerequisite-DAG or lateral counts.
"""

from __future__ import annotations

import pytest

from adapters.persistence.neo4j.backends.curriculum_backends import KnowledgeHealthBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.services.analytics.knowledge_health_service import KnowledgeHealthService

P = "khtest_"  # uid prefix for this module's fixture graph


async def _build_graph(neo4j_driver) -> None:
    """Plant a deterministic knowledge subgraph + an activity noise pair.

    Kus k1..k6 (k6 isolated → orphan); PathSteps ps1/ps2; LP lp1; Exercise ex1;
    Tasks t1/t2 carrying the activity-domain noise edges.
    """
    nodes = [
        (P + "k1", "Ku", "ku"),
        (P + "k2", "Ku", "ku"),
        (P + "k3", "Ku", "ku"),
        (P + "k4", "Ku", "ku"),
        (P + "k5", "Ku", "ku"),
        (P + "k6", "Ku", "ku"),  # orphan — zero incident edges
        (P + "ps1", "PathStep", "path_step"),
        (P + "ps2", "PathStep", "path_step"),
        (P + "lp1", "LearningPath", "learning_path"),
        (P + "ex1", "Exercise", "exercise"),
        (P + "t1", "Task", "task"),  # activity noise
        (P + "t2", "Task", "task"),
    ]
    edges = [
        # Composition: 3 edges (USES_KU x2 + CONTAINS_KNOWLEDGE) → composed {k1,k2,k3}
        (P + "ps1", "USES_KU", P + "k1"),
        (P + "ps1", "USES_KU", P + "k2"),
        (P + "ps2", "CONTAINS_KNOWLEDGE", P + "k3"),
        # Prerequisite DAG: k1→k2→k3 (2 edges, depth 2, dag Kus {k1,k2,k3})
        (P + "k1", "PREREQUISITE_FOR", P + "k2"),
        (P + "k2", "PREREQUISITE_FOR", P + "k3"),
        # ORGANIZES: k1→k4 (organized {k1,k4})
        (P + "k1", "ORGANIZES", P + "k4"),
        # Lateral: k4—RELATED_TO—k5 (1 edge)
        (P + "k4", "RELATED_TO", P + "k5"),
        # Enablement: k1→k5 (surfaced separately, not lateral)
        (P + "k1", "ENABLES", P + "k5"),
        # Practice: ps1 anchors ex1 (ps_with_exercise = 1 of 2)
        (P + "ps1", "HAS_EXERCISE", P + "ex1"),
        # Activity NOISE — must NOT count in the knowledge gauge (scoping guard):
        (P + "t1", "DEPENDS_ON", P + "t2"),  # NOT a knowledge prerequisite
        (P + "t1", "RELATED_TO", P + "t2"),  # NOT a knowledge lateral edge
    ]
    async with neo4j_driver.session() as s:
        for uid, label, etype in nodes:
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        # ex1 is a CURRICULUM-scoped exercise (the only scope practice coverage counts).
        await s.run(
            "MATCH (ex{uid:$u}) SET ex.scope = 'curriculum'",
            u=P + "ex1",
        )
        for from_uid, rel, to_uid in edges:
            await s.run(
                f"MATCH (a{{uid:$a}}),(b{{uid:$b}}) CREATE (a)-[:{rel}]->(b)",
                a=from_uid,
                b=to_uid,
            )


@pytest.mark.asyncio
async def test_measures_constructed_subgraph(neo4j_driver, clean_neo4j) -> None:
    """The backend reproduces the planted graph's structural facts exactly."""
    await _build_graph(neo4j_driver)
    backend = KnowledgeHealthBackend(Neo4jQueryExecutor(neo4j_driver))

    result = await backend.measure_knowledge_subgraph()
    assert result.is_ok, result
    raw = result.value

    assert raw["total_kus"] == 6
    assert raw["total_path_steps"] == 2
    assert raw["total_learning_paths"] == 1
    assert raw["total_exercises"] == 1

    # Degree = all incident edges per Ku: [4,3,2,2,2,0] → avg 13/6, max 4, 1 orphan.
    assert raw["avg_ku_degree"] == pytest.approx(13 / 6, abs=1e-3)
    assert raw["max_ku_degree"] == 4
    assert raw["orphan_ku_count"] == 1
    assert [o["uid"] for o in raw["orphan_kus"]] == [P + "k6"]

    assert raw["composition_edge_count"] == 3
    assert raw["composed_ku_count"] == 3
    assert raw["dag_max_depth"] == 2
    assert raw["dag_ku_count"] == 3
    assert raw["organizes_edge_count"] == 1
    assert raw["organized_ku_count"] == 2
    assert raw["enablement_edge_count"] == 1
    assert raw["path_steps_with_exercise"] == 1


@pytest.mark.asyncio
async def test_scoping_excludes_activity_edges(neo4j_driver, clean_neo4j) -> None:
    """Task→Task DEPENDS_ON / RELATED_TO must NOT pollute knowledge counts.

    This is the plan's gotcha #1: the prerequisite DAG and lateral density are
    scoped to knowledge nodes on BOTH endpoints, so activity-domain edges of the
    same relationship type are excluded.
    """
    await _build_graph(neo4j_driver)
    backend = KnowledgeHealthBackend(Neo4jQueryExecutor(neo4j_driver))

    raw = (await backend.measure_knowledge_subgraph()).value

    # Only k1→k2, k2→k3 are knowledge prerequisites — the Task DEPENDS_ON is out.
    assert raw["prerequisite_edge_count"] == 2
    # Only k4—k5 is a knowledge lateral — the Task RELATED_TO is out.
    assert raw["lateral_edge_count"] == 1


@pytest.mark.asyncio
async def test_service_derives_report(neo4j_driver, clean_neo4j) -> None:
    """The service fold produces coverage ratios, a bounded score, and flags."""
    await _build_graph(neo4j_driver)
    service = KnowledgeHealthService(
        backend=KnowledgeHealthBackend(Neo4jQueryExecutor(neo4j_driver))
    )

    result = await service.analyze_knowledge_subgraph_health()
    assert result.is_ok, result
    report = result.value

    assert report["orphan_fraction"] == pytest.approx(1 / 6, abs=1e-3)
    assert report["composition"]["coverage"] == pytest.approx(3 / 6, abs=1e-3)
    assert report["prerequisite_dag"]["coverage"] == pytest.approx(3 / 6, abs=1e-3)
    assert report["organizes"]["coverage"] == pytest.approx(2 / 6, abs=1e-3)
    assert report["practice_coverage"] == pytest.approx(1 / 2, abs=1e-3)
    assert 0.0 <= report["gds_readiness_score"] <= 1.0
    # Sparse fixture → not GDS-ready, and the orphan is flagged.
    assert report["gds_ready"] is False
    assert any("orphan" in f.lower() for f in report["flags"])


@pytest.mark.asyncio
async def test_depth_ignores_inverse_prerequisite_cycle(neo4j_driver, clean_neo4j) -> None:
    """An auto-inverse prerequisite pair must not inflate dag_max_depth (Codex #770 P2).

    `A-PREREQUISITE_FOR->B` + `B-REQUIRES_PREREQUISITE->A` (the lateral auto-inverse)
    is a 2-cycle. A single mixed directed walk would loop it to the depth cap; the
    direction-coherent traversal reports the true chain depth of 1.
    """
    async with neo4j_driver.session() as s:
        for uid in (P + "d1", P + "d2"):
            await s.run(
                "CREATE (n:Entity:Ku {uid:$u, entity_type:'ku', title:$u, "
                "status:'active', created_at:datetime()})",
                u=uid,
            )
        await s.run(
            "MATCH (a{uid:$a}),(b{uid:$b}) CREATE (a)-[:PREREQUISITE_FOR]->(b)",
            a=P + "d1",
            b=P + "d2",
        )
        await s.run(
            "MATCH (a{uid:$a}),(b{uid:$b}) CREATE (b)-[:REQUIRES_PREREQUISITE]->(a)",
            a=P + "d1",
            b=P + "d2",
        )
    backend = KnowledgeHealthBackend(Neo4jQueryExecutor(neo4j_driver))

    raw = (await backend.measure_knowledge_subgraph()).value
    # Both edges are counted broadly, but depth is the true chain length, not the cap.
    assert raw["prerequisite_edge_count"] == 2
    assert raw["dag_max_depth"] == 1


@pytest.mark.asyncio
async def test_learner_telemetry_excluded_from_degree(neo4j_driver, clean_neo4j) -> None:
    """Learner-state telemetry must not count toward degree or un-orphan a Ku (Codex #770 P2).

    A Ku whose only incident edge is a MASTERED (learner state) edge is
    structurally isolated → orphan, and does not raise avg degree.
    """
    async with neo4j_driver.session() as s:
        for uid in (P + "t_iso", P + "t_a", P + "t_b"):
            await s.run(
                "CREATE (n:Entity:Ku {uid:$u, entity_type:'ku', title:$u, "
                "status:'active', created_at:datetime()})",
                u=uid,
            )
        await s.run(
            "CREATE (u:Entity:Task {uid:$u, entity_type:'task', title:$u, "
            "status:'active', created_at:datetime()})",
            u=P + "t_user",
        )
        # Telemetry-only edge on t_iso (type-filtered out regardless of endpoints).
        await s.run(
            "MATCH (u{uid:$u}),(k{uid:$k}) CREATE (u)-[:MASTERED]->(k)",
            u=P + "t_user",
            k=P + "t_iso",
        )
        # Structural lateral so t_a / t_b are genuinely connected.
        await s.run(
            "MATCH (a{uid:$a}),(b{uid:$b}) CREATE (a)-[:RELATED_TO]->(b)",
            a=P + "t_a",
            b=P + "t_b",
        )
    backend = KnowledgeHealthBackend(Neo4jQueryExecutor(neo4j_driver))

    raw = (await backend.measure_knowledge_subgraph()).value
    assert raw["total_kus"] == 3
    assert raw["orphan_ku_count"] == 1
    assert [o["uid"] for o in raw["orphan_kus"]] == [P + "t_iso"]
    # Degrees after excluding MASTERED: [0, 1, 1] → avg 2/3.
    assert raw["avg_ku_degree"] == pytest.approx(2 / 3, abs=1e-3)


@pytest.mark.asyncio
async def test_practice_coverage_counts_curriculum_scope_only(neo4j_driver, clean_neo4j) -> None:
    """PERSONAL exercises must not count toward corpus practice coverage (Codex #770 P2).

    A learner's PERSONAL exercise dual-writes the same `HAS_EXERCISE` edge as a
    vault-authored CURRICULUM exercise, so only CURRICULUM scope counts.
    """
    async with neo4j_driver.session() as s:
        for uid, label, etype, scope in (
            (P + "pc_ps1", "PathStep", "path_step", None),
            (P + "pc_ps2", "PathStep", "path_step", None),
            (P + "pc_cur", "Exercise", "exercise", "curriculum"),
            (P + "pc_per", "Exercise", "exercise", "personal"),
        ):
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
            if scope is not None:
                await s.run("MATCH (n{uid:$u}) SET n.scope = $s", u=uid, s=scope)
        # ps1 → CURRICULUM exercise (counts); ps2 → PERSONAL exercise (excluded).
        await s.run(
            "MATCH (a{uid:$a}),(b{uid:$b}) CREATE (a)-[:HAS_EXERCISE]->(b)",
            a=P + "pc_ps1",
            b=P + "pc_cur",
        )
        await s.run(
            "MATCH (a{uid:$a}),(b{uid:$b}) CREATE (a)-[:HAS_EXERCISE]->(b)",
            a=P + "pc_ps2",
            b=P + "pc_per",
        )
    backend = KnowledgeHealthBackend(Neo4jQueryExecutor(neo4j_driver))

    raw = (await backend.measure_knowledge_subgraph()).value
    assert raw["total_path_steps"] == 2
    # Only ps1 (CURRICULUM exercise) counts; ps2's PERSONAL exercise is excluded.
    assert raw["path_steps_with_exercise"] == 1


@pytest.mark.asyncio
async def test_requires_step_counts_in_prerequisite_dag(neo4j_driver, clean_neo4j) -> None:
    """PathStep prerequisites (REQUIRES_STEP) belong in the DAG (Codex #770 P2).

    Authored via `prerequisite_step_uids`, REQUIRES_STEP is a real PathStep→PathStep
    prerequisite edge; a corpus with these but no Ku PREREQUISITE_FOR must not read
    as an empty DAG.
    """
    async with neo4j_driver.session() as s:
        for uid in (P + "rs1", P + "rs2", P + "rs3"):
            await s.run(
                "CREATE (n:Entity:PathStep {uid:$u, entity_type:'path_step', title:$u, "
                "status:'active', created_at:datetime()})",
                u=uid,
            )
        # rs1 requires rs2 requires rs3 → a 2-hop PathStep prerequisite chain.
        await s.run(
            "MATCH (a{uid:$a}),(b{uid:$b}) CREATE (a)-[:REQUIRES_STEP]->(b)",
            a=P + "rs1",
            b=P + "rs2",
        )
        await s.run(
            "MATCH (a{uid:$a}),(b{uid:$b}) CREATE (a)-[:REQUIRES_STEP]->(b)",
            a=P + "rs2",
            b=P + "rs3",
        )
    backend = KnowledgeHealthBackend(Neo4jQueryExecutor(neo4j_driver))

    raw = (await backend.measure_knowledge_subgraph()).value
    assert raw["prerequisite_edge_count"] == 2  # both REQUIRES_STEP edges counted
    assert raw["dag_max_depth"] == 2  # rs1→rs2→rs3 chain contributes depth


@pytest.mark.asyncio
async def test_label_less_pathstep_counted_by_entity_type(neo4j_driver, clean_neo4j) -> None:
    """PathSteps persisted without the :PathStep label must still count (Codex #770 P2).

    The one writer that produced such nodes (`create_step_node`) now stamps
    the multi-label (Codex #1068 P1), but the structural gauge keeps matching
    by entity_type as defense for any legacy label-less data.
    """
    async with neo4j_driver.session() as s:
        # Label-less path step (mirrors create_step_node) + a labelled one.
        await s.run(
            "CREATE (n:Entity {uid:$u, entity_type:'path_step', title:$u, "
            "status:'active', created_at:datetime()})",
            u=P + "ll_nolabel",
        )
        await s.run(
            "CREATE (n:Entity:PathStep {uid:$u, entity_type:'path_step', title:$u, "
            "status:'active', created_at:datetime()})",
            u=P + "ll_labelled",
        )
    backend = KnowledgeHealthBackend(Neo4jQueryExecutor(neo4j_driver))

    raw = (await backend.measure_knowledge_subgraph()).value
    # Both count — label-only matching would have found just the labelled one.
    assert raw["total_path_steps"] == 2


@pytest.mark.asyncio
async def test_empty_subgraph_is_all_zeros(neo4j_driver, clean_neo4j) -> None:
    """An empty knowledge subgraph measures to zeros, not an error."""
    backend = KnowledgeHealthBackend(Neo4jQueryExecutor(neo4j_driver))

    result = await backend.measure_knowledge_subgraph()
    assert result.is_ok, result
    raw = result.value
    assert raw["total_kus"] == 0
    assert raw["avg_ku_degree"] == 0.0
    assert raw["orphan_ku_count"] == 0
    assert raw["orphan_kus"] == []

    report = KnowledgeHealthService._build_report(raw)
    assert report["gds_readiness_score"] == 0.0
    assert report["gds_ready"] is False


@pytest.mark.asyncio
async def test_embedding_coverage_probe_counts_and_scope(neo4j_driver, clean_neo4j) -> None:
    """``EmbeddingCoverageBackend`` counts total vs embedding-NULL per label.

    The load-bearing halves: the UserEntry scope filter (only knowledge-pipeline,
    non-private entries are gauge-visible — a vector may never exist for the
    rest, so they must count as neither total nor missing) and remedy
    assignment (ReferenceChunk has no backfill path).
    """
    from adapters.persistence.neo4j.backends.curriculum_backends import (
        EmbeddingCoverageBackend,
    )
    from core.services.embeddings.retrievability import BACKFILL_COMMAND

    async with neo4j_driver.session() as s:
        # Ku: one embedded, one not.
        await s.run(
            "CREATE (:Entity:Ku {uid:$k1, entity_type:'ku', title:$k1, embedding:[0.1,0.2]}),"
            " (:Entity:Ku {uid:$k2, entity_type:'ku', title:$k2})",
            k1=P + "ec_k1",
            k2=P + "ec_k2",
        )
        # Chunks: ContentChunk missing, ReferenceChunk embedded.
        await s.run(
            "CREATE (:ContentChunk {uid:$cc}), (:ReferenceChunk {uid:$rc, embedding:[0.1]})",
            cc=P + "ec_cc1",
            rc=P + "ec_rc1",
        )
        # UserEntry scope: only the knowledge-pipeline, non-private entry counts.
        await s.run(
            "CREATE (:Entity:UserEntry {uid:$u1, entity_type:'user_entry', pipeline:'knowledge'}),"
            " (:Entity:UserEntry {uid:$u2, entity_type:'user_entry', pipeline:'knowledge', private:true}),"
            " (:Entity:UserEntry {uid:$u3, entity_type:'user_entry', pipeline:'exercise'})",
            u1=P + "ec_ue1",
            u2=P + "ec_ue2",
            u3=P + "ec_ue3",
        )
    backend = EmbeddingCoverageBackend(Neo4jQueryExecutor(neo4j_driver))

    result = await backend.measure_embedding_coverage()
    assert result.is_ok, result
    coverage = result.value

    by = {c.label: c for c in coverage.by_label}
    assert by["Ku"].total == 2 and by["Ku"].missing == 1
    assert by["ContentChunk"].total == 1 and by["ContentChunk"].missing == 1
    assert by["ReferenceChunk"].total == 1 and by["ReferenceChunk"].missing == 0
    # Scope filter: the private + non-knowledge entries are gauge-invisible.
    assert by["UserEntry"].total == 1 and by["UserEntry"].missing == 1

    assert coverage.missing == 3  # ec_k2 + ec_cc1 + ec_ue1
    assert coverage.missing_chunks == 1
    assert coverage.missing_entities == 2
    assert coverage.is_complete is False

    # Remedy assignment travels with the measurement.
    assert by["Ku"].backfill == BACKFILL_COMMAND
    assert by["ReferenceChunk"].backfill is None


@pytest.mark.asyncio
async def test_embedding_coverage_empty_graph_is_complete(neo4j_driver, clean_neo4j) -> None:
    """An empty graph measures as complete (all-zero coverage), not an error."""
    from adapters.persistence.neo4j.backends.curriculum_backends import (
        EmbeddingCoverageBackend,
    )

    backend = EmbeddingCoverageBackend(Neo4jQueryExecutor(neo4j_driver))
    result = await backend.measure_embedding_coverage()
    assert result.is_ok, result
    assert result.value.total == 0
    assert result.value.is_complete is True


@pytest.mark.asyncio
async def test_create_step_node_multilabel_visible_to_coverage(neo4j_driver, clean_neo4j) -> None:
    """The API step writer stamps :Entity:PathStep (Codex #1068 P1).

    An Entity-only step is invisible to every label-matched instrument — the
    embedding worker's store, the backfill script, and the coverage probe — so
    its embedding request would silently match zero rows. Guard the writer's
    labels AND the step's visibility to the coverage gauge.
    """
    from adapters.persistence.neo4j.backends.curriculum_backends import (
        EmbeddingCoverageBackend,
        PsBackend,
    )
    from core.models.enums.neo_labels import NeoLabel
    from core.models.pathways.path_step import PathStep

    ps_backend = PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    created = await ps_backend.create_step_node(
        {
            "uid": P + "api_ps1",
            "title": "API-created step",
            "intent": "coverage guard",
            "description": "",
            "learning_path_uid": None,
            "sequence": 1,
            "mastery_threshold": 0.8,
            "current_mastery": 0.0,
            "estimated_hours": 1.0,
            "step_difficulty": "beginner",
            "status": "active",
            "completed": False,
            "domain": "test",
        }
    )
    assert created.is_ok, created

    async with neo4j_driver.session() as s:
        result = await s.run("MATCH (n {uid:$u}) RETURN labels(n) AS labels", u=P + "api_ps1")
        record = await result.single()
    assert set(record["labels"]) == {"Entity", "PathStep"}

    coverage_result = await EmbeddingCoverageBackend(
        Neo4jQueryExecutor(neo4j_driver)
    ).measure_embedding_coverage()
    assert coverage_result.is_ok, coverage_result
    by = {c.label: c for c in coverage_result.value.by_label}
    assert by["PathStep"].total == 1
    assert by["PathStep"].missing == 1  # no embedding yet — the gauge must see it
