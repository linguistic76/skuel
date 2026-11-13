"""Every writer that changes a goal's habits moves a habit-based goal's figure, over the
bootstrapped app.

A HABIT_BASED goal's figure is its owner's supporting habits' average streak against
``target_value`` (10 days here), written by the locked recompute
(``GoalsProgressService.recompute_habit_figure``) that ``GoalHabitsChanged``'s one
subscriber runs. The goal page's own doors are ``test_goal_habit_system_doors.py``; held
here are the other membership writers:

- goal create with two supporting habits writes their average at once;
- habit create linked to the goal lowers it (a new habit's streak is 0);
- habit delete at the CRUD route raises or lowers it, and with the last habit gone
  writes 0;
- the vault: a habit file's ``connections.supports_goal`` and a goal file's
  ``connections.supporting_habits`` added and dropped, a deleted habit file, and a
  ``SUPPORTS_GOAL`` Edge YAML written and deleted; a link a vault file writes carries
  the create doors' ``weight`` and ``essentiality``;
- ``./dev reconcile-goal-tallies`` closes a habit-based goal's stale figure;
- a percentage goal is untouched by all of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.relationship_names import RelationshipName
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import (
    create,
    edges_between,
    signed_in_client,
    sync_vault,
    wipe,
    write_edge_file,
    write_vault_file,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    import httpx
    from neo4j import AsyncDriver

    from adapters.inbound.fasthtml_types import FastHTMLApp

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzgoalhabitwriters"
CALLER = seed_user_uid(MARK)
SUPPORTS_GOAL = RelationshipName.SUPPORTS_GOAL.value


@dataclass(frozen=True)
class Env:
    client: httpx.AsyncClient
    services: Any  # boundary: the composed Services container
    driver: AsyncDriver


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(skuel_app: FastHTMLApp) -> AsyncIterator[Env]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with signed_in_client(skuel_app, CALLER, MARK) as client:
        yield Env(client=client, services=skuel_app.state.services, driver=driver)
    await wipe(driver, CALLER, MARK)


# ---------------------------------------------------------------------------
# Seeds and reads
# ---------------------------------------------------------------------------


async def _habit_goal(
    env: Env,
    title: str,
    **fields: Any,  # boundary: JSON body fields
) -> str:
    """A HABIT_BASED goal with a 10-day streak target, made at the JSON create door."""
    return await create(
        env.client,
        "goals",
        f"{MARK} {title}",
        measurement_type="habit_based",
        target_value=10,
        **fields,
    )


async def _percentage_goal_at_30(env: Env, title: str) -> str:
    goal = await create(env.client, "goals", f"{MARK} {title}", measurement_type="percentage")
    recorded = await env.client.post(f"/api/goals/{goal}/progress", json={"progress": 30})
    assert recorded.status_code == 200, recorded.text
    return goal


async def _habit(
    env: Env,
    title: str,
    streak: int | None = None,
    **fields: Any,  # boundary: JSON body fields
) -> str:
    """A habit made at the JSON create door, its streak seeded straight into the graph."""
    habit = await create(env.client, "habits", f"{MARK} {title}", **fields)
    if streak is not None:
        await _set_streak(env, habit, streak)
    return habit


async def _set_streak(env: Env, habit: str, streak: int) -> None:
    async with env.driver.session() as session:
        await session.run(
            "MATCH (h:Habit {uid: $uid}) SET h.current_streak = $streak", uid=habit, streak=streak
        )


async def _link(env: Env, goal: str, habit: str) -> None:
    linked = await env.client.post(f"/api/goals/{goal}/habits", json={"habit_uid": habit})
    assert linked.status_code == 200, linked.text


async def _delete_habit(env: Env, habit: str) -> None:
    deleted = await env.client.post(f"/api/habits/delete?uid={habit}")
    assert deleted.status_code == 200, deleted.text


async def _figure(env: Env, goal: str) -> tuple[float, float]:
    """The goal's stored ``(progress_percentage, current_value)``."""
    async with env.driver.session() as session:
        record = await (
            await session.run(
                "MATCH (g:Goal {uid: $uid}) "
                "RETURN g.progress_percentage AS progress, g.current_value AS value",
                uid=goal,
            )
        ).single()
    assert record is not None, goal
    return (record["progress"], record["value"])


async def _progress(env: Env, goal: str) -> float:
    return (await _figure(env, goal))[0]


async def _supports(
    env: Env, habit: str, goal: str
) -> list[dict[str, Any]]:  # boundary: raw relationship properties
    return [
        edge.properties
        for edge in await edges_between(env.driver, habit, goal)
        if edge.type == SUPPORTS_GOAL and edge.source == habit
    ]


# ---------------------------------------------------------------------------
# The create doors
# ---------------------------------------------------------------------------


async def test_a_goal_created_with_two_habits_takes_their_average_at_once(env: Env) -> None:
    short = await _habit(env, "create short", streak=4)
    long = await _habit(env, "create long", streak=8)

    goal = await _habit_goal(env, "create", supporting_habit_uids=[short, long])

    assert await _figure(env, goal) == (60.0, 6.0)


async def test_a_habit_created_linked_to_the_goal_lowers_its_figure(env: Env) -> None:
    goal = await _habit_goal(env, "habit create")
    await _link(env, goal, await _habit(env, "habit create old", streak=8))
    assert await _figure(env, goal) == (80.0, 8.0)

    await _habit(env, "habit create new", linked_goal_uids=[goal])

    assert await _figure(env, goal) == (40.0, 4.0)


# ---------------------------------------------------------------------------
# Habit delete
# ---------------------------------------------------------------------------


