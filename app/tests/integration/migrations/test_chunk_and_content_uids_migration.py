"""The chunk and Content uid migration, census and write, against a real Neo4j.

``scripts/migrations/chunk_and_content_uids_2026_10.py`` renames every chunk uid
in the old ``{parent}:chunk:{n}`` shape to ``chunk_uid`` of its store, parent and
index, and clears the uid every :Content node shared with its entity.

The seed is the graph the old writers left: a PathStep and a UserEntry whose
:Content carries the entity's uid and whose chunks carry the old uid and an
embedding, and a shelved Resource whose reference chunks do the same — plus a
PathStep the new code already re-chunked, which the run must leave alone.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

import pytest

from core.models.ps_content.content_chunks import ChunkStore, chunk_uid

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from neo4j import AsyncDriver

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

SCRIPT = (
    Path(__file__).resolve().parents[3] / "scripts/migrations/chunk_and_content_uids_2026_10.py"
)


def _load() -> ModuleType:
    """Import the script by path (``scripts/`` is not a package)."""
    spec = importlib.util.spec_from_file_location("chunk_and_content_uids_2026_10", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migration = _load()

STEP = "ps.zzzchunkmig.step"
ENTRY = "ue_zzzchunkmig1"
BOOK = "resource.zzzchunkmig-book"
FRESH = "ps.zzzchunkmig.fresh"
PARENTS = [STEP, ENTRY, BOOK, FRESH]
CHUNKS = {STEP: 3, ENTRY: 2, BOOK: 2, FRESH: 2}
VECTOR = [0.5, 0.25, 0.125]


async def _run(
    driver: AsyncDriver, query: str, **params: Any
) -> list[Any]:  # boundary: cypher-params
    async with driver.session() as session:
        result = await session.run(query, params)
        return [record async for record in result]


async def _clean(driver: AsyncDriver) -> None:
    await _run(
        driver,
        """
        MATCH (p) WHERE p.uid IN $parents
        OPTIONAL MATCH (p)-[:HAS_CONTENT]->(c:Content)
        OPTIONAL MATCH (c)-[:HAS_CHUNK]->(k:ContentChunk)
        OPTIONAL MATCH (p)-[:HAS_REFERENCE_CHUNK]->(rk:ReferenceChunk)
        DETACH DELETE k, rk, c, p
        """,
        parents=PARENTS,
    )


@pytest.fixture
async def old_graph(neo4j_driver: AsyncDriver, clean_neo4j: None) -> AsyncIterator[None]:
    """The old shapes on an otherwise empty graph — the census reads every chunk."""
    await _clean(neo4j_driver)
    await _run(
        neo4j_driver,
        """
        CREATE (:Entity:PathStep {uid: $step, entity_type: 'path_step'})
        CREATE (:Entity:UserEntry {uid: $entry, entity_type: 'user_entry'})
        CREATE (:Entity:Resource {uid: $book, entity_type: 'resource'})
        CREATE (:Entity:PathStep {uid: $fresh, entity_type: 'path_step'})
        """,
        step=STEP,
        entry=ENTRY,
        book=BOOK,
        fresh=FRESH,
    )
    # The old content store: Content on its entity's uid, chunks on {parent}:chunk:{n}.
    for parent in (STEP, ENTRY):
        await _run(
            neo4j_driver,
            """
            MATCH (e:Entity {uid: $parent})
            CREATE (e)-[:HAS_CONTENT]->(c:Content {uid: $parent, body: 'old body'})
            WITH c
            UNWIND range(0, $n - 1) AS i
            CREATE (c)-[:HAS_CHUNK {sequence: i}]->(:ContentChunk {
                uid: $parent + ':chunk:' + toString(i), text: 'old', embedding: $vector})
            """,
            parent=parent,
            n=CHUNKS[parent],
            vector=VECTOR,
        )
    await _run(
        neo4j_driver,
        """
        MATCH (r:Resource {uid: $book})
        UNWIND range(0, $n - 1) AS i
        CREATE (r)-[:HAS_REFERENCE_CHUNK {sequence: i}]->(:ReferenceChunk {
            uid: $book + ':chunk:' + toString(i), text: 'old', embedding: $vector})
        """,
        book=BOOK,
        n=CHUNKS[BOOK],
        vector=VECTOR,
    )
    # A parent the new code already re-chunked: uid-less Content, minted chunk uids.
    await _run(
        neo4j_driver,
        """
        MATCH (e:Entity {uid: $fresh})
        CREATE (e)-[:HAS_CONTENT]->(c:Content {body: 'new body'})
        WITH c
        UNWIND range(0, size($uids) - 1) AS i
        CREATE (c)-[:HAS_CHUNK {sequence: i}]->(:ContentChunk {uid: $uids[i], embedding: $vector})
        """,
        fresh=FRESH,
        uids=[chunk_uid(ChunkStore.CONTENT, FRESH, i) for i in range(CHUNKS[FRESH])],
        vector=VECTOR,
    )
    yield
    await _clean(neo4j_driver)


async def _chunk_uids(driver: AsyncDriver) -> dict[str, list[str]]:
    rows = await _run(
        driver,
        """
        MATCH (p)-[r:HAS_CONTENT|HAS_REFERENCE_CHUNK]->(x) WHERE p.uid IN $parents
        OPTIONAL MATCH (x)-[s:HAS_CHUNK]->(k:ContentChunk)
        WITH p, CASE WHEN x:ReferenceChunk THEN x ELSE k END AS chunk,
             CASE WHEN x:ReferenceChunk THEN r.sequence ELSE s.sequence END AS sequence
        WHERE chunk IS NOT NULL
        RETURN p.uid AS parent, chunk.uid AS uid ORDER BY parent, sequence
        """,
        parents=PARENTS,
    )
    found: dict[str, list[str]] = {}
    for row in rows:
        found.setdefault(str(row["parent"]), []).append(str(row["uid"]))
    return found


def _ours(plan: Any) -> dict[str, list[str]]:
    """The planned renames for this test's parents (the shared graph holds others)."""
    return {
        label: [r.old for r in renames if r.parent in PARENTS]
        for label, renames in plan.renames.items()
    }


