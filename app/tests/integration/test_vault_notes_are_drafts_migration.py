"""The PR 8 migration's classification, against a real Neo4j (Submit & Share arc R9).

``scripts/migrations/vault_notes_are_drafts_2026_09.py`` retracts audience
links from LIVING vault notes and moves the old provenance key onto
``submitted_from_uid``. A frozen submission that carries a ``vault_file_path``
— a turn-in (snapshot or edge), a filed copy, a ``teacher_review`` node — is
never a living note: its links are the audience it was handed to and must
survive ``--confirm``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from tests.helpers.seed_uids import seed_user_uid

SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts/migrations/vault_notes_are_drafts_2026_09.py"
)
OWNER = seed_user_uid("drafts_migration")
READER = seed_user_uid("drafts_migration_reader")
GROUP = "group.drafts-migration"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vault_notes_are_drafts", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _vault(path: str) -> str:
    return json.dumps({"vault_file_path": f"/vault/{path}"})


@pytest.fixture
async def seeded(clean_neo4j, neo4j_driver) -> None:
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (o:User {uid: $owner})
            MERGE (r:User {uid: $reader})
            MERGE (g:Group {uid: $group}) SET g.is_active = true
            CREATE (ex:Entity:Exercise {uid: 'ex.drafts-migration', entity_type: 'exercise'})
            CREATE (living:Entity:UserEntry {uid: 'ue.living', entity_type: 'user_entry',
                pipeline: 'knowledge', metadata: $living_meta})
            CREATE (turn_in:Entity:UserEntry {uid: 'ue.vault-turn-in', entity_type: 'user_entry',
                pipeline: 'llm_summary', metadata: $turn_in_meta})
            CREATE (review:Entity:UserEntry {uid: 'ue.vault-review', entity_type: 'user_entry',
                pipeline: 'teacher_review', metadata: $review_meta})
            CREATE (copy:Entity:UserEntry {uid: 'ue.old-copy', entity_type: 'user_entry',
                pipeline: 'teacher_review', metadata: $copy_meta})
            MERGE (o)-[:OWNS]->(living)
            MERGE (o)-[:OWNS]->(turn_in)
            MERGE (o)-[:OWNS]->(review)
            MERGE (o)-[:OWNS]->(copy)
            MERGE (living)-[:SHARED_WITH_GROUP]->(g)
            MERGE (r)-[:SHARES_WITH]->(living)
            MERGE (turn_in)-[:FULFILLS_EXERCISE {revision: 1}]->(ex)
            MERGE (turn_in)-[:SHARED_WITH_GROUP]->(g)
            MERGE (r)-[:SHARES_WITH]->(turn_in)
            MERGE (review)-[:SUBMITTED_TO_GROUP]->(g)
            """,
            owner=OWNER,
            reader=READER,
            group=GROUP,
            living_meta=_vault("knowledge/note.md"),
            turn_in_meta=_vault("knowledge/turned-in.md"),
            review_meta=_vault("knowledge/for-review.md"),
            copy_meta=json.dumps({"submitted_from_entry": "ue.living", "keep": "me"}),
        )


async def _links(neo4j_driver, uid: str) -> int:
    async with neo4j_driver.session() as session:
        row = await (
            await session.run(
                """
                MATCH (e:Entity {uid: $uid})
                RETURN COUNT { (e)-[:SHARED_WITH_GROUP|SUBMITTED_TO_GROUP]->() }
                     + COUNT { ()-[:SHARES_WITH]->(e) } AS n
                """,
                uid=uid,
            )
        ).single()
    assert row is not None
    return int(row["n"])


@pytest.mark.asyncio
async def test_confirm_retracts_living_links_only_and_moves_the_key(seeded, neo4j_driver) -> None:
    migration = _load()

    census = await migration._census(neo4j_driver)
    assert {(r["uid"], r["kind"]) for r in census.share_links} == {
        ("ue.living", "SHARED_WITH_GROUP"),
        ("ue.living", "SHARES_WITH"),
    }, "only the living note's links are retraction candidates"
    assert census.feedback_requests == [], "a teacher_review vault node is frozen, not a STOP"
    assert {r["uid"] for r in census.frozen_vault_entries} == {
        "ue.vault-turn-in",
        "ue.vault-review",
    }
    assert [r["uid"] for r in census.old_keys] == ["ue.old-copy"]

    assert await migration._move_keys(neo4j_driver, census.old_keys) == []
    assert await migration._retract(neo4j_driver, census.share_links) == []

    assert await _links(neo4j_driver, "ue.living") == 0
    assert await _links(neo4j_driver, "ue.vault-turn-in") == 2, "a turn-in keeps its audience"
    assert await _links(neo4j_driver, "ue.vault-review") == 1, "a feedback request stands"
    async with neo4j_driver.session() as session:
        copy = await (
            await session.run(
                "MATCH (c:Entity {uid: 'ue.old-copy'}) "
                "RETURN c.submitted_from_uid AS from_uid, c.metadata AS metadata"
            )
        ).single()
    assert copy is not None
    assert copy["from_uid"] == "ue.living"
    assert json.loads(copy["metadata"]) == {"keep": "me"}

    after = await migration._census(neo4j_driver)
    assert after.clean
