"""Every door that links a principle to a goal writes one edge that both ends read.

The link is ``(Principle)-[:SUPPORTS_GOAL]->(Goal)``, whichever side made it:

- ``POST /api/principles/link?uid=<principle>`` with ``link_type: goal``;
- ``POST /api/goals/link-principle``;
- ``POST /api/goals/create`` with ``supporting_principle_uids``;
- a note's ``@context(goal) @link(principle:<uid>)`` line, through the
  EXTRACT_ACTIVITIES run to goal create;
- a principle file's ``connections.supports_goal``;
- a goal file's ``connections.supporting_principles``.

After each door the pair holds exactly that one edge, the goal's keyed read
``supporting_principles`` returns the principle and the principle's keyed read
``supported_goals`` returns the goal. The app doors stamp
``{weight: 1.0, essentiality: "supporting"}``; a vault file's edge carries no
property. The same link made at two doors is still one edge.

Both pages showing the link under their own heading is held by
``test_activity_page_links.py``: its pairs are the registry's census, and
(Principle, SUPPORTS_GOAL, Goal) is one of them — asserted here so that coverage
cannot lapse unnoticed.

The app runs bootstrapped over its own graph; the routes are the ones the bootstrap
wires (``tests/integration/_activity_link_rig.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.pipeline import Pipeline
from core.models.relationship_names import RelationshipName
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.services.user_entry.user_entry_processing_service import UserEntryProcessingService
from tests.helpers.activity_links import Link, links_read_at_both_ends
from tests.integration._activity_link_rig import (
    RETIRED_PRINCIPLE_GOAL,
    Edge,
    create,
    edges_between,
    signed_in_client,
    sync_vault,
    write_vault_file,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable
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

MARK = "zzzpgdoors"
CALLER = f"user_{MARK}"

SUPPORTS_GOAL = RelationshipName.SUPPORTS_GOAL.value
APP_STAMP = {"weight": 1.0, "essentiality": "supporting"}


@dataclass(frozen=True)
class Env:
    """What a door needs to be walked through."""

    client: httpx.AsyncClient
    services: Any  # boundary: the composed Services container
    driver: AsyncDriver
    vault_root: Path


# A door, walked: makes its own principle and goal, links them, returns (principle, goal).
type Walk = Callable[[Env, str], Awaitable[tuple[str, str]]]


async def _own_pair(env: Env, name: str) -> tuple[str, str]:
    principle = await create(env.client, "principles", f"{MARK} {name} principle")
    goal = await create(env.client, "goals", f"{MARK} {name} goal")
    return principle, goal


async def _post_principle_link(env: Env, principle: str, goal: str) -> None:
    response = await env.client.post(
        f"/api/principles/link?uid={principle}", json={"link_type": "goal", "target_uid": goal}
    )
    assert response.status_code == 200, response.text


async def _post_goal_link_principle(env: Env, principle: str, goal: str) -> None:
    response = await env.client.post(
        "/api/goals/link-principle", json={"goal_uid": goal, "principle_uid": principle}
    )
    assert response.status_code == 200, response.text


async def _principle_link_door(env: Env, name: str) -> tuple[str, str]:
    principle, goal = await _own_pair(env, name)
    await _post_principle_link(env, principle, goal)
    return principle, goal


async def _goal_link_principle_door(env: Env, name: str) -> tuple[str, str]:
    principle, goal = await _own_pair(env, name)
    await _post_goal_link_principle(env, principle, goal)
    return principle, goal


async def _goal_create_door(env: Env, name: str) -> tuple[str, str]:
    principle = await create(env.client, "principles", f"{MARK} {name} principle")
    goal = await create(
        env.client, "goals", f"{MARK} {name} goal", supporting_principle_uids=[principle]
    )
    return principle, goal


async def _note_line_door(env: Env, name: str) -> tuple[str, str]:
    """A note whose one activity line is a goal naming the principle."""
    principle = await create(env.client, "principles", f"{MARK} {name} principle")
    title = f"{MARK} {name} goal from a note"
    entry = await env.services.user_entry.create_entry(
        request=UserEntryCreateRequest(
            title=f"{MARK} {name} note",
            content=f"Notes.\n\n- [ ] {title} @context(goal) @link(principle:{principle})\n",
            pipeline=Pipeline.EXTRACT_ACTIVITIES,
        ),
        user_uid=CALLER,
    )
    assert entry.is_ok, entry
    # The app's own extractor over the app's own goal facade; no LLM pre-pass.
    processor = UserEntryProcessingService(
        entry_service=env.services.user_entry,
        activity_extractor=env.services.user_entry_processor.activity_extractor,
        user_service=env.services.user_entry_processor.user_service,
    )
    processed = await processor.process(entry.value[0])
    assert processed.is_ok, processed
    async with env.driver.session() as session:
        record = await (
            await session.run(
                """
                MATCH (g:Goal {user_uid: $user})-[:EXTRACTED_FROM]->(:UserEntry {uid: $entry})
                RETURN collect(g.uid) AS goals
                """,
                user=CALLER,
                entry=entry.value[0].uid,
            )
        ).single()
    assert record is not None and len(record["goals"]) == 1, (
        f"the note's goal line created {record and record['goals']}"
    )
    return principle, str(record["goals"][0])


def _vault_pair(name: str) -> tuple[str, str]:
    return f"principle.{MARK}.{name}", f"goal.{MARK}.{name}"


async def _principle_file_door(env: Env, name: str) -> tuple[str, str]:
    principle, goal = _vault_pair(name)
    vault = env.vault_root / name
    vault.mkdir()
    write_vault_file(vault, f"{name}-goal", entity_type="goal", uid=goal, owner=CALLER)
    write_vault_file(
        vault,
        f"{name}-principle",
        entity_type="principle",
        uid=principle,
        owner=CALLER,
        connections={"supports_goal": [goal]},
    )
    await sync_vault(env.driver, vault)
    return principle, goal


async def _goal_file_door(env: Env, name: str) -> tuple[str, str]:
    principle, goal = _vault_pair(name)
    vault = env.vault_root / name
    vault.mkdir()
    write_vault_file(
        vault, f"{name}-principle", entity_type="principle", uid=principle, owner=CALLER
    )
    write_vault_file(
        vault,
        f"{name}-goal",
        entity_type="goal",
        uid=goal,
        owner=CALLER,
        connections={"supporting_principles": [principle]},
    )
    await sync_vault(env.driver, vault)
    return principle, goal


@dataclass(frozen=True)
class Door:
    label: str
    name: str  # a slug for this door's own entities
    walk: Walk
    stamps: bool  # whether the door writes the importance properties


DOORS = (
    Door("POST /api/principles/link [goal]", "plink", _principle_link_door, stamps=True),
    Door("POST /api/goals/link-principle", "glink", _goal_link_principle_door, stamps=True),
    Door("POST /api/goals/create", "gcreate", _goal_create_door, stamps=True),
    Door("note line @context(goal) @link(principle:)", "note", _note_line_door, stamps=True),
    Door("principle file connections.supports_goal", "pfile", _principle_file_door, stamps=False),
    Door("goal file connections.supporting_principles", "gfile", _goal_file_door, stamps=False),
)
_DOOR_IDS = [door.label for door in DOORS]


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(
    skuel_app: Any,  # boundary: fasthtml-app
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[Env]:
    async with signed_in_client(skuel_app, CALLER, MARK) as client:
        yield Env(
            client=client,
            services=skuel_app.state.services,
            driver=skuel_app.state.services.neo4j_driver,
            vault_root=tmp_path_factory.mktemp("principle_goal_vaults"),
        )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def linked(env: Env) -> dict[str, tuple[str, str]]:
    """Each door walked once: door label -> (principle uid, goal uid)."""
    return {door.label: await door.walk(env, door.name) for door in DOORS}


@pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
async def test_the_door_leaves_exactly_one_edge_from_the_principle_to_the_goal(
    env: Env, linked: dict[str, tuple[str, str]], door: Door
) -> None:
    principle, goal = linked[door.label]

    stored = await edges_between(env.driver, principle, goal)

    assert not {edge.type for edge in stored} & RETIRED_PRINCIPLE_GOAL, stored
    assert [(edge.type, edge.source, edge.target) for edge in stored] == [
        (SUPPORTS_GOAL, principle, goal)
    ]


@pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
async def test_the_goal_reads_the_principle_among_its_supporting_principles(
    env: Env, linked: dict[str, tuple[str, str]], door: Door
) -> None:
    principle, goal = linked[door.label]

    read = await env.services.goals.relationships.get_related_uids("supporting_principles", goal)

    assert read.is_ok, read
    assert read.value == [principle]


@pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
async def test_the_principle_reads_the_goal_among_its_supported_goals(
    env: Env, linked: dict[str, tuple[str, str]], door: Door
) -> None:
    principle, goal = linked[door.label]

    read = await env.services.principles.relationships.get_related_uids(
        "supported_goals", principle
    )

    assert read.is_ok, read
    assert read.value == [goal]


@pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
async def test_an_app_door_stamps_the_importance_and_a_vault_file_stamps_nothing(
    env: Env, linked: dict[str, tuple[str, str]], door: Door
) -> None:
    stored = await edges_between(env.driver, *linked[door.label])

    assert [edge.properties for edge in stored] == [APP_STAMP if door.stamps else {}]


async def _one_edge(env: Env, principle: str, goal: str) -> Edge:
    stored = await edges_between(env.driver, principle, goal)
    assert len(stored) == 1, stored
    return stored[0]


async def test_the_link_made_at_both_app_doors_is_one_edge(env: Env) -> None:
    principle, goal = await _own_pair(env, "both-doors")

    await _post_principle_link(env, principle, goal)
    first = await _one_edge(env, principle, goal)
    await _post_goal_link_principle(env, principle, goal)

    assert await _one_edge(env, principle, goal) == first
    assert first == Edge(SUPPORTS_GOAL, principle, goal, APP_STAMP)


async def test_the_link_declared_in_both_files_is_one_edge(env: Env) -> None:
    principle, goal = _vault_pair("bothfiles")
    vault = env.vault_root / "bothfiles"
    vault.mkdir()
    write_vault_file(
        vault,
        "bothfiles-principle",
        entity_type="principle",
        uid=principle,
        owner=CALLER,
        connections={"supports_goal": [goal]},
    )
    write_vault_file(
        vault,
        "bothfiles-goal",
        entity_type="goal",
        uid=goal,
        owner=CALLER,
        connections={"supporting_principles": [principle]},
    )

    await sync_vault(env.driver, vault)

    assert await _one_edge(env, principle, goal) == Edge(SUPPORTS_GOAL, principle, goal, {})


async def test_both_pages_showing_the_link_is_held_by_the_page_tests() -> None:
    """``test_activity_page_links.py`` walks this pair: both detail pages, both cards."""
    assert Link(NeoLabel.PRINCIPLE, RelationshipName.SUPPORTS_GOAL, NeoLabel.GOAL) in (
        links_read_at_both_ends()
    )
