"""A uid that names no PathStep reads as not found, never as a database failure.

``PsCoreService.get_step`` reads through ``PsBackend.get_step_with_knowledge``, which
matches the ``PathStep`` label. A uid naming a node of another kind (a Task, a Ku) is
None to it, so each door it serves answers 404 for that uid, as it does for a uid that
names nothing. The ``PathStep`` constructor refuses a node of another kind (G6), so the
label is what keeps such a uid from reading as a database error (503).

The three readers: ``GET /api/path-steps/prerequisites``, ``POST /api/pathways/progress``
and ``LpService.get_step`` (the progress door's own read). A published step is the
control at each: found, and answered past the existence gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from adapters.inbound.fasthtml_types import FastHTMLApp
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import (
    create,
    seed_published_path_step,
    signed_in_client,
)

if TYPE_CHECKING:
    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

READER = seed_user_uid("psgetstep_reader")
MARK = "psgetstep"
STEP = "ps.psgetstep.step"
KU = "ku.psgetstep.concept"
NOTHING = "ps.psgetstep.nothing"


async def _seed_ku(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (k:Entity:Ku {uid: $uid})
            SET k.title = 'A concept', k.entity_type = 'ku', k.status = 'active',
                k.publication_state = 'published'
            """,
            uid=KU,
        )


async def test_each_reader_answers_not_found_for_a_uid_of_another_kind(
    skuel_app: FastHTMLApp,
) -> None:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    lp_service = skuel_app.state.services.lp
    assert lp_service is not None
    async with signed_in_client(skuel_app, READER, MARK) as client:
        task = await create(client, "tasks", "Not a step")
        await _seed_ku(driver)
        await seed_published_path_step(driver, STEP, "A step")

        for uid in (task, KU, NOTHING):
            prerequisites = await client.get(
                "/api/path-steps/prerequisites", params={"step_uid": uid}
            )
            assert prerequisites.status_code == 404, (uid, prerequisites.text)
            progress = await client.post(
                "/api/pathways/progress", json={"step_uid": uid, "mastery_level": 0.5}
            )
            assert progress.status_code == 404, (uid, progress.text)
            read = await lp_service.get_step(uid)
            assert read.is_ok, (uid, read)
            assert read.value is None, uid

        # The control: the step itself is found by all three.
        prerequisites = await client.get("/api/path-steps/prerequisites", params={"step_uid": STEP})
        assert prerequisites.status_code == 200, prerequisites.text
        # Found, then refused for what the step lacks: it names no knowledge to record.
        progress = await client.post(
            "/api/pathways/progress", json={"step_uid": STEP, "mastery_level": 0.5}
        )
        assert progress.status_code == 400, progress.text
        assert "no associated knowledge units" in progress.json()["message"]
        read = await lp_service.get_step(STEP)
        assert read.is_ok and read.value is not None
        assert read.value.uid == STEP
