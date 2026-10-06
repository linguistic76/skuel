"""Every door that links a principle to a choice writes one edge that both ends read.

The link is ``(Principle)-[:INFORMS_CHOICE]->(Choice)``, whichever side made it:

- ``POST /api/principles/link?uid=<principle>`` with ``link_type: choice``;
- ``POST /api/choices/link-principle``;
- a choice file's ``connections.informing_principles``;
- a principle file's ``connections.informs_choice``.

After each door the pair holds exactly that one edge, carrying no property, and no
edge of a retired type (``GUIDES_CHOICE``, ``INFORMED_BY_PRINCIPLE``). The choice's
keyed read ``informing_principles`` returns the principle, the principle's keyed
read ``informed_choices`` returns the choice, and the choice's habit view
``informing_habits`` does not. Both detail pages list the far end under their own
heading. The same link made at two doors is still one edge, and a file that stops
declaring the link loses the edge on its next sync.

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
from core.models.relationship_names import RelationshipName
from tests.helpers.activity_links import Link, links_read_at_both_ends
from tests.integration._activity_link_rig import (
    RETIRED_PRINCIPLE_CHOICE,
    Edge,
    create,
    edges_between,
    signed_in_client,
    sync_vault,
    under_heading,
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

MARK = "zzzpcdoors"
CALLER = f"user_{MARK}"

INFORMS_CHOICE = RelationshipName.INFORMS_CHOICE.value

CHOICE_HEADING = "Principles that inform this choice"
PRINCIPLE_HEADING = "Choices this principle informs"


@dataclass(frozen=True)
class Env:
    """What a door needs to be walked through."""

    client: httpx.AsyncClient
    services: Any  # boundary: the composed Services container
    driver: AsyncDriver
    vault_root: Path


@dataclass(frozen=True)
class Pair:
    """A principle and a choice a door linked, with the titles their pages show."""

    principle: str
    choice: str
    principle_title: str
    choice_title: str


# A door, walked: makes its own principle and choice, links them, returns the pair.
type Walk = Callable[[Env, str], Awaitable[Pair]]


async def _own_pair(env: Env, name: str) -> Pair:
    principle_title = f"{MARK} {name} principle"
    choice_title = f"{MARK} {name} choice"
    return Pair(
        principle=await create(env.client, "principles", principle_title),
        choice=await create(env.client, "choices", choice_title),
        principle_title=principle_title,
        choice_title=choice_title,
    )


async def _post_principle_link(env: Env, pair: Pair) -> None:
    response = await env.client.post(
        f"/api/principles/link?uid={pair.principle}",
        json={"link_type": "choice", "target_uid": pair.choice},
    )
    assert response.status_code == 200, response.text


async def _post_choice_link_principle(
    env: Env,
    pair: Pair,
    **extra: Any,  # boundary: extra JSON body fields
) -> None:
    response = await env.client.post(
        "/api/choices/link-principle",
        json={"choice_uid": pair.choice, "principle_uid": pair.principle, **extra},
    )
    assert response.status_code == 200, response.text


async def _principle_link_door(env: Env, name: str) -> Pair:
    pair = await _own_pair(env, name)
    await _post_principle_link(env, pair)
    return pair


async def _choice_link_principle_door(env: Env, name: str) -> Pair:
    pair = await _own_pair(env, name)
    await _post_choice_link_principle(env, pair)
    return pair


def _vault_pair(name: str) -> Pair:
    return Pair(
        principle=f"principle.{MARK}.{name}",
        choice=f"choice.{MARK}.{name}",
        principle_title=f"{name}-principle",
        choice_title=f"{name}-choice",
    )


async def _choice_file_door(env: Env, name: str) -> Pair:
    pair = _vault_pair(name)
    vault = env.vault_root / name
    vault.mkdir()
    write_vault_file(
        vault, pair.principle_title, entity_type="principle", uid=pair.principle, owner=CALLER
    )
    write_vault_file(
        vault,
        pair.choice_title,
        entity_type="choice",
        uid=pair.choice,
        owner=CALLER,
        connections={"informing_principles": [pair.principle]},
    )
    await sync_vault(env.driver, vault)
    return pair


async def _principle_file_door(env: Env, name: str) -> Pair:
    pair = _vault_pair(name)
    vault = env.vault_root / name
    vault.mkdir()
    write_vault_file(vault, pair.choice_title, entity_type="choice", uid=pair.choice, owner=CALLER)
    write_vault_file(
        vault,
        pair.principle_title,
        entity_type="principle",
        uid=pair.principle,
        owner=CALLER,
        connections={"informs_choice": [pair.choice]},
    )
    await sync_vault(env.driver, vault)
    return pair


@dataclass(frozen=True)
class Door:
    label: str
    name: str  # a slug for this door's own entities
    walk: Walk


DOORS = (
    Door("POST /api/principles/link [choice]", "plink", _principle_link_door),
    Door("POST /api/choices/link-principle", "clink", _choice_link_principle_door),
    Door("choice file connections.informing_principles", "cfile", _choice_file_door),
    Door("principle file connections.informs_choice", "pfile", _principle_file_door),
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
            vault_root=tmp_path_factory.mktemp("principle_choice_vaults"),
        )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def linked(env: Env) -> dict[str, Pair]:
    """Each door walked once: door label -> the pair it linked."""
    return {door.label: await door.walk(env, door.name) for door in DOORS}


async def _related(
    service: Any,  # boundary: a composed domain facade (choices, principles)
    key: str,
    uid: str,
) -> list[str]:
    read = await service.relationships.get_related_uids(key, uid)
    assert read.is_ok, read
    return list(read.value)


@pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
async def test_the_door_leaves_exactly_one_edge_from_the_principle_to_the_choice(
    env: Env, linked: dict[str, Pair], door: Door
) -> None:
    pair = linked[door.label]

    stored = await edges_between(env.driver, pair.principle, pair.choice)

    assert not {edge.type for edge in stored} & RETIRED_PRINCIPLE_CHOICE, stored
    assert [(edge.type, edge.source, edge.target) for edge in stored] == [
        (INFORMS_CHOICE, pair.principle, pair.choice)
    ]


@pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
async def test_the_edge_carries_no_property(env: Env, linked: dict[str, Pair], door: Door) -> None:
    pair = linked[door.label]

    stored = await edges_between(env.driver, pair.principle, pair.choice)

    assert [edge.properties for edge in stored] == [{}]


@pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
async def test_the_choice_reads_the_principle_among_its_informing_principles(
    env: Env, linked: dict[str, Pair], door: Door
) -> None:
    pair = linked[door.label]

    assert await _related(env.services.choices, "informing_principles", pair.choice) == [
        pair.principle
    ]


@pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
async def test_the_principle_is_not_among_the_choices_informing_habits(
    env: Env, linked: dict[str, Pair], door: Door
) -> None:
    pair = linked[door.label]

    assert await _related(env.services.choices, "informing_habits", pair.choice) == []


@pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
async def test_the_principle_reads_the_choice_among_its_informed_choices(
    env: Env, linked: dict[str, Pair], door: Door
) -> None:
    pair = linked[door.label]

    assert await _related(env.services.principles, "informed_choices", pair.principle) == [
        pair.choice
    ]


@pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
async def test_the_choice_page_lists_the_principle_under_its_heading(
    env: Env, linked: dict[str, Pair], door: Door
) -> None:
    pair = linked[door.label]

    response = await env.client.get(f"/choices/detail/content?uid={pair.choice}")

    assert response.status_code == 200, response.text[:500]
    assert pair.principle_title in under_heading(response.text, CHOICE_HEADING)
    assert response.text.count(pair.principle_title) == 1, "the principle is listed once"


@pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
async def test_the_principle_page_lists_the_choice_under_its_heading(
    env: Env, linked: dict[str, Pair], door: Door
) -> None:
    pair = linked[door.label]

    response = await env.client.get(f"/principles/detail/content?uid={pair.principle}")

    assert response.status_code == 200, response.text[:500]
    assert pair.choice_title in under_heading(response.text, PRINCIPLE_HEADING)


async def _one_edge(env: Env, pair: Pair) -> Edge:
    stored = await edges_between(env.driver, pair.principle, pair.choice)
    assert len(stored) == 1, stored
    return stored[0]


async def test_the_link_made_at_both_app_doors_is_one_edge(env: Env) -> None:
    pair = await _own_pair(env, "both-doors")

    await _post_principle_link(env, pair)
    first = await _one_edge(env, pair)
    await _post_choice_link_principle(env, pair)

    assert await _one_edge(env, pair) == first
    assert first == Edge(INFORMS_CHOICE, pair.principle, pair.choice, {})


async def test_an_alignment_score_sent_to_the_choice_door_is_not_stored(env: Env) -> None:
    """The retired request field is ignored: the edge carries no property."""
    pair = await _own_pair(env, "stray-score")

    await _post_choice_link_principle(env, pair, alignment_score=0.9)

    assert await _one_edge(env, pair) == Edge(INFORMS_CHOICE, pair.principle, pair.choice, {})


async def test_the_link_declared_in_both_files_is_one_edge(env: Env) -> None:
    pair = _vault_pair("bothfiles")
    vault = env.vault_root / "bothfiles"
    vault.mkdir()
    write_vault_file(
        vault,
        pair.principle_title,
        entity_type="principle",
        uid=pair.principle,
        owner=CALLER,
        connections={"informs_choice": [pair.choice]},
    )
    write_vault_file(
        vault,
        pair.choice_title,
        entity_type="choice",
        uid=pair.choice,
        owner=CALLER,
        connections={"informing_principles": [pair.principle]},
    )

    await sync_vault(env.driver, vault)

    assert await _one_edge(env, pair) == Edge(INFORMS_CHOICE, pair.principle, pair.choice, {})


async def test_a_choice_file_that_drops_informing_principles_retracts_the_edge(
    env: Env,
) -> None:
    pair = _vault_pair("cretract")
    vault = env.vault_root / "cretract"
    vault.mkdir()
    write_vault_file(
        vault, pair.principle_title, entity_type="principle", uid=pair.principle, owner=CALLER
    )
    write_vault_file(
        vault,
        pair.choice_title,
        entity_type="choice",
        uid=pair.choice,
        owner=CALLER,
        connections={"informing_principles": [pair.principle]},
    )
    await sync_vault(env.driver, vault)
    assert await _related(env.services.choices, "informing_principles", pair.choice) == [
        pair.principle
    ]

    write_vault_file(vault, pair.choice_title, entity_type="choice", uid=pair.choice, owner=CALLER)
    await sync_vault(env.driver, vault)

    assert await edges_between(env.driver, pair.principle, pair.choice) == []
    assert await _related(env.services.choices, "informing_principles", pair.choice) == []
    assert await _related(env.services.principles, "informed_choices", pair.principle) == []


async def test_a_principle_file_that_drops_informs_choice_retracts_the_edge(env: Env) -> None:
    pair = _vault_pair("pretract")
    vault = env.vault_root / "pretract"
    vault.mkdir()
    write_vault_file(vault, pair.choice_title, entity_type="choice", uid=pair.choice, owner=CALLER)
    write_vault_file(
        vault,
        pair.principle_title,
        entity_type="principle",
        uid=pair.principle,
        owner=CALLER,
        connections={"informs_choice": [pair.choice]},
    )
    await sync_vault(env.driver, vault)
    assert await _related(env.services.principles, "informed_choices", pair.principle) == [
        pair.choice
    ]

    write_vault_file(
        vault, pair.principle_title, entity_type="principle", uid=pair.principle, owner=CALLER
    )
    await sync_vault(env.driver, vault)

    assert await edges_between(env.driver, pair.principle, pair.choice) == []
    assert await _related(env.services.principles, "informed_choices", pair.principle) == []
    assert await _related(env.services.choices, "informing_principles", pair.choice) == []


async def test_both_pages_showing_the_link_for_every_pair_is_held_by_the_page_tests() -> None:
    """``test_activity_page_links.py`` walks the pairs the registry reads at both ends:
    the principle's and the habit's ``INFORMS_CHOICE`` are each one of them."""
    pairs = links_read_at_both_ends()

    assert Link(NeoLabel.PRINCIPLE, RelationshipName.INFORMS_CHOICE, NeoLabel.CHOICE) in pairs
    assert Link(NeoLabel.HABIT, RelationshipName.INFORMS_CHOICE, NeoLabel.CHOICE) in pairs
