"""A periodic note's knowledge links, as chips on ``GET /journals/{uid}``.

An EXTRACT_ACTIVITIES note links knowledge two ways: the owner names it with
``@ku()`` / ``@link(ku:…|ps:…)``, and the grounding pass infers it. The page shows
every link to a published Ku or PathStep as a chip under the editor. Only an
inferred chip can be removed (``POST /api/user-entries/grounding/remove``): a link
the owner named is unnamed in the text, so the remove door answers it the same 404
as an absent edge and leaves it standing.

The note is a vault daily note synced through the directory door and processed at
``POST /api/user-entries/process``; the inferred link is written by the grounding
pass's own writer; the Kus and the PathStep are seeded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.entry_grounding_backend import EntryGroundingBackend
from adapters.persistence.neo4j.query.cypher.crud_queries import build_content_subtree_delete
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry import periodic_note_uid
from tests.helpers.production_backends import build_ingestion_service, build_production_backends
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import (
    edges_between,
    signed_in_client,
    touch_forward,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx
    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzentrychips"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
LEARNER_MARK = f"{MARK}l"
OTHER_MARK = f"{MARK}o"
LEARNER = seed_user_uid(f"{LEARNER_MARK}")
OTHER = seed_user_uid(f"{OTHER_MARK}")
DAY = "2026-10-14"
NOTE = periodic_note_uid("daily", LEARNER, DAY)
KU_NAMED = f"ku.{LEARNER_MARK}.named"
PS_NAMED = f"ps.{LEARNER_MARK}.named"
KU_DRAFTED = f"ku.{LEARNER_MARK}.drafted"
KU_INFERRED = f"ku.{LEARNER_MARK}.inferred"
KU_TO_REMOVE = f"ku.{LEARNER_MARK}.to-remove"


async def _seed(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        for uid, label, entity_type in (
            (KU_NAMED, "Ku", "ku"),
            (PS_NAMED, "PathStep", "path_step"),
            (KU_DRAFTED, "Ku", "ku"),
            (KU_INFERRED, "Ku", "ku"),
            (KU_TO_REMOVE, "Ku", "ku"),
        ):
            await session.run(
                f"""
                CREATE (:Entity:{label} {{uid: $uid, entity_type: $entity_type,
                                         title: $uid, status: 'active',
                                         publication_state: 'published'}})
                """,
                uid=uid,
                entity_type=entity_type,
            )


async def _cleanup(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        # A periodic note's uid carries no mark, so its tracker row goes with it.
        await session.run(
            "MATCH (u:User)-[:OWNS]->(n) WHERE u.uid IN $users "
            "MATCH (m:IngestionMetadata {entity_uid: n.uid}) DETACH DELETE m",
            users=[LEARNER, OTHER],
        )
        await session.run(
            "MATCH (u:User)-[:OWNS]->(n) WHERE u.uid IN $users "
            f"{build_content_subtree_delete('n')} DETACH DELETE n",
            users=[LEARNER, OTHER],
        )
        await session.run(
            "MATCH (n) WHERE n.uid CONTAINS $mark OR n.entity_uid CONTAINS $mark DETACH DELETE n",
            mark=MARK,
        )


class World:
    def __init__(
        self,
        driver: AsyncDriver,
        learner: httpx.AsyncClient,
        other: httpx.AsyncClient,
        grounding: EntryGroundingBackend,
    ) -> None:
        self.driver = driver
        self.learner = learner
        self.other = other
        self.grounding = grounding

    async def applies(self, far_uid: str) -> bool:
        edges = await edges_between(self.driver, NOTE, far_uid)
        return any(
            e.type == RelationshipName.APPLIES_KNOWLEDGE.value and e.source == NOTE for e in edges
        )

    async def remove(self, client: httpx.AsyncClient, ku_uid: str) -> int:
        response = await client.post(
            "/api/user-entries/grounding/remove", params={"uid": NOTE, "ku_uid": ku_uid}
        )
        return response.status_code


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(
    skuel_app: Any,  # boundary: fasthtml-app
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[World]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with (
        signed_in_client(skuel_app, LEARNER, LEARNER_MARK) as learner,
        signed_in_client(skuel_app, OTHER, OTHER_MARK) as other,
    ):
        try:
            await _seed(driver)
            vault = tmp_path_factory.mktemp("personal_vault")
            note = vault / f"{DAY}.md"
            note.write_text(
                "---\n"
                "type: user_entry\n"
                "pipeline: extract_activities\n"
                f"user_uid: {LEARNER}\n"
                "metadata:\n"
                "  entry_kind: daily\n"
                f"date: {DAY}\n"
                "---\n\n"
                f"- [ ] Read on it @context(task) @ku({KU_NAMED}) @link(ps:{PS_NAMED})\n"
                f"- [ ] Read on more @context(task) @ku({KU_DRAFTED})\n"
            )
            touch_forward(note)
            ingestion = build_ingestion_service(
                driver=driver,
                default_user_uid=UserUID(LEARNER),
                ingestion_backend=build_production_backends(driver)["ingestion_backend"],
                user_entry_service=skuel_app.state.services.user_entry,
            )
            synced = await ingestion.ingest_directory(vault, ingestion_mode="smart")
            assert synced.is_ok and not synced.value.errors, synced
            processed = await learner.post(
                "/api/user-entries/process",
                json={"uid": NOTE, "pipeline": "extract_activities"},
            )
            assert processed.status_code == 200, processed.text

            grounding = build_production_backends(driver)["entry_grounding_backend"]
            for ku_uid in (KU_INFERRED, KU_TO_REMOVE):
                written = await grounding.write_applies_knowledge(NOTE, ku_uid, 0.74)
                assert written.is_ok and written.value is True, (ku_uid, written)
            # A named link whose Ku has since become a draft.
            async with driver.session() as session:
                await session.run(
                    "MATCH (k:Ku {uid: $uid}) SET k.publication_state = 'draft'", uid=KU_DRAFTED
                )
            world = World(driver, learner, other, grounding)
            for uid in (KU_NAMED, PS_NAMED, KU_DRAFTED, KU_INFERRED, KU_TO_REMOVE):
                assert await world.applies(uid), uid
            yield world
        finally:
            await _cleanup(driver)


async def test_the_page_shows_each_published_link_as_a_chip(world: World) -> None:
    response = await world.learner.get(f"/journals/{NOTE}")

    assert response.status_code == 200, response.text
    html = response.text
    assert "Knowledge in this note" in html
    assert f'href="/explore/ku/{KU_NAMED}"' in html
    assert f'href="/explore/ps/{PS_NAMED}"' in html
    assert f'href="/explore/ku/{KU_INFERRED}"' in html
    # A draft is unfinished curriculum: no chip, though the link stands.
    assert f'href="/explore/ku/{KU_DRAFTED}"' not in html


async def test_only_an_inferred_chip_carries_a_remove_button(world: World) -> None:
    html = (await world.learner.get(f"/journals/{NOTE}")).text

    assert f"ku_uid={KU_INFERRED}" in html
    assert f"ku_uid={KU_NAMED}" not in html
    assert f"ku_uid={PS_NAMED}" not in html


async def test_the_remove_door_refuses_a_named_link_like_an_absent_one(world: World) -> None:
    named = await world.remove(world.learner, KU_NAMED)
    absent = await world.remove(world.learner, f"ku.{LEARNER_MARK}.never-linked")

    assert named == absent == 404
    assert await world.applies(KU_NAMED)


async def test_another_user_cannot_remove_an_inferred_link(world: World) -> None:
    assert await world.remove(world.other, KU_TO_REMOVE) == 404
    assert await world.applies(KU_TO_REMOVE)
    assert (await world.other.get(f"/journals/{NOTE}")).status_code == 404


async def test_the_owner_removes_an_inferred_link(world: World) -> None:
    assert await world.remove(world.learner, KU_TO_REMOVE) == 200

    assert not await world.applies(KU_TO_REMOVE)
    html = (await world.learner.get(f"/journals/{NOTE}")).text
    assert f'href="/explore/ku/{KU_TO_REMOVE}"' not in html
    # Control: the page still shows the chips that stand.
    assert f'href="/explore/ku/{KU_INFERRED}"' in html