@pytest.mark.usefixtures("old_graph")
class TestTheRename:
    async def test_census_plans_the_old_shapes_and_leaves_the_fresh_parent(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        plan = await migration.census(neo4j_driver)

        assert plan.stops == [], plan.stops
        assert _ours(plan) == {
            "ContentChunk": sorted(
                f"{p}:chunk:{i}" for p in (STEP, ENTRY) for i in range(CHUNKS[p])
            ),
            "ReferenceChunk": [f"{BOOK}:chunk:{i}" for i in range(CHUNKS[BOOK])],
        }
        assert plan.already["ContentChunk"] >= CHUNKS[FRESH]

    async def test_confirm_renames_in_place_and_keeps_every_embedding(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        plan = await migration.census(neo4j_driver)

        renamed, cleared = await migration.migrate(neo4j_driver, plan)

        assert renamed["ReferenceChunk"] == len(plan.renames["ReferenceChunk"])
        assert cleared == plan.content_to_clear >= 2
        uids = await _chunk_uids(neo4j_driver)
        assert uids[STEP] == [chunk_uid(ChunkStore.CONTENT, STEP, i) for i in range(CHUNKS[STEP])]
        assert uids[ENTRY] == [
            chunk_uid(ChunkStore.CONTENT, ENTRY, i) for i in range(CHUNKS[ENTRY])
        ]
        assert uids[BOOK] == [chunk_uid(ChunkStore.REFERENCE, BOOK, i) for i in range(CHUNKS[BOOK])]
        assert uids[FRESH] == [
            chunk_uid(ChunkStore.CONTENT, FRESH, i) for i in range(CHUNKS[FRESH])
        ]
        kept = await _run(
            neo4j_driver,
            """
            MATCH (k) WHERE (k:ContentChunk OR k:ReferenceChunk) AND k.uid IN $uids
            RETURN count(k) AS n, count(k.embedding) AS embedded
            """,
            uids=[uid for parent_uids in uids.values() for uid in parent_uids],
        )
        assert kept[0]["n"] == kept[0]["embedded"] == sum(CHUNKS.values())
        contents = await _run(
            neo4j_driver,
            """
            MATCH (p:Entity)-[:HAS_CONTENT]->(c:Content) WHERE p.uid IN $parents
            RETURN collect(c.uid) AS uids, count(c) AS n
            """,
            parents=PARENTS,
        )
        assert contents[0]["n"] == 3 and contents[0]["uids"] == []
        assert await migration._read_back(neo4j_driver, plan) == []

    async def test_a_re_run_writes_nothing(self, neo4j_driver: AsyncDriver) -> None:
        await migration.migrate(neo4j_driver, await migration.census(neo4j_driver))

        again = await migration.census(neo4j_driver)

        assert again.stops == [] and again.writes == 0

    async def test_an_unaccounted_chunk_stops_the_run_before_any_write(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        await _run(
            neo4j_driver,
            """
            MATCH (:Entity {uid: $step})-[:HAS_CONTENT]->(:Content)-[r:HAS_CHUNK]->
                  (:ContentChunk {uid: $uid})
            SET r.sequence = 7
            """,
            step=STEP,
            uid=f"{STEP}:chunk:1",
        )
        plan = await migration.census(neo4j_driver)
        assert any(f"{STEP}:chunk:1 has sequence 7" in stop for stop in plan.stops)

        with pytest.raises(migration.CountMismatchError):
            await migration.migrate(neo4j_driver, plan)
        assert (await _chunk_uids(neo4j_driver))[STEP][0] == f"{STEP}:chunk:0"
