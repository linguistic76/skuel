"""Through the ask door: an engaged step that does not read gives way to a readable step in progress.

The steps go in through the content-vault door, as the vault writes them; one value is then
set around the ingestion gate, the way a stray stored value arrives. The learner is engaged
with the step that does not read and has the other in progress unengaged. Askesis guides on
the step that reads and closes its answer by naming the one it could not open.

Requires the live OpenAI API (FULL tier): the guided answer is generated.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from adapters.inbound.fasthtml_types import FastHTMLApp
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.helpers.ingestion_owner import INGESTION_TEST_OWNER
from tests.helpers.production_backends import build_ingestion_service
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import signed_in_client

pytestmark = pytest.mark.skipif(
    not get_credential("OPENAI_API_KEY") or not IntelligenceTier.from_env().ai_enabled,
    reason="Requires OPENAI_API_KEY (env or keychain) and INTELLIGENCE_TIER=full for Askesis tests",
)

_MARK = "askesis-unopened-step"
_UNREADABLE = "ps.test.unopened-noticing"
_READABLE = "ps.test.unopened-naming"
_STEPS = {_UNREADABLE: "Noticing A Feeling", _READABLE: "Naming A Feeling"}


@pytest_asyncio.fixture
async def two_steps_in_the_graph(skuel_app: FastHTMLApp, tmp_path: Path) -> AsyncIterator[None]:
    """Both steps ingested through the content-vault door, removed after the test."""
    driver = skuel_app.state.services.neo4j_driver
    ingestion = build_ingestion_service(driver=driver, default_user_uid=INGESTION_TEST_OWNER)
    for uid, title in _STEPS.items():
        path = tmp_path / f"{uid}.md"
        path.write_text(
            "---\n"
            "type: path_step\n"
            f"uid: {uid}\n"
            f"title: {title}\n"
            "learning_level: beginner\n"
            f"intent: Practise {title.lower()}\n"
            "publication_state: published\n"
            "---\n\nA short step about a feeling.\n",
            encoding="utf-8",
        )
        assert (await ingestion.ingest_file(path)).is_ok
    yield
    async with driver.session() as session:
        await session.run(
            "MATCH (ps:Entity) WHERE ps.uid IN $uids DETACH DELETE ps", uids=list(_STEPS)
        )


@pytest.mark.stores_unreadable_value("the step whose learning_level its enum refuses")
async def test_the_ask_door_guides_on_the_readable_step_and_names_the_one_it_could_not_open(
    skuel_app: FastHTMLApp, two_steps_in_the_graph: None
) -> None:
    services = skuel_app.state.services
    user_uid = seed_user_uid("askesis_unopened_step")
    async with signed_in_client(skuel_app, user_uid, _MARK) as http:
        async with services.neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (u:User {uid: $user_uid})
                SET u.role = 'MEMBER'
                WITH u
                MATCH (ps:Entity:PathStep) WHERE ps.uid IN $steps
                MERGE (u)-[:IN_PROGRESS]->(ps)
                """,
                user_uid=user_uid,
                steps=list(_STEPS),
            )
            await session.run(
                """
                MATCH (u:User {uid: $user_uid}), (ps:Entity:PathStep {uid: $unreadable})
                MERGE (u)-[r:ENGAGED_WITH]->(ps)
                SET r.uid = $engagement_uid, r.state = 'engaged', r.since = datetime()
                SET ps.learning_level = 'expertish'
                """,
                user_uid=user_uid,
                unreadable=_UNREADABLE,
                engagement_uid="eng_7e57a5ce515e0001",
            )
        await services.user.activity.invalidate_context(user_uid, immediate=True)

        response = await http.get(
            "/api/askesis/ask", params={"question": "Explain the concept I'm learning right now"}
        )
        # The answer's conversation turns are written in the background; let them land
        # before the rig removes the learner.
        await asyncio.gather(*services.askesis.query_processor._background_tasks)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "guided", body
    assert body["guidance_mode"]
    assert body["answer"].endswith(
        "I couldn't open your step \"Noticing A Feeling\" just now, so I'm working from "
        '"Naming A Feeling".'
    ), body["answer"][-300:]
