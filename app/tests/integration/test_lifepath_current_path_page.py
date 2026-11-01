"""
The recommendations page shows the learner's chosen path, found by the vision's search or not.
==============================================================================================

``GET /lifepath/vision/recommendations`` over the whole bootstrapped app and its graph
(``tests/integration/_activity_link_rig.py``). The learner designates a path their vision's
themes find, then revises the vision: the new themes find another path and miss theirs. A
revised vision keeps the designation (``save_vision`` writes only the User node), so the page
still shows their path, once, as "Your current path" above the recommendations, at 0%, and
says the path is theirs. A chosen path later marked draft is hidden from the search and still
shown, with no note, and its link opens the path's page.

The vision is saved through the real writer (``LifePathCoreService.save_vision``) rather than
the capture door, so no tier's theme extraction decides what the themes are.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.services.lifepath.lifepath_service import LifePathService
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import seed_published_learning_path, signed_in_client

if TYPE_CHECKING:
    import httpx

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzlpcurrent"
USER = seed_user_uid(MARK)
CHOSEN = f"lp.{MARK}.chosen"
OTHER = f"lp.{MARK}.other"
CHOSEN_TITLE = "Zzzlanternwick Crafting"
OTHER_TITLE = "Zzzquillmoss Studies"
RECOMMENDATIONS = "/lifepath/vision/recommendations"


async def _save_vision(lifepath: LifePathService, themes: list[str]) -> None:
    saved = await lifepath.core.save_vision(
        user_uid=USER, vision_statement=f"A life of {' and '.join(themes)}", vision_themes=themes
    )
    assert saved.is_ok, saved


def _header(page: str) -> str:
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.DOTALL)
    assert h1 is not None, "no page header"
    return h1.group(1).strip()


def _designate_forms(page: str) -> list[str]:
    return re.findall(r'name="life_path_uid" value="([^"]+)"', page)


async def _page(client: httpx.AsyncClient) -> str:
    response = await client.get(RECOMMENDATIONS)
    assert response.status_code == 200, response.text
    return response.text


async def test_a_chosen_path_the_revised_vision_misses_is_still_shown_once(
    skuel_app: Any,  # boundary: fasthtml-app
) -> None:
    services = skuel_app.state.services
    lifepath = services.lifepath
    assert isinstance(lifepath, LifePathService)
    async with signed_in_client(skuel_app, USER, MARK) as client:
        await seed_published_learning_path(services.neo4j_driver, CHOSEN, CHOSEN_TITLE)
        await seed_published_learning_path(services.neo4j_driver, OTHER, OTHER_TITLE)

        await _save_vision(lifepath, ["zzzlanternwick"])
        before = await _page(client)
        assert _header(before) == "Choose Your Life Path"
        assert "Your current path" not in before
        assert _designate_forms(before) == [CHOSEN]

        designated = await client.post("/api/lifepath/designate", json={"life_path_uid": CHOSEN})
        assert designated.status_code == 200, designated.text
        found = await _page(client)
        assert _header(found) == "Your Life Path"
        assert found.count(CHOSEN_TITLE) == 1
        assert "Match: 100%" in found
        assert _designate_forms(found) == []

        await _save_vision(lifepath, ["zzzquillmoss"])
        missed = await _page(client)

    assert _header(missed) == "Your Life Path"
    current = missed[missed.index("Your current path") : missed.index("Recommended Learning Paths")]
    assert re.search(rf'<a href="/lp/{re.escape(CHOSEN)}"[^>]*>{CHOSEN_TITLE}</a>', current)
    assert "Match: 0%" in current
    assert missed.count(CHOSEN_TITLE) == 1
    assert missed.count("Your current path") == 1
    assert _designate_forms(missed) == [OTHER]


async def test_a_chosen_path_now_a_draft_is_still_shown_and_its_page_opens(
    skuel_app: Any,  # boundary: fasthtml-app
) -> None:
    """The search hides a draft; the learner's own path is read by its uid, shown with no
    note, and its link leads to the path's page — the detail read has no publication gate."""
    services = skuel_app.state.services
    lifepath = services.lifepath
    assert isinstance(lifepath, LifePathService)
    async with signed_in_client(skuel_app, USER, MARK) as client:
        await seed_published_learning_path(services.neo4j_driver, CHOSEN, CHOSEN_TITLE)
        await _save_vision(lifepath, ["zzzlanternwick"])
        designated = await client.post("/api/lifepath/designate", json={"life_path_uid": CHOSEN})
        assert designated.status_code == 200, designated.text
        async with services.neo4j_driver.session() as session:
            await session.run(
                "MATCH (lp:Entity {uid: $uid}) SET lp.publication_state = 'draft'", uid=CHOSEN
            )

        page = await _page(client)
        detail = await client.get(f"/lp/{CHOSEN}/content")

    assert _header(page) == "Your Life Path"
    current = page[page.index("Your current path") : page.index("Recommended Learning Paths")]
    assert re.search(rf'<a href="/lp/{re.escape(CHOSEN)}"[^>]*>{CHOSEN_TITLE}</a>', current)
    assert "Match: 100%" in current
    assert "draft" not in page.lower()
    assert "No Matching Learning Paths" in page
    assert detail.status_code == 200, detail.text
    assert CHOSEN_TITLE in detail.text
