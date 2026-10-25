"""An entry's knowledge links, as chips on the owner's ``GET /gradebook/{uid}``.

The grounding pass reads knowledge notes and activity notes
(``Pipeline.grounds_knowledge``); the owner's page for such an entry shows its
links to published curriculum as chips under the submission card, the same chips
and the same read as ``/journals/{uid}``: only an inferred chip carries a remove button.
A recipient the entry is shared with opens the recipient card, which never shows
them; an entry on any other pipeline shows none, whatever links it holds. A
periodic note on either grounded pipeline shows them on ``/journals/{uid}`` too.

The notes are vault files synced through the directory door (the daily note then
processed at ``POST /api/user-entries/process``), the share is the owner's
``POST /api/user-entries/{uid}/share``, the inferred links are written by the
grounding pass's own writer and the plain entry's link by the ``@ku`` writer; the
Kus and the group are seeded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.query.cypher.crud_queries import build_content_subtree_delete
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry import periodic_note_uid
from core.utils.result_simplified import Errors, Result
from tests.helpers.production_backends import build_ingestion_service, build_production_backends
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import (
    edges_between,
    signed_in_client,
    touch_forward,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    import httpx
    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzgbchips"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
LEARNER_MARK = f"{MARK}l"
OTHER_MARK = f"{MARK}o"
LEARNER = seed_user_uid(f"{LEARNER_MARK}")
OTHER = seed_user_uid(f"{OTHER_MARK}")
GROUP = f"group.{LEARNER_MARK}-class"
DAY = "2026-10-14"
KNOWLEDGE_DAY = "2026-10-15"
ACTIVITY_NOTE = periodic_note_uid("daily", LEARNER, DAY)
PERIODIC_KNOWLEDGE_NOTE = periodic_note_uid("daily", LEARNER, KNOWLEDGE_DAY)
KNOWLEDGE_NOTE = f"ue.{LEARNER_MARK}.knowledge"
PLAIN_ENTRY = f"ue.{LEARNER_MARK}.plain"
KU_NAMED = f"ku.{LEARNER_MARK}.named"
KU_INFERRED = f"ku.{LEARNER_MARK}.inferred"
KU_KNOWLEDGE = f"ku.{LEARNER_MARK}.knowledge"
KU_PLAIN = f"ku.{LEARNER_MARK}.plain"


def _note(*frontmatter: str, body: str = "") -> str:
    return "---\n" + "\n".join(frontmatter) + f"\nuser_uid: {LEARNER}\n---\n\n{body}"


def _write_vault(vault: Path) -> None:
    files = {
        f"{DAY}.md": _note(
            "type: user_entry",
            "title: Monday",
            "pipeline: extract_activities",
            "metadata:\n  entry_kind: daily",
            f"date: {DAY}",
            body=f"- [ ] Read on it @context(task) @ku({KU_NAMED})\n",
        ),
        f"{KNOWLEDGE_DAY}.md": _note(
            "type: user_entry",
            "title: Tuesday",
            "pipeline: knowledge",
            "metadata:\n  entry_kind: daily",
            f"date: {KNOWLEDGE_DAY}",
            body="What I noticed about attention today.\n",
        ),
        "knowledge.md": _note(
            "type: user_entry",
            f"uid: {KNOWLEDGE_NOTE}",
            "title: How I keep a habit",
            "pipeline: knowledge",
            body="A cue, a routine, a reward.\n",
        ),
        "plain.md": _note(
            "type: user_entry",
            f"uid: {PLAIN_ENTRY}",
            "title: A plain entry",
            "pipeline: none",
            body="Nothing to ground here.\n",
        ),
    }
    for name, text in files.items():
        path = vault / name
        path.write_text(text)
        touch_forward(path)


async def _seed(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        for uid in (KU_NAMED, KU_INFERRED, KU_KNOWLEDGE, KU_PLAIN):
            await session.run(
                """
                CREATE (:Entity:Ku {uid: $uid, entity_type: 'ku', title: $uid,
                                    status: 'active', publication_state: 'published'})
                """,
                uid=uid,
            )
        await session.run(
            """
            MATCH (learner:User {uid: $learner}), (other:User {uid: $other})
            CREATE (g:Group {uid: $group, name: 'Class', is_active: true})
            CREATE (learner)-[:MEMBER_OF {role: 'student'}]->(g),
                   (other)-[:MEMBER_OF {role: 'student'}]->(g)
            """,
            learner=LEARNER,
            other=OTHER,
            group=GROUP,
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
        skuel_app: Any,  # boundary: fasthtml-app
        learner: httpx.AsyncClient,
        other: httpx.AsyncClient,
    ) -> None:
        self.skuel_app = skuel_app
        self.driver: AsyncDriver = skuel_app.state.services.neo4j_driver
        self.learner = learner
        self.other = other

    async def applies(self, entry_uid: str, ku_uid: str) -> bool:
        edges = await edges_between(self.driver, entry_uid, ku_uid)
        return any(
            e.type == RelationshipName.APPLIES_KNOWLEDGE.value and e.source == entry_uid
            for e in edges
        )


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
            _write_vault(vault)
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
                json={"uid": ACTIVITY_NOTE, "pipeline": "extract_activities"},
            )
            assert processed.status_code == 200, processed.text

            grounding = build_production_backends(driver)["entry_grounding_backend"]
            for entry_uid, ku_uid in (
                (ACTIVITY_NOTE, KU_INFERRED),
                (KNOWLEDGE_NOTE, KU_KNOWLEDGE),
                (PERIODIC_KNOWLEDGE_NOTE, KU_KNOWLEDGE),
            ):
                written = await grounding.write_applies_knowledge(entry_uid, ku_uid, 0.74)
                assert written.is_ok and written.value is True, (entry_uid, ku_uid, written)
            # A link the grounding pass never writes on this pipeline: the owner's.
            linked = await skuel_app.state.services.user_entry.backend.write_applied_knowledge(
                PLAIN_ENTRY, KU_PLAIN
            )
            assert linked.is_ok and linked.value is not None, linked

            for entry_uid in (KNOWLEDGE_NOTE, ACTIVITY_NOTE):
                shared = await learner.post(
                    f"/api/user-entries/{entry_uid}/share", json={"audience": [f"group:{GROUP}"]}
                )
                assert shared.status_code == 200, shared.text

            world = World(skuel_app, learner, other)
            for entry_uid, ku_uid in (
                (ACTIVITY_NOTE, KU_NAMED),
                (ACTIVITY_NOTE, KU_INFERRED),
                (KNOWLEDGE_NOTE, KU_KNOWLEDGE),
                (PERIODIC_KNOWLEDGE_NOTE, KU_KNOWLEDGE),
                (PLAIN_ENTRY, KU_PLAIN),
            ):
                assert await world.applies(entry_uid, ku_uid), (entry_uid, ku_uid)
            yield world
        finally:
            await _cleanup(driver)


async def test_the_owner_sees_a_knowledge_notes_chips(world: World) -> None:
    response = await world.learner.get(f"/gradebook/{KNOWLEDGE_NOTE}")

    assert response.status_code == 200, response.text
    html = response.text
    assert "Knowledge in this note" in html
    assert f'href="/explore/ku/{KU_KNOWLEDGE}"' in html
    assert f"ku_uid={KU_KNOWLEDGE}" in html


async def test_an_activity_note_shows_both_writers_links_and_only_the_inferred_one_has_a_remove_button(
    world: World,
) -> None:
    html = (await world.learner.get(f"/gradebook/{ACTIVITY_NOTE}")).text

    assert f'href="/explore/ku/{KU_NAMED}"' in html
    assert f'href="/explore/ku/{KU_INFERRED}"' in html
    assert f"ku_uid={KU_INFERRED}" in html
    assert f"ku_uid={KU_NAMED}" not in html


async def test_a_recipient_card_never_shows_the_chips(world: World) -> None:
    for entry_uid, ku_uid in ((KNOWLEDGE_NOTE, KU_KNOWLEDGE), (ACTIVITY_NOTE, KU_INFERRED)):
        response = await world.other.get(f"/gradebook/{entry_uid}")

        # Control: the share admits the recipient to the card.
        assert response.status_code == 200, response.text
        html = response.text
        assert "Shared with you" in html
        assert "Knowledge in this note" not in html
        assert f'href="/explore/ku/{ku_uid}"' not in html


async def test_an_entry_on_a_pipeline_that_does_not_ground_shows_no_chips(world: World) -> None:
    response = await world.learner.get(f"/gradebook/{PLAIN_ENTRY}")

    assert response.status_code == 200, response.text
    html = response.text
    # Control: the owner's page rendered, and the link it does not show stands.
    assert "A plain entry" in html
    assert await world.applies(PLAIN_ENTRY, KU_PLAIN)
    assert "Knowledge in this note" not in html
    assert f'href="/explore/ku/{KU_PLAIN}"' not in html


async def test_a_failed_read_is_said_not_shown_as_no_links(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fail(entry_uid: str, user_uid: UserUID) -> Result[list[Any]]:
        return Result.fail(Errors.database(operation="get_entry_knowledge_chips", message="down"))

    monkeypatch.setattr(
        world.skuel_app.state.services.user_entry, "list_entry_knowledge_chips", _fail
    )
    html = (await world.learner.get(f"/gradebook/{KNOWLEDGE_NOTE}")).text

    assert "knowledge links." in html and "Could not load this note" in html
    assert f'href="/explore/ku/{KU_KNOWLEDGE}"' not in html


async def test_a_periodic_knowledge_note_shows_its_chips_on_the_journal_page(world: World) -> None:
    response = await world.learner.get(f"/journals/{PERIODIC_KNOWLEDGE_NOTE}")

    assert response.status_code == 200, response.text
    html = response.text
    assert f'href="/explore/ku/{KU_KNOWLEDGE}"' in html
    assert f"ku_uid={KU_KNOWLEDGE}" in html
