"""A task's inferred knowledge on its detail page, over the bootstrapped app (CORE tier).

The task is created at the real create door with one link its owner names; the
grounding pass's own writer (``TaskGroundingBackend.write_applies_knowledge``) adds
``APPLIES_KNOWLEDGE {inferred: true}`` to a second Ku. The page's Connections section
(``GET /tasks/detail/content``) marks only the inferred link and carries its remove;
that control's request, sent as htmx sends it, removes the link at the real door
(``POST /api/tasks/grounding/remove``) and is answered with the section, which the
page then shows with only the owner's link. The page is its owner's alone: another
user's read of it is refused.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import create, signed_in_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx
    from neo4j import AsyncDriver

    from adapters.inbound.fasthtml_types import FastHTMLApp
    from services_bootstrap import Services

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "taskgroundpage"
OWNER = seed_user_uid(f"{MARK}_owner")
STRANGER = seed_user_uid(f"{MARK}_stranger")
KU_NAMED = f"ku.{MARK}.named"
KU_INFERRED = f"ku.{MARK}.inferred"
NAMED_TITLE = "Named by the owner"
INFERRED_TITLE = "Inferred by grounding"
REMOVE = re.compile(r"<button[^>]*data-inferred-link-remove[^>]*>")


@dataclass(frozen=True)
class Env:
    client: httpx.AsyncClient
    stranger: httpx.AsyncClient
    services: Services
    driver: AsyncDriver


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(skuel_app: FastHTMLApp) -> AsyncIterator[Env]:
    services: Services = skuel_app.state.services
    driver: AsyncDriver = services.neo4j_driver
    async with (
        signed_in_client(skuel_app, OWNER, MARK) as client,
        signed_in_client(skuel_app, STRANGER, f"{MARK}stranger") as stranger,
    ):
        async with driver.session() as session:
            await session.run(
                """
                UNWIND $kus AS ku
                MERGE (k:Entity:Ku {uid: ku.uid})
                SET k.title = ku.title, k.entity_type = 'ku',
                    k.publication_state = 'published'
                """,
                kus=[
                    {"uid": KU_NAMED, "title": NAMED_TITLE},
                    {"uid": KU_INFERRED, "title": INFERRED_TITLE},
                ],
            )
        yield Env(client=client, stranger=stranger, services=services, driver=driver)


async def _task_with_both_links(env: Env) -> str:
    task = await create(
        env.client, "tasks", f"{MARK} notice the breath", applies_knowledge_uids=[KU_NAMED]
    )
    grounding = env.services.task_grounding
    assert grounding is not None
    written = await grounding.backend.write_applies_knowledge(task, KU_INFERRED, 0.82)
    assert written.is_ok and written.value, written
    return task


def _attribute(tag: str, name: str) -> str:
    match = re.search(rf'{name}="([^"]*)"', tag)
    assert match is not None, (name, tag)
    return match.group(1).replace("&amp;", "&")


def _row_of(html: str, title: str) -> str:
    """The Connections row carrying ``title``."""
    start = html.rindex("<li", 0, html.index(f">{title}<"))
    return html[start : html.index("</li>", start)]


async def _page(env: Env, task: str) -> str:
    response = await env.client.get("/tasks/detail/content", params={"uid": task})
    assert response.status_code == 200, response.text
    return response.text


async def test_the_page_marks_only_the_inferred_link_and_its_remove_takes_it(env: Env) -> None:
    task = await _task_with_both_links(env)

    page = await _page(env, task)
    assert "inferred" not in _row_of(page, NAMED_TITLE)
    assert REMOVE.search(_row_of(page, NAMED_TITLE)) is None
    assert "inferred · 82%" in _row_of(page, INFERRED_TITLE)
    buttons = REMOVE.findall(page)
    assert len(buttons) == 1
    button = buttons[0]
    target = _attribute(button, "hx-target")
    assert f'id="{target.removeprefix("#")}"' in page

    # The control's request, as htmx sends it.
    removed = await env.client.post(_attribute(button, "hx-post"), headers={"HX-Request": "true"})

    assert removed.status_code == 200, removed.text
    assert removed.text.lstrip().startswith(f'<div id="{target.removeprefix("#")}"')
    assert NAMED_TITLE in removed.text
    assert INFERRED_TITLE not in removed.text
    assert REMOVE.search(removed.text) is None
    after = await _page(env, task)
    assert NAMED_TITLE in after
    assert INFERRED_TITLE not in after
    assert REMOVE.search(after) is None

    # Sent again (a page left open), the door refuses and htmx swaps nothing: the
    # page's toast reads the message.
    again = await env.client.post(_attribute(button, "hx-post"), headers={"HX-Request": "true"})
    assert again.status_code == 404
    assert again.headers["X-Toast-Type"] == "error"
    assert again.headers["X-Toast-Message"] == (
        f"Task knowledge link not found: {task} -> {KU_INFERRED}"
    )


async def test_another_users_read_of_the_page_is_refused(env: Env) -> None:
    task = await _task_with_both_links(env)

    foreign = await env.stranger.get("/tasks/detail/content", params={"uid": task})

    assert foreign.status_code == 404
    assert INFERRED_TITLE not in foreign.text
    assert NAMED_TITLE not in foreign.text
    assert REMOVE.search(foreign.text) is None
