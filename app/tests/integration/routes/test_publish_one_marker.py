"""A PathStep is published by its vault file's ``publication_state`` alone (ADR-091 S7).

The content vault is the one door for curriculum, and publishing is one marker in it:
a file synced with ``publication_state: draft`` is withheld from the learner's
PathStep catalogue, and the same file re-synced with ``publication_state: published``
is listed. There is no in-app publish door: the two routes that once wrote a
PathStep's ``status`` (``POST /api/ps/{uid}/publish`` and
``POST /explore/ps/{uid}/publish``, with the ``publish-state`` fragment beside it)
answer as routes that do not exist, even to a teacher, and write nothing.

The step is made by a real sync of a real file; the learner and the teacher read and
post through the bootstrapped app's routes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.integration._activity_link_rig import signed_in_client, sync_vault, touch_forward

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzpubmarker"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
LEARNER_MARK = f"{MARK}l"
TEACHER_MARK = f"{MARK}t"
LEARNER = f"user_{LEARNER_MARK}"
TEACHER = f"user_{TEACHER_MARK}"
STEP = f"ps.{LEARNER_MARK}.switch"
STEP_TITLE = f"{MARK} switch step"
CATALOGUE = "/path-steps/content"


def _write_step(vault: Path, publication_state: str) -> None:
    """The step's content-vault file, marked ``publication_state``."""
    path = vault / "ps_publish-switch.md"
    path.write_text(
        "---\n"
        "type: path_step\n"
        f"uid: {STEP}\n"
        f"title: {STEP_TITLE}\n"
        # First in the catalogue's sequence order, so its page of 50 always holds it.
        "sequence: 1\n"
        f"publication_state: {publication_state}\n"
        "---\n\nA step about the one publish switch.\n"
    )
    touch_forward(path)


async def _set_role(driver: AsyncDriver, uid: str, role: str) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (u:User {uid: $uid})
            SET u.username = $uid, u.display_name = $uid, u.email = $uid + '@example.com',
                u.role = $role, u.created_at = datetime(), u.updated_at = datetime()
            """,
            uid=uid,
            role=role,
        )


async def _step_status(driver: AsyncDriver) -> tuple[str | None, str | None]:
    """The step's stored ``status`` and ``publication_state``."""
    async with driver.session() as session:
        record = await (
            await session.run(
                "MATCH (s:Entity:PathStep {uid: $uid}) "
                "RETURN s.status AS status, s.publication_state AS publication_state",
                uid=STEP,
            )
        ).single()
    assert record is not None, STEP
    return record["status"], record["publication_state"]


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def clients(
    skuel_app: Any,  # boundary: fasthtml-app
) -> AsyncIterator[dict[str, Any]]:  # boundary: httpx clients and the driver
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with (
        signed_in_client(skuel_app, LEARNER, LEARNER_MARK) as learner,
        signed_in_client(skuel_app, TEACHER, TEACHER_MARK) as teacher,
    ):
        await _set_role(driver, LEARNER, "member")
        await _set_role(driver, TEACHER, "teacher")
        yield {"learner": learner, "teacher": teacher, "driver": driver}


async def test_the_vault_marker_hides_and_publishes_a_step(clients, tmp_path) -> None:
    driver: AsyncDriver = clients["driver"]
    learner = clients["learner"]

    _write_step(tmp_path, "draft")
    await sync_vault(driver, tmp_path)
    assert await _step_status(driver) == ("active", "draft")
    hidden = await learner.get(CATALOGUE)
    assert hidden.status_code == 200
    assert STEP_TITLE not in hidden.text

    # Positive control: the same file, re-synced as published, is listed.
    _write_step(tmp_path, "published")
    await sync_vault(driver, tmp_path)
    assert await _step_status(driver) == ("active", "published")
    listed = await learner.get(CATALOGUE)
    assert listed.status_code == 200
    assert STEP_TITLE in listed.text


async def test_no_in_app_door_publishes_a_step(clients, tmp_path) -> None:
    driver: AsyncDriver = clients["driver"]
    teacher = clients["teacher"]

    _write_step(tmp_path, "draft")
    await sync_vault(driver, tmp_path)

    for method, path in (
        ("POST", f"/api/ps/{STEP}/publish"),
        ("POST", f"/explore/ps/{STEP}/publish"),
        ("GET", f"/explore/ps/{STEP}/publish-state"),
    ):
        response = await teacher.request(method, path)
        assert response.status_code in (404, 405), (method, path, response.status_code)

    # Nothing was written: the step is the draft the vault made it.
    assert await _step_status(driver) == ("active", "draft")

    # Positive control: the same client reaches a live door of the same family — the
    # step's engagement read — so a refusal above is the route's absence, not the
    # client's.
    actions = await teacher.get(f"/explore/ps/{STEP}/engagement-actions")
    assert actions.status_code == 200
    assert 'id="ps-engagement-actions"' in actions.text
