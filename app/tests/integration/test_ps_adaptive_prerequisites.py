"""`PsBackend.query_prerequisite_uids` — one round trip for a category's prerequisites.

The adaptive service reads a whole category's REQUIRES_KNOWLEDGE targets in one
statement and treats every requested uid as a key, so the contract pinned here is
the map's shape: a step with no prerequisites maps to ``[]`` (not absent), a step
with two maps to both, and a uid the graph does not hold is absent.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.path_step import PathStep

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def backend(neo4j_driver) -> PsBackend:
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n:Entity) WHERE n.uid STARTS WITH 'ps_prereq_' DETACH DELETE n")
        await session.run(
            """
            CREATE (root:Entity:PathStep {uid: 'ps_prereq_root', entity_type: 'path_step'})
            CREATE (a:Entity:PathStep {uid: 'ps_prereq_a', entity_type: 'path_step'})
            CREATE (b:Entity:PathStep {uid: 'ps_prereq_b', entity_type: 'path_step'})
            CREATE (leaf:Entity:PathStep {uid: 'ps_prereq_leaf', entity_type: 'path_step'})
            CREATE (leaf)-[:REQUIRES_KNOWLEDGE]->(a)
            CREATE (leaf)-[:REQUIRES_KNOWLEDGE]->(b)
            CREATE (a)-[:REQUIRES_KNOWLEDGE]->(root)
            """
        )
    yield PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n:Entity) WHERE n.uid STARTS WITH 'ps_prereq_' DETACH DELETE n")


@pytest.mark.asyncio
async def test_every_requested_step_is_a_key_and_only_its_own_prerequisites(backend) -> None:
    result = await backend.query_prerequisite_uids(
        ["ps_prereq_root", "ps_prereq_a", "ps_prereq_leaf", "ps_prereq_missing"]
    )

    assert result.is_ok
    prerequisites = result.value
    assert prerequisites["ps_prereq_root"] == []  # no prerequisites → an EMPTY list, not absent
    assert prerequisites["ps_prereq_a"] == ["ps_prereq_root"]
    assert sorted(prerequisites["ps_prereq_leaf"]) == ["ps_prereq_a", "ps_prereq_b"]
    assert "ps_prereq_missing" not in prerequisites  # no node → no key (not asked ≠ none)
    assert "ps_prereq_b" not in prerequisites  # only the requested uids come back


@pytest.mark.asyncio
async def test_an_empty_request_is_an_empty_map(backend) -> None:
    result = await backend.query_prerequisite_uids([])

    assert result.is_ok
    assert result.value == {}
