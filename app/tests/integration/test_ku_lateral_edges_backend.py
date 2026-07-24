"""
Integration tests for PsBackend.get_ku_lateral_edges (testcontainer Neo4j).

Pins the backend method the Askesis SURFACE_CONNECTION pipeline calls
(call-pin lesson, #782): real Ku↔Ku lateral edges with authored evidence
come back with both endpoints, the relationship type, and the evidence text
— matched when EITHER endpoint is in the requested KU set.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.path_step import PathStep

pytestmark = pytest.mark.asyncio(loop_scope="session")

_FIXTURE_UIDS = [
    "ku.test.anchor",
    "ku.test.breath",
    "ku.test.other-a",
    "ku.test.other-b",
    "task_test_lateral",
]


@pytest.fixture
def ps_backend(neo4j_driver) -> PsBackend:
    return PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)


@pytest_asyncio.fixture(loop_scope="session")
async def lateral_edge_graph(neo4j_driver):
    """Two KUs joined by an evidenced RELATED_TO edge, plus noise:
    an edge between unrelated KUs and a Ku→Task edge (wrong endpoint type).
    """
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (anchor:Entity:Ku {uid: 'ku.test.anchor', title: 'Anchor',
                                      entity_type: 'ku'})
            CREATE (breath:Entity:Ku {uid: 'ku.test.breath', title: 'Breath',
                                      entity_type: 'ku'})
            CREATE (other_a:Entity:Ku {uid: 'ku.test.other-a', title: 'Other A',
                                       entity_type: 'ku'})
            CREATE (other_b:Entity:Ku {uid: 'ku.test.other-b', title: 'Other B',
                                       entity_type: 'ku'})
            CREATE (task:Entity:Task {uid: 'task_test_lateral', title: 'A Task',
                                      entity_type: 'task'})
            CREATE (anchor)-[:RELATED_TO {evidence: 'The breath is the most common anchor.',
                                          confidence: 0.9, source: 'teacher'}]->(breath)
            CREATE (breath)-[:PREREQUISITE_FOR]->(other_a)
            CREATE (breath)-[:ENABLES {evidence: 'Breath skill enables other-b.'}]->(other_b)
            CREATE (other_a)-[:RELATED_TO {evidence: 'noise'}]->(other_b)
            CREATE (breath)-[:RELATED_TO {evidence: 'wrong endpoint type'}]->(task)
            """
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n:Entity) WHERE n.uid IN $uids DETACH DELETE n",
            uids=_FIXTURE_UIDS,
        )


class TestGetKuLateralEdges:
    async def test_returns_evidenced_edge_when_target_endpoint_matches(
        self, ps_backend, lateral_edge_graph
    ) -> None:
        """anchor→breath matches on its TARGET when only breath is in the bundle."""
        result = await ps_backend.get_ku_lateral_edges(["ku.test.breath"])

        assert result.is_ok
        related = [r for r in result.value if r["relationship_type"] == "RELATED_TO"]
        assert related == [
            {
                "source_uid": "ku.test.anchor",
                "source_title": "Anchor",
                "target_uid": "ku.test.breath",
                "target_title": "Breath",
                "relationship_type": "RELATED_TO",
                "evidence": "The breath is the most common anchor.",
            }
        ]

    async def test_source_endpoint_match_and_null_evidence(
        self, ps_backend, lateral_edge_graph
    ) -> None:
        """breath→other_a matches on its SOURCE; evidence-less edge returns null."""
        result = await ps_backend.get_ku_lateral_edges(["ku.test.breath"])

        assert result.is_ok
        prereq = [r for r in result.value if r["relationship_type"] == "PREREQUISITE_FOR"]
        assert len(prereq) == 1
        assert prereq[0]["source_uid"] == "ku.test.breath"
        assert prereq[0]["target_uid"] == "ku.test.other-a"
        assert prereq[0]["evidence"] is None

    async def test_excludes_edges_not_touching_requested_kus(
        self, ps_backend, lateral_edge_graph
    ) -> None:
        result = await ps_backend.get_ku_lateral_edges(["ku.test.breath", "ku.test.anchor"])

        assert result.is_ok
        pairs = {(r["source_uid"], r["target_uid"]) for r in result.value}
        assert ("ku.test.other-a", "ku.test.other-b") not in pairs

    async def test_full_lateral_vocabulary_includes_enables(
        self, ps_backend, lateral_edge_graph
    ) -> None:
        """ENABLES edges surface too — the filter is the registry's full lateral
        set, not a hard-coded subset (Codex #787 P2)."""
        result = await ps_backend.get_ku_lateral_edges(["ku.test.breath"])

        assert result.is_ok
        enables = [r for r in result.value if r["relationship_type"] == "ENABLES"]
        assert len(enables) == 1
        assert enables[0]["target_uid"] == "ku.test.other-b"
        assert enables[0]["evidence"] == "Breath skill enables other-b."

    async def test_excludes_non_ku_endpoints(self, ps_backend, lateral_edge_graph) -> None:
        """Ku→Task RELATED_TO never surfaces — both endpoints must be KUs."""
        result = await ps_backend.get_ku_lateral_edges(["ku.test.breath"])

        assert result.is_ok
        target_uids = {r["target_uid"] for r in result.value}
        assert "task_test_lateral" not in target_uids

    async def test_empty_ku_set_returns_no_rows(self, ps_backend, lateral_edge_graph) -> None:
        result = await ps_backend.get_ku_lateral_edges([])

        assert result.is_ok
        assert result.value == []
