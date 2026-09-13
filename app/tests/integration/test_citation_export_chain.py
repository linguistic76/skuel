"""
The citation export follows the node's outgoing prerequisite chain, one row per evidenced edge.

``(node)-[:REQUIRES_KNOWLEDGE]->(prerequisite)`` is the direction every writer records
(GRAPH_CONTRACT: ``outgoing`` on the dependent). Over a chain with mixed metadata the
export must attribute each edge's evidence to that edge's own target, drop the
evidence-less hop, keep an evidenced deeper hop, and never export an edge twice.
"""

import pytest
from neo4j import AsyncDriver

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.services.askesis_citation_service import AskesisCitationService


@pytest.fixture
async def prerequisite_chain(neo4j_driver: AsyncDriver, clean_neo4j) -> None:
    """A -> B (evidence) -> C (none) -> D (evidence); and X -> A (evidence) as a dependent of A."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (a:Entity:Ku {uid: 'ku.chain.a', entity_type: 'ku', title: 'A'})
            CREATE (b:Entity:Ku {uid: 'ku.chain.b', entity_type: 'ku', title: 'B'})
            CREATE (c:Entity:Ku {uid: 'ku.chain.c', entity_type: 'ku', title: 'C'})
            CREATE (d:Entity:Ku {uid: 'ku.chain.d', entity_type: 'ku', title: 'D'})
            CREATE (x:Entity:Ku {uid: 'ku.chain.x', entity_type: 'ku', title: 'X'})
            CREATE (a)-[:REQUIRES_KNOWLEDGE {source: 'curriculum', evidence: ['a needs b'], confidence: 0.9}]->(b)
            CREATE (b)-[:REQUIRES_KNOWLEDGE {source: 'inferred'}]->(c)
            CREATE (c)-[:REQUIRES_KNOWLEDGE {source: 'expert_verified', evidence: ['c needs d'], confidence: 0.8}]->(d)
            CREATE (x)-[:REQUIRES_KNOWLEDGE {source: 'curriculum', evidence: ['x needs a']}]->(a)
            """
        )


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
    # B and D each under their own uid with their own evidence; C (no evidence) absent;
    # X (a DEPENDENT of A — the incoming side) absent; nothing twice.
    assert set(rows) == {"ku.chain.b", "ku.chain.d"}, rows
    assert len(result.value) == 2
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
    assert "**C**" not in text and "**X**" not in text