async def test_deleting_a_habit_moves_the_figure_and_the_last_one_writes_0(env: Env) -> None:
    goal = await _habit_goal(env, "delete")
    short = await _habit(env, "delete short", streak=4)
    long = await _habit(env, "delete long", streak=8)
    await _link(env, goal, short)
    await _link(env, goal, long)
    assert await _figure(env, goal) == (60.0, 6.0)

    await _delete_habit(env, short)
    assert await _figure(env, goal) == (80.0, 8.0)

    await _delete_habit(env, long)
    assert await _figure(env, goal) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# The vault
# ---------------------------------------------------------------------------


def _habit_file(vault: Path, name: str, goals: list[str]) -> Path:
    return write_vault_file(
        vault,
        name,
        entity_type="habit",
        uid=f"habit.{MARK}.{name}",
        owner=CALLER,
        connections={"supports_goal": goals} if goals else None,
    )


def _bystanders(vault: Path) -> None:
    """Files that stay, so a deleted file stays under the mass-deletion guard."""
    for name in ("bystander-1", "bystander-2", "bystander-3"):
        _habit_file(vault, name, [])


async def test_a_habit_files_goal_added_dropped_and_its_file_deleted_moves_the_figure(
    env: Env, tmp_path: Path
) -> None:
    goal = await _habit_goal(env, "vault habit field")
    await _link(env, goal, await _habit(env, "vault habit field app", streak=8))
    bus = env.services.event_bus
    _bystanders(tmp_path)
    vault_habit = f"habit.{MARK}.field"

    _habit_file(tmp_path, "field", [goal])
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await _figure(env, goal) == (40.0, 4.0)
    assert await _supports(env, vault_habit, goal) == [
        {"weight": 1.0, "essentiality": "supporting"}
    ]

    _habit_file(tmp_path, "field", [])
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await _supports(env, vault_habit, goal) == []
    assert await _figure(env, goal) == (80.0, 8.0)

    file = _habit_file(tmp_path, "field", [goal])
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await _figure(env, goal) == (40.0, 4.0)

    file.unlink()
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await _figure(env, goal) == (80.0, 8.0)


async def test_a_goal_files_habit_added_and_dropped_moves_its_figure(
    env: Env, tmp_path: Path
) -> None:
    habit = await _habit(env, "vault goal field", streak=6)
    bus = env.services.event_bus
    vault_goal = f"goal.{MARK}.goal-field"

    def goal_file(habits: list[str]) -> None:
        write_vault_file(
            tmp_path,
            "goal-field",
            entity_type="goal",
            uid=vault_goal,
            owner=CALLER,
            connections={"supporting_habits": habits} if habits else None,
            extra=("measurement_type: habit_based", "target_value: 10"),
        )

    goal_file([habit])
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await _figure(env, vault_goal) == (60.0, 6.0)
    assert await _supports(env, habit, vault_goal) == [
        {"weight": 1.0, "essentiality": "supporting"}
    ]

    goal_file([])
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await _figure(env, vault_goal) == (0.0, 0.0)


async def test_an_edge_file_of_the_type_adds_and_its_deletion_removes_a_habit(
    env: Env, tmp_path: Path
) -> None:
    goal = await _habit_goal(env, "edge file")
    habit = await _habit(env, "edge file", streak=5)
    bus = env.services.event_bus
    _bystanders(tmp_path)
    edge = write_edge_file(tmp_path, "edge-sg", source=habit, edge_type=SUPPORTS_GOAL, target=goal)

    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await _figure(env, goal) == (50.0, 5.0)

    edge.unlink()
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await _figure(env, goal) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# The backstop
# ---------------------------------------------------------------------------


async def test_the_reconciler_closes_a_habit_based_goals_stale_figure(env: Env) -> None:
    goal = await _habit_goal(env, "reconcile")
    await _link(env, goal, await _habit(env, "reconcile", streak=3))
    async with env.driver.session() as session:
        await session.run(
            "MATCH (g:Goal {uid: $uid}) SET g.progress_percentage = 90.0, g.current_value = 9.0",
            uid=goal,
        )

    listed = await env.services.goals.progress.reconcile_goal_tallies(dry_run=True)
    assert listed.is_ok, listed
    assert goal in {gap.goal_uid for gap in listed.value}
    assert await _figure(env, goal) == (90.0, 9.0), "a dry run writes nothing"

    closed = await env.services.goals.progress.reconcile_goal_tallies(dry_run=False)
    assert closed.is_ok, closed
    assert await _figure(env, goal) == (30.0, 3.0)
    again = await env.services.goals.progress.reconcile_goal_tallies(dry_run=True)
    assert goal not in {gap.goal_uid for gap in again.value}


# ---------------------------------------------------------------------------
# Another measurement type
# ---------------------------------------------------------------------------


async def test_a_percentage_goal_is_untouched_by_every_membership_writer(
    env: Env, tmp_path: Path
) -> None:
    goal = await _percentage_goal_at_30(env, "percentage")
    bus = env.services.event_bus
    _bystanders(tmp_path)

    habit = await _habit(env, "percentage new", streak=9, linked_goal_uids=[goal])
    assert await _progress(env, goal) == 30.0
    await _delete_habit(env, habit)
    assert await _progress(env, goal) == 30.0
    _habit_file(tmp_path, "percentage", [goal])
    await sync_vault(env.driver, tmp_path, event_bus=bus)
    assert await _progress(env, goal) == 30.0
    born_linked = await create(
        env.client,
        "goals",
        f"{MARK} percentage born linked",
        measurement_type="percentage",
        supporting_habit_uids=[await _habit(env, "percentage born", streak=9)],
    )
    assert await _progress(env, born_linked) == 0.0, "not the habit's 90%"
