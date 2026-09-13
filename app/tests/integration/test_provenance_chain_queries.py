"""
The provenance chain queries follow the node's OUTGOING prerequisite chain.

``(node)-[:REQUIRES_KNOWLEDGE]->(prerequisite)`` is the direction every writer records
(GRAPH_CONTRACT: ``outgoing`` on the dependent; ``incoming`` = dependents). One graph
serves all three builders: a chain with mixed metadata, a second short trusted chain,
and a DEPENDENT of the queried node that must never come back as its prerequisite.

    A -> B (curriculum, 1 evidence, 0.9) -> C (inferred, no evidence) -> D (expert, 1 evidence, 0.8)
    A -> E (expert_verified, 3 evidence, 0.95)          E requires nothing further
    A -> F (curriculum, 2 evidence, 0.9)                F requires nothing further
    X -> A (curriculum, 1 evidence)                     X REQUIRES A — a dependent, not a prerequisite

The citation export returns one row per evidenced edge, attributed to that edge's own
target; the two chain builders return only chain ROOTS — a far prerequisite that requires
nothing further — with every edge on the way passing their filter.
"""

import pytest
from neo4j import AsyncDriver

from adapters.persistence.neo4j.query._provenance_queries import ProvenanceQueries
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.services.askesis_citation_service import AskesisCitationService


@pytest.fixture
async def prerequisite_chain(neo4j_driver: AsyncDriver, clean_neo4j) -> None:
    """The graph drawn in the module docstring."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (a:Entity:Ku {uid: 'ku.chain.a', entity_type: 'ku', title: 'A'})
            CREATE (b:Entity:Ku {uid: 'ku.chain.b', entity_type: 'ku', title: 'B'})
            CREATE (c:Entity:Ku {uid: 'ku.chain.c', entity_type: 'ku', title: 'C'})
            CREATE (d:Entity:Ku {uid: 'ku.chain.d', entity_type: 'ku', title: 'D'})
            CREATE (e:Entity:Ku {uid: 'ku.chain.e', entity_type: 'ku', title: 'E'})
            CREATE (f:Entity:Ku {uid: 'ku.chain.f', entity_type: 'ku', title: 'F'})
            CREATE (x:Entity:Ku {uid: 'ku.chain.x', entity_type: 'ku', title: 'X'})
            CREATE (a)-[:REQUIRES_KNOWLEDGE {source: 'curriculum', evidence: ['a needs b'], confidence: 0.9}]->(b)
            CREATE (b)-[:REQUIRES_KNOWLEDGE {source: 'inferred'}]->(c)
            CREATE (c)-[:REQUIRES_KNOWLEDGE {source: 'expert_verified', evidence: ['c needs d'], confidence: 0.8}]->(d)
            CREATE (a)-[:REQUIRES_KNOWLEDGE {source: 'expert_verified', evidence: ['e1', 'e2', 'e3'], confidence: 0.95}]->(e)
            CREATE (a)-[:REQUIRES_KNOWLEDGE {source: 'curriculum', evidence: ['f1', 'f2'], confidence: 0.9}]->(f)
            CREATE (x)-[:REQUIRES_KNOWLEDGE {source: 'curriculum', evidence: ['x needs a']}]->(a)
            """
        )


async def _chain_roots(neo4j_driver: AsyncDriver, query: str, params: dict) -> dict[str, int]:
    """{root uid: depth} for a chain-builder query, run raw — nothing consumes these builders yet."""
    async with neo4j_driver.session() as session:
        result = await session.run(query, params)
        return {record["start"]["uid"]: record["depth"] async for record in result}


@pytest.mark.asyncio
async def test_export_attributes_each_evidenced_edge_to_its_own_target(
    ku_backend, prerequisite_chain
) -> None:
    result = await ku_backend.get_citation_export(
        node_uid="ku.chain.a",
        node_label=NeoLabel.ENTITY,
        relationship_type=RelationshipName.REQUIRES_KNOWLEDGE.value,
        depth=3,
    )

    assert result.is_ok, result.error
    rows = {row["prerequisite_uid"]: row for row in result.value}
    # B, D, E and F each under their own uid with their own evidence; C (no evidence)
    # absent; X (a DEPENDENT of A — the incoming side) absent; nothing twice.
    assert set(rows) == {"ku.chain.b", "ku.chain.d", "ku.chain.e", "ku.chain.f"}, rows
    assert len(result.value) == 4
    assert rows["ku.chain.b"]["evidence"] == ["a needs b"]
    assert rows["ku.chain.b"]["prerequisite_title"] == "B"
    assert rows["ku.chain.d"]["evidence"] == ["c needs d"]
    assert rows["ku.chain.d"]["source"] == "expert_verified"


@pytest.mark.asyncio
async def test_citation_service_formats_the_chain_without_the_evidence_less_hop(
    ku_backend, prerequisite_chain
) -> None:
    service = AskesisCitationService(backend=ku_backend)

    result = await service.format_citations_for_askesis(
        knowledge_uid="ku.chain.a", knowledge_title="A", depth=3, min_evidence_count=1
    )

    assert result.is_ok, result.error
    text = result.value
    assert "**B**" in text and "a needs b" in text
    assert "**D**" in text and "c needs d" in text
    assert "**E**" in text and "**F**" in text
    assert "**C**" not in text and "**X**" not in text


@pytest.mark.asyncio
async def test_trust_filtered_chain_returns_the_trusted_roots_and_never_a_dependent(
    neo4j_driver: AsyncDriver, prerequisite_chain
) -> None:
    query, params = ProvenanceQueries.build_trust_filtered_prerequisite_chain(
        node_uid="ku.chain.a",
        allowed_sources=["expert_verified", "curriculum"],
        depth=5,
        min_confidence=0.7,
    )

    roots = await _chain_roots(neo4j_driver, query, params)

    # E and F: trusted edges to prerequisites that require nothing further.
    # B: trusted, but still requires C — not a root. C, D: reached only through the
    # untrusted (inferred) edge. X: requires A — a dependent, never a prerequisite.
    assert roots == {"ku.chain.e": 1, "ku.chain.f": 1}, roots


@pytest.mark.asyncio
async def test_well_supported_chain_applies_the_evidence_floor_to_every_edge(
    neo4j_driver: AsyncDriver, prerequisite_chain
) -> None:
    def build(min_evidence_count: int) -> tuple[str, dict]:
        return ProvenanceQueries.build_well_supported_prerequisites_query(
            node_uid="ku.chain.a", min_evidence_count=min_evidence_count, depth=5
        )

    # At 3 items only the A -> E edge qualifies; at 1, A -> F joins it — and A -> B still
    # passes but B is no root (it requires C), while the B -> C hop (no evidence) ends
    # every longer chain. X is a dependent and never appears at any floor.
    assert await _chain_roots(neo4j_driver, *build(3)) == {"ku.chain.e": 1}
    assert await _chain_roots(neo4j_driver, *build(1)) == {"ku.chain.e": 1, "ku.chain.f": 1}
