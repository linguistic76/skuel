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
