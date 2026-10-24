"""Three Activity intelligence readers read what the graph holds, over the bootstrapped app.

- **Knowledge-aware task priorities** (``GET /api/tasks/knowledge-priorities``) score
  each task against the user's mastery progression in the knowledge the task links.
  The knowledge a task links is its ``APPLIES_KNOWLEDGE`` / ``REQUIRES_KNOWLEDGE`` /
  ``INFERRED_KNOWLEDGE`` edges to published curriculum, read from the graph.
- **Principle conflicts** (``PrinciplesService.get_principle_conflict_analysis``) pair
  two principles that support the same goal — the ``SUPPORTS_GOAL`` edge each link door
  writes, read from the principle's ``supported_goals`` context.
- **A task's knowledge prerequisites** (``GET /api/tasks/insights``) come from the
  task's own neighbourhood. The every-edge lens stops at a ``User`` node: a PathStep the
  owner viewed is not a prerequisite of a task that does not link it.

Entities are created at the real create and link doors (``_activity_link_rig.py``);
shared curriculum is seeded the way the content vault writes it.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.constants import KnowledgeEnhancementScore
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import (
    create,
    seed_published_path_step,
    signed_in_client,
    write_edge,
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


class Env:
    def __init__(self, client: httpx.AsyncClient, services: Any, uids: dict[str, str]) -> None:
        self.client = client
        self.services = services  # boundary: the composed Services container
        self.uids = uids


async def _seed_ku(driver: AsyncDriver, uid: str, state: str | None) -> None:
    """A shared Ku; ``state`` is its ``publication_state`` (``None`` = authored before it)."""
    async with driver.session() as session:
        await session.run(
            """
            MERGE (k:Entity:Ku {uid: $uid})
            SET k.title = $uid, k.entity_type = 'ku', k.status = 'active',
                k.publication_state = $state
            """,
            uid=uid,
            state=state,
        )


async def _set_state(client: httpx.AsyncClient, segment: str, uid: str, status: str) -> None:
    response = await client.post(f"/api/{segment}/{uid}/status", data={"status": status})
    assert response.status_code == 200, response.text
    assert "Missing status" not in response.text and "Invalid status" not in response.text


def _far_due_date() -> str:
    """Past the urgency window, so a due date adds nothing to the mastery score."""
    return (today_in(current_zone()) + timedelta(days=30)).isoformat()


# ---------------------------------------------------------------------------
# Knowledge-aware task priorities
# ---------------------------------------------------------------------------

PRI_MARK = "zzzakpri"
PRI_USER = seed_user_uid(f"{PRI_MARK}")
KU_APPLIED = f"ku.{PRI_MARK}.applied"
KU_REQUIRED = f"ku.{PRI_MARK}.required"
KU_LATER_DRAFT = f"ku.{PRI_MARK}.later-draft"  # published when linked, a draft since


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def priorities(skuel_app: Any) -> AsyncIterator[Env]:  # boundary: fasthtml-app
    services = skuel_app.state.services
    driver = services.neo4j_driver
    async with signed_in_client(skuel_app, PRI_USER, PRI_MARK) as client:
        for ku in (KU_APPLIED, KU_REQUIRED, KU_LATER_DRAFT):
            await _seed_ku(driver, ku, None)
        uids = {
            "open": await create(
                client,
                "tasks",
                f"{PRI_MARK} open",
                due_date=_far_due_date(),
                applies_knowledge_uids=[KU_APPLIED],
                prerequisite_knowledge_uids=[KU_REQUIRED],
            ),
            "done": await create(
                client, "tasks", f"{PRI_MARK} done", applies_knowledge_uids=[KU_APPLIED]
            ),
            "bare": await create(client, "tasks", f"{PRI_MARK} bare", due_date=_far_due_date()),
            "later": await create(
                client, "tasks", f"{PRI_MARK} later", applies_knowledge_uids=[KU_LATER_DRAFT]
            ),
        }
        await _set_state(client, "tasks", uids["done"], "completed")
        await _seed_ku(driver, KU_LATER_DRAFT, "draft")
        yield Env(client, services, uids)


async def _priority(env: Env, task: str) -> dict[str, Any]:  # boundary: JSON body
    response = await env.client.get(
        "/api/tasks/knowledge-priorities", params={"task_uids": env.uids[task]}
    )
    assert response.status_code == 200, response.text
    rows = response.json()["priorities"]
    assert [row["task_uid"] for row in rows] == [env.uids[task]]
    return rows[0]


async def test_a_task_is_scored_against_its_knowledges_mastery_progression(
    priorities: Env,
) -> None:
    """The applied Ku has a progression (one task done, one open, mastery 0), so the
    task scores the room left in it — not the no-progression fallback."""
    row = await _priority(priorities, "open")

    assert row["knowledge_enhancement_score"] == pytest.approx(1.0)
    assert row["knowledge_enhancement_score"] != pytest.approx(
        KnowledgeEnhancementScore.NEW_KNOWLEDGE_POTENTIAL
    )
    # Two links, both with a progression and no velocity: room weight only.
    assert row["mastery_progression_score"] == pytest.approx(
        KnowledgeEnhancementScore.MASTERY_ROOM_WEIGHT
    )


async def test_a_task_with_no_knowledge_scores_the_baseline(priorities: Env) -> None:
    row = await _priority(priorities, "bare")

    assert row["knowledge_enhancement_score"] == pytest.approx(
        KnowledgeEnhancementScore.NO_KNOWLEDGE_BASELINE
    )
    assert row["mastery_progression_score"] == pytest.approx(
        KnowledgeEnhancementScore.NO_KNOWLEDGE_BASELINE
    )


async def test_mastery_progression_tracks_every_published_ku_the_tasks_link(
    priorities: Env,
) -> None:
    """Applied and required knowledge both count; a Ku unpublished after the link does not."""
    result = await priorities.services.tasks.track_knowledge_mastery_progression(PRI_USER)

    assert result.is_ok, result
    progressions = result.value
    assert set(progressions) == {KU_APPLIED, KU_REQUIRED}
    assert progressions[KU_APPLIED].activities_completed == 1
    assert progressions[KU_REQUIRED].activities_completed == 0


# ---------------------------------------------------------------------------
# Principle conflicts
# ---------------------------------------------------------------------------

CON_MARK = "zzzakcon"
CON_USER = seed_user_uid(f"{CON_MARK}")


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def conflicts(skuel_app: Any) -> AsyncIterator[Env]:  # boundary: fasthtml-app
    services = skuel_app.state.services
    async with signed_in_client(skuel_app, CON_USER, CON_MARK) as client:
        uids = {
            "g_shared": await create(client, "goals", f"{CON_MARK} shared", goal_type="learning"),
            "g_own": await create(client, "goals", f"{CON_MARK} own", goal_type="learning"),
            "p_one": await create(client, "principles", f"{CON_MARK} one", strength="core"),
            "p_two": await create(client, "principles", f"{CON_MARK} two", strength="core"),
            "p_apart": await create(client, "principles", f"{CON_MARK} apart", strength="core"),
            "p_near": await create(client, "principles", f"{CON_MARK} near", strength="core"),
        }
        for goal, principle in (
            ("g_shared", "p_one"),
            ("g_shared", "p_two"),
            ("g_own", "p_apart"),
        ):
            linked = await client.post(
                "/api/goals/link-principle",
                json={"goal_uid": uids[goal], "principle_uid": uids[principle]},
            )
            assert linked.status_code == 200, linked.text
        # p_near supports no goal itself; p_one's goals are two hops from it.
        await write_edge(services.neo4j_driver, uids["p_near"], "RELATED_TO", uids["p_one"])
        yield Env(client, services, uids)


async def test_two_principles_supporting_one_goal_are_a_conflict(conflicts: Env) -> None:
    result = await conflicts.services.principles.get_principle_conflict_analysis(CON_USER)

    assert result.is_ok, result
    analysis = result.value
    assert analysis["total_principles"] == 4
    pairs = [{c["principle1"]["uid"], c["principle2"]["uid"]} for c in analysis["conflicts"]]
    assert pairs == [{conflicts.uids["p_one"], conflicts.uids["p_two"]}]
    assert analysis["conflicts"][0]["overlapping_goals_count"] == 1
    assert analysis["conflicts_detected"] == 1
    assert analysis["conflict_severity"] == {"high": 1, "medium": 0, "low": 0}


# ---------------------------------------------------------------------------
# A task's knowledge prerequisites — the neighbourhood stops at a User node
# ---------------------------------------------------------------------------

NB_MARK = "zzzaknbh"
NB_USER = seed_user_uid(f"{NB_MARK}")
KU_LINKED = f"ku.{NB_MARK}.linked"
STEP_VIEWED = f"ps.{NB_MARK}.viewed"


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def neighbourhood(skuel_app: Any) -> AsyncIterator[Env]:  # boundary: fasthtml-app
    services = skuel_app.state.services
    driver = services.neo4j_driver
    async with signed_in_client(skuel_app, NB_USER, NB_MARK) as client:
        await _seed_ku(driver, KU_LINKED, None)
        await seed_published_path_step(driver, STEP_VIEWED, f"{NB_MARK} viewed step")
        viewed = await client.get(f"/explore/ps/{STEP_VIEWED}/content")
        assert viewed.status_code == 200, viewed.text
        uids = {
            "task": await create(
                client, "tasks", f"{NB_MARK} task", applies_knowledge_uids=[KU_LINKED]
            ),
        }
        yield Env(client, services, uids)


async def test_the_view_door_wrote_the_edge_the_lens_would_walk(neighbourhood: Env) -> None:
    """The instrument: the owner's ``VIEWED`` edge is in the graph."""
    async with neighbourhood.services.neo4j_driver.session() as session:
        record = await (
            await session.run(
                "MATCH (:User {uid: $u})-[r:VIEWED]->(:PathStep {uid: $s}) RETURN count(r) AS n",
                u=NB_USER,
                s=STEP_VIEWED,
            )
        ).single()
    assert record is not None and record["n"] == 1


async def test_a_tasks_prerequisites_are_its_own_links_not_what_its_owner_viewed(
    neighbourhood: Env,
) -> None:
    response = await neighbourhood.client.get(
        "/api/tasks/insights", params={"uid": neighbourhood.uids["task"]}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    prerequisites = {item["uid"] for item in body["knowledge_prerequisites"]}
    assert prerequisites == {KU_LINKED}
    assert body["has_prerequisites"] is True
