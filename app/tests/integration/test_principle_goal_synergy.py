"""
The principle→goal synergy a built UserContext answers — method 6's ``principle_goal``.
=====================================================================================

A principle guides the goals it ``SUPPORTS_GOAL`` (both link doors write that one
edge, ADR-090). The rich build reads the edge into ``principle_supported_goals`` and
each principle's ``strength`` into ``principle_priorities``; the synergy detector
pairs a principle only with the still-active goals it supports.

The learner:

    P_LINKED   strength core       -> G_LEARN (goal's door), G_OUTCOME (principle's door),
                                      G_DONE (linked, then completed)
    P_NONE     strength exploring  -> nothing
    P_FOREIGN  strength moderate   -> another user's goal (seeded raw)
    G_UNLINKED an active learning goal no principle supports

The app runs bootstrapped over its own graph (``tests/integration/_activity_link_rig.py``).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.integration._activity_link_rig import create, signed_in_client, write_edge

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx

    from core.services.user import UserContext

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzpgsyn"
USER = f"user_{MARK}"
OTHER = f"user_{MARK}_other"  # owns the foreign goal; never signs in
FOREIGN_GOAL = f"goal_{MARK}_foreign"


class Env:
    def __init__(self, client: httpx.AsyncClient, services: Any, uids: dict[str, str]) -> None:
        self.client = client
        self.services = services  # boundary: the composed Services container
        self.uids = uids


async def _seed_foreign_goal(driver: Any) -> None:  # boundary: neo4j AsyncDriver
    async with driver.session() as session:
        await session.run(
            """
            MERGE (o:User {uid: $other})
            MERGE (g:Entity:Goal {uid: $goal})
            SET g.title = $goal, g.entity_type = 'goal', g.status = 'active',
                g.user_uid = $other, g.goal_type = 'learning'
            MERGE (o)-[:OWNS]->(g)
            """,
            other=OTHER,
            goal=FOREIGN_GOAL,
        )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(
    skuel_app: Any,  # boundary: fasthtml-app
) -> AsyncIterator[Env]:
    async with signed_in_client(skuel_app, USER, MARK) as client:
        uids = {
            "g_learn": await create(client, "goals", f"{MARK} learn", goal_type="learning"),
            "g_outcome": await create(client, "goals", f"{MARK} outcome", goal_type="outcome"),
            "g_done": await create(client, "goals", f"{MARK} done", goal_type="learning"),
            "g_unlinked": await create(client, "goals", f"{MARK} unlinked", goal_type="learning"),
            "p_linked": await create(client, "principles", f"{MARK} linked", strength="core"),
            "p_none": await create(client, "principles", f"{MARK} none", strength="exploring"),
            "p_foreign": await create(client, "principles", f"{MARK} foreign", strength="moderate"),
        }
        for goal in ("g_learn", "g_done"):
            linked = await client.post(
                "/api/goals/link-principle",
                json={"goal_uid": uids[goal], "principle_uid": uids["p_linked"]},
            )
            assert linked.status_code == 200, linked.text
        linked = await client.post(
            f"/api/principles/link?uid={uids['p_linked']}",
            json={"link_type": "goal", "target_uid": uids["g_outcome"]},
        )
        assert linked.status_code == 200, linked.text
        done = await client.post(
            f"/api/goals/{uids['g_done']}/status", data={"status": "completed"}
        )
        assert done.status_code == 200, done.text
        assert "Missing status" not in done.text and "Invalid status" not in done.text

        services = skuel_app.state.services
        await _seed_foreign_goal(services.neo4j_driver)
        await write_edge(
            services.neo4j_driver,
            uids["p_foreign"],
            "SUPPORTS_GOAL",
            FOREIGN_GOAL,
            {"weight": 1.0, "essentiality": "supporting"},
        )
        yield Env(client, services, uids)


async def _rich(env: Env) -> UserContext:
    # The builder itself, past the context cache: a test below seeds after a build.
    built = await env.services.context.context_builder.build_rich(USER)
    assert built.is_ok, built
    return built.value


async def test_the_rich_build_reads_the_goals_each_principle_supports(env: Env) -> None:
    context = await _rich(env)
    u = env.uids

    # Every status of goal; another user's goal is no goal of the learner's principle.
    assert context.principle_supported_goals == {
        u["p_linked"]: sorted([u["g_learn"], u["g_outcome"], u["g_done"]])
    }


async def test_the_rich_build_weighs_each_principle_by_its_strength(env: Env) -> None:
    context = await _rich(env)
    u = env.uids

    assert context.principle_priorities == {
        u["p_linked"]: 1.0,
        u["p_none"]: 0.2,
        u["p_foreign"]: 0.6,
    }


async def test_a_principle_guides_only_the_active_goals_it_supports(env: Env) -> None:
    intelligence = env.services.context_intelligence.create(await _rich(env))
    u = env.uids

    result = await intelligence.get_cross_domain_synergies(
        min_synergy_score=0.0, include_types=["principle_goal"]
    )

    assert result.is_ok, result
    assert [(s.source_uid, set(s.target_uids)) for s in result.value] == [
        (u["p_linked"], {u["g_learn"], u["g_outcome"]})
    ]
    synergy = result.value[0]
    assert synergy.source_domain == "principle"
    assert synergy.target_domain == "goal"
    # two goals and a CORE principle: 0.3 + 2 * 0.15 + 1.0 * 0.2
    assert synergy.synergy_score == pytest.approx(0.8)


async def test_unlinked_principles_and_goals_appear_in_no_synergy(env: Env) -> None:
    intelligence = env.services.context_intelligence.create(await _rich(env))
    u = env.uids

    result = await intelligence.get_cross_domain_synergies(min_synergy_score=0.0)

    assert result.is_ok, result
    named = {s.source_uid for s in result.value} | {
        uid for s in result.value for uid in s.target_uids
    }
    for absent in ("p_none", "p_foreign", "g_unlinked", "g_done"):
        assert u[absent] not in named, absent
    assert FOREIGN_GOAL not in named


async def test_the_standard_build_carries_no_principle_support(env: Env) -> None:
    built = await env.services.context.context_builder.build(USER)
    assert built.is_ok, built

    assert built.value.principle_supported_goals == {}


async def _set_alignment(env: Env, principle: str, current: str, history: list[str]) -> None:
    records = [
        {
            "assessed_date": f"2026-09-{day:02d}",
            "alignment_level": level,
            "evidence": "",
            "reflection": None,
            "kind": "assessment",
        }
        for day, level in enumerate(history, start=1)
    ]
    async with env.services.neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (p:Principle {uid: $uid})
            SET p.current_alignment = $current, p.alignment_history = $history
            """,
            uid=principle,
            current=current,
            history=json.dumps(records),
        )


async def test_a_deeply_held_principle_is_not_called_declining_without_a_fall(
    env: Env,
) -> None:
    """Its strength is its own reason; the trend is read off the dated assessments."""
    u = env.uids
    await _set_alignment(env, u["p_linked"], "misaligned", ["misaligned"])
    await _set_alignment(env, u["p_none"], "drifting", ["aligned", "drifting"])

    result = await env.services.principles.get_principles_needing_attention_for_user(
        await _rich(env), limit=10
    )

    assert result.is_ok, result
    by_uid = {p.uid: p for p in result.value}
    linked = by_uid[u["p_linked"]]
    assert linked.title == f"{MARK} linked"
    assert linked.alignment_trend == "stable"
    assert "Alignment trend is declining" not in linked.attention_reasons
    assert any(r.startswith("Deeply held, but low alignment") for r in linked.attention_reasons)
    fell = by_uid[u["p_none"]]
    assert fell.alignment_trend == "declining"
    assert "Alignment trend is declining" in fell.attention_reasons
