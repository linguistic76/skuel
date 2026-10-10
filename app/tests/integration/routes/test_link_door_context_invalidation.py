"""A link made or removed at a link door reaches the owner's cached context at once.

The rich context is cached for five minutes, and every link-derived field reads the
link edges — the goals a principle supports among them. A link door writes those edges
through ``UnifiedRelationshipService``, which announces each write and each removal
(``EntityLinksChanged``); the bootstrap subscribes that to an immediate context
invalidation — no debounce, since the page that made the link reads the context right
back. So when ``POST /api/goals/link-principle`` answers, the cached context is already
dropped, and the next rich read — and the Insights synergies card that reads it — names
the link, inside the cache's five minutes.

The app runs bootstrapped over its own graph; the routes are the ones the bootstrap
wires (``tests/integration/_activity_link_rig.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums import HubQuestion
from core.models.type_hints import UserUID
from tests.integration._activity_link_rig import create, signed_in_client

if TYPE_CHECKING:
    import httpx

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzlinkcache"
CALLER = f"user_{MARK}"


async def _supported_goals(services: Any, principle: str) -> list[str]:  # boundary: Services
    context = await services.user.get_rich_unified_context(UserUID(CALLER))
    assert context.is_ok, context
    return list(context.value.principle_supported_goals.get(principle, []))


def _dropped(services: Any) -> bool:  # boundary: Services
    """Whether the cached context is gone — read with no wait after the write answered."""
    return services.user.activity.get_valid_context(UserUID(CALLER)) is None


async def _synergies_card(client: httpx.AsyncClient) -> str:
    card = await client.get(HubQuestion.SYNERGIES.fragment_url())
    assert card.status_code == 200, card.text[:300]
    return card.text


async def test_a_link_and_its_removal_reach_the_cached_context(skuel_app: Any) -> None:
    services = skuel_app.state.services
    async with signed_in_client(skuel_app, CALLER, MARK) as client:
        principle = await create(client, "principles", f"{MARK} steady principle")
        goal = await create(client, "goals", f"{MARK} guided goal")
        # The context is now cached, without the link.
        assert await _supported_goals(services, principle) == []
        assert f"{MARK} steady principle" not in await _synergies_card(client)

        linked = await client.post(
            "/api/goals/link-principle", json={"goal_uid": goal, "principle_uid": principle}
        )
        assert linked.status_code == 200, linked.text
        assert _dropped(services)

        assert await _supported_goals(services, principle) == [goal]
        assert f"{MARK} steady principle" in await _synergies_card(client)

        removed = await services.goals.unlink_goal_from_principle(goal, principle)
        assert removed.is_ok, removed
        assert _dropped(services)

        assert await _supported_goals(services, principle) == []
