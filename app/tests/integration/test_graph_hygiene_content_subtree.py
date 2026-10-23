"""R4's ":Content off its subtree" check names each way a :Content node leaves its subtree.

A :Content node has no uid and is reached only through its one :Entity holder's
``HAS_CONTENT`` edge; its own edges out are ``HAS_CHUNK`` to a :ContentChunk. The check
carries no label but ``:Content``. The check is that rule read over the whole graph, so
the seed holds one well-formed subtree beside one violation per clause — another label, a
uid, no holder, an edge of another type, an allowed edge type with the wrong node at its
far end — each with every other clause held. The report must name each violation and
never the well-formed subtree.

The query is imported from the script (``fetch_anomalies``), not retyped.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from audit_graph_hygiene import fetch_anomalies  # type: ignore[import-not-found]

pytestmark = pytest.mark.asyncio(loop_scope="session")

CHECK = ":Content off its subtree"
MARK = "hygiene_r4_content_subtree"
WELL_FORMED = "ku.hygiene-r4.well-formed"
WITH_UID = "ku.hygiene-r4.content-with-uid"
STRAY_EDGE = "ku.hygiene-r4.stray-edge"
SECOND_HOLDER = "ku.hygiene-r4.second-holder"
WRONG_CHUNK = "ku.hygiene-r4.wrong-chunk"
EXTRA_LABEL = "ku.hygiene-r4.extra-label"
USER = "user_hygiene_r4"
REFERENCE_CHUNK = "chunk_hygiene_r4_reference"
ENTRY = "ue_hygiene_r4_entry"
CHUNK = "chunk_hygiene_r4"
CONTENT_UID = "content_hygiene_r4"


@pytest.fixture
async def seeded(neo4j_driver):
    """A well-formed subtree, then one :Content per way of leaving it."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (:Entity:Ku {uid: $well_formed, entity_type: 'ku', mark: $mark})
                   -[:HAS_CONTENT]->(:Content {mark: $mark})
                   -[:HAS_CHUNK]->(:ContentChunk {uid: $chunk, mark: $mark})
            CREATE (:Entity:Ku {uid: $with_uid, entity_type: 'ku', mark: $mark})
                   -[:HAS_CONTENT]->(:Content {uid: $content_uid, mark: $mark})
            CREATE (:Entity:Ku {uid: $stray_edge, entity_type: 'ku', mark: $mark})
                   -[:HAS_CONTENT]->(stray:Content {mark: $mark})
            CREATE (stray)-[:EXTRACTED_FROM]->
                   (:Entity:UserEntry {uid: $entry, entity_type: 'user_entry', mark: $mark})
            CREATE (:Content {mark: $mark, orphan: true})
            CREATE (:Entity:Ku {uid: $second_holder, entity_type: 'ku', mark: $mark})
                   -[:HAS_CONTENT]->(held_twice:Content {mark: $mark})
            CREATE (:User {uid: $user, mark: $mark})-[:HAS_CONTENT]->(held_twice)
            CREATE (:Entity:Ku {uid: $wrong_chunk, entity_type: 'ku', mark: $mark})
                   -[:HAS_CONTENT]->(:Content {mark: $mark})
                   -[:HAS_CHUNK]->(:ReferenceChunk {uid: $reference_chunk, mark: $mark})
            CREATE (:Entity:Ku {uid: $extra_label, entity_type: 'ku', mark: $mark})
                   -[:HAS_CONTENT]->(:Content:Entity {mark: $mark})
            """,
            well_formed=WELL_FORMED,
            with_uid=WITH_UID,
            stray_edge=STRAY_EDGE,
            entry=ENTRY,
            chunk=CHUNK,
            content_uid=CONTENT_UID,
            second_holder=SECOND_HOLDER,
            user=USER,
            wrong_chunk=WRONG_CHUNK,
            reference_chunk=REFERENCE_CHUNK,
            extra_label=EXTRA_LABEL,
            mark=MARK,
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n {mark: $mark}) DETACH DELETE n", mark=MARK)


async def _report(driver) -> list[dict]:
    return (await fetch_anomalies(driver))[CHECK]


async def test_a_well_formed_subtree_is_not_reported(neo4j_driver, seeded):
    rows = await _report(neo4j_driver)
    assert not [row for row in rows if WELL_FORMED in row["holders"]]


async def test_a_content_holding_a_uid_is_reported(neo4j_driver, seeded):
    rows = await _report(neo4j_driver)
    assert {
        "holders": [WITH_UID],
        "content_uid": CONTENT_UID,
        "stray": [],
        "extra_labels": [],
    } in rows


async def test_a_content_with_an_edge_of_another_type_is_reported(neo4j_driver, seeded):
    rows = await _report(neo4j_driver)
    assert {
        "holders": [STRAY_EDGE],
        "content_uid": None,
        "stray": ["EXTRACTED_FROM"],
        "extra_labels": [],
    } in rows


async def test_a_second_holder_outside_entity_is_reported(neo4j_driver, seeded):
    rows = await _report(neo4j_driver)
    assert {
        "holders": [SECOND_HOLDER],
        "content_uid": None,
        "stray": ["HAS_CONTENT"],
        "extra_labels": [],
    } in rows


async def test_a_chunk_edge_to_a_node_that_is_not_a_content_chunk_is_reported(neo4j_driver, seeded):
    rows = await _report(neo4j_driver)
    assert {
        "holders": [WRONG_CHUNK],
        "content_uid": None,
        "stray": ["HAS_CHUNK"],
        "extra_labels": [],
    } in rows


async def test_a_content_with_no_holder_is_reported(neo4j_driver, seeded):
    # An orphan has nothing to name it by, so the count must drop when the
    # seeded one goes — another test's leftover orphan cannot stand in for it.
    orphan: dict[str, list[str] | None] = {
        "holders": [],
        "content_uid": None,
        "stray": [],
        "extra_labels": [],
    }
    with_seeded = (await _report(neo4j_driver)).count(orphan)
    async with neo4j_driver.session() as session:
        await session.run("MATCH (c:Content {mark: $mark, orphan: true}) DELETE c", mark=MARK)
    assert (await _report(neo4j_driver)).count(orphan) == with_seeded - 1


async def test_a_content_carrying_another_label_is_reported(neo4j_driver, seeded):
    rows = await _report(neo4j_driver)
    expected = {
        "holders": [EXTRA_LABEL],
        "content_uid": None,
        "stray": [],
        "extra_labels": ["Entity"],
    }
    assert expected in rows
