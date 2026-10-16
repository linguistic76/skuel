"""Lateral edges between curriculum items are authored only in the content vault.

ADR-091 S8: the ku / ps / lp lateral routes register reads only. No create (blocks,
prerequisites, alternatives, complementary), DELETE or manage list is registered for
them, and ``/api/ku/{uid}/lateral/enables`` answers GET only. Each such request
answers 404 or 405 to an admin, sent a well-formed body naming nodes it could
join, and leaves the graph unchanged.

Controls: the vault sync writes the edges those doors wrote (Edge YAML files), the
curriculum reads still answer, and an Activity lateral write between the admin's
own tasks still lands — the factory keeps the writes of a domain with an owner.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.integration._activity_link_rig import (
    create,
    edges_between,
    signed_in_client,
    sync_vault,
    touch_forward,
    write_edge_file,
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

MARK = "zzzlateralretired"
ADMIN = f"user_{MARK}"
PARENT = f"ps.{MARK}.parent"
KU_A = f"ku.{MARK}.a"
KU_B = f"ku.{MARK}.b"  # what a create would join: no vault edge reaches it
KU_C = f"ku.{MARK}.c"  # the far end of every vault-authored lateral edge
STEP = f"ps.{MARK}.step"
PATH = f"lp.{MARK}.path"
ANCHORS = {"ku": KU_A, "ps": STEP, "lp": PATH}

# The vault-authored lateral edges: what a curriculum DELETE or enables would change.
VAULT_EDGES = [
    (KU_A, "BLOCKS", KU_C),
    (STEP, "BLOCKS", KU_C),
    (PATH, "BLOCKS", KU_C),
    (KU_A, "ENABLES", KU_C),
]


def _write(vault: Path, name: str, text: str) -> None:
    path = vault / name
    path.write_text(text)
    touch_forward(path)


def _vault(vault: Path) -> None:
    """Every anchor under one parent, so a create's same-parent and same-depth
    rules hold: each body below is well-formed for the nodes it names."""
    for uid, name in ((KU_A, "a"), (KU_B, "b"), (KU_C, "c")):
        _write(vault, f"{name}.md", f"---\ntype: ku\nuid: {uid}\ntitle: {MARK} {name}\n---\nA.\n")
    _write(vault, "step.md", f"---\ntype: ps\nuid: {STEP}\ntitle: {MARK} step\n---\nA step.\n")
    _write(vault, "path.md", f"---\ntype: lp\nuid: {PATH}\ntitle: {MARK} path\n---\nA path.\n")
    organized = "".join(f"  - {uid}\n" for uid in (KU_A, KU_B, KU_C, STEP, PATH))
    _write(
        vault,
        "parent.md",
        f"---\ntype: ps\nuid: {PARENT}\ntitle: {MARK} parent\norganizes:\n{organized}---\nP.\n",
    )
    for index, (source, edge_type, target) in enumerate(VAULT_EDGES):
        write_edge_file(vault, f"edge-{index}", source=source, edge_type=edge_type, target=target)


async def _graph(driver: AsyncDriver) -> list[list[Any]]:  # boundary: raw graph read
    """Every edge touching this file's nodes, with its properties — what any
    curriculum lateral write would change. The pattern names no label (an index sync still
    running can refuse a labelled ``CONTAINS`` scan)."""
    async with driver.session() as session:
        record = await (
            await session.run(
                """
                MATCH (a)-[r]->(b)
                WHERE a.uid CONTAINS $mark OR b.uid CONTAINS $mark
                WITH a.uid AS from_uid, type(r) AS type, b.uid AS to_uid, properties(r) AS props
                ORDER BY from_uid, type, to_uid
                RETURN collect([from_uid, type, to_uid, props]) AS rows
                """,
                mark=MARK,
            )
        ).single()
    assert record is not None
    rows: list[list[Any]] = record["rows"]  # boundary: raw graph rows
    return rows


class World:
    def __init__(self, driver: AsyncDriver, client: httpx.AsyncClient) -> None:
        self.driver = driver
        self.client = client


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(
    skuel_app: Any,  # boundary: fasthtml-app
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[World]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    vault = tmp_path_factory.mktemp("content_vault")
    async with signed_in_client(skuel_app, ADMIN, MARK) as client:
        async with driver.session() as session:
            await session.run(
                """
                MATCH (u:User {uid: $uid})
                SET u.username = $uid, u.display_name = $uid, u.email = $uid + '@example.com',
                    u.role = 'admin', u.created_at = datetime(), u.updated_at = datetime()
                """,
                uid=ADMIN,
            )
        _vault(vault)
        await sync_vault(driver, vault)
        yield World(driver, client)


def _retired() -> dict[str, tuple[str, str, dict[str, str]]]:
    """Each curriculum write path with a well-formed form body. Creates aim at
    ``KU_B`` (nothing joins it yet); DELETE and manage aim at a vault-authored edge."""
    creates = {
        "blocks": {"reason": "order matters"},
        "prerequisites": {},
        "alternatives": {"comparison_criteria": "depth"},
        "complementary": {"synergy_description": "pair well"},
    }
    doors: dict[str, tuple[str, str, dict[str, str]]] = {}
    for domain, anchor in ANCHORS.items():
        for suffix, extra in creates.items():
            doors[f"{domain}-{suffix}"] = (
                "POST",
                f"/api/{domain}/{anchor}/lateral/{suffix}",
                {"target_uid": KU_B, **extra},
            )
        doors[f"{domain}-manage"] = ("GET", f"/api/{domain}/{anchor}/lateral/manage", {})
    doors["ku-enables"] = ("POST", f"/api/ku/{KU_A}/lateral/enables", {"target_uid": KU_B})
    # Last, so a delete that landed could not hide another case's write.
    for domain, anchor in ANCHORS.items():
        doors[f"{domain}-delete"] = ("DELETE", f"/api/{domain}/{anchor}/lateral/blocks/{KU_C}", {})
    return doors


RETIRED = _retired()


async def test_the_vault_writes_the_curriculum_lateral_edges(world: World) -> None:
    edges = {(row[0], row[1], row[2]) for row in await _graph(world.driver)}

    assert set(VAULT_EDGES) <= edges
    assert {(PARENT, "ORGANIZES", uid) for uid in (KU_A, KU_B, KU_C, STEP, PATH)} <= edges


@pytest.mark.parametrize("door", RETIRED)
async def test_a_curriculum_write_path_answers_nothing_and_writes_nothing(
    world: World, door: str
) -> None:
    method, url, form = RETIRED[door]
    before = await _graph(world.driver)

    if method == "POST":
        response = await world.client.post(url, data=form)
    else:
        response = await world.client.request(method, url)

    assert response.status_code in (404, 405), (url, response.status_code, response.text)
    assert await _graph(world.driver) == before


async def test_the_curriculum_reads_still_answer(world: World) -> None:
    enables = await world.client.get(f"/api/ku/{KU_A}/lateral/enables")
    assert enables.status_code == 200, enables.text
    assert KU_C in enables.text

    for domain, anchor in ANCHORS.items():
        blocked = await world.client.get(f"/api/{domain}/{anchor}/lateral/blocked")
        assert blocked.status_code == 200, (domain, blocked.text)
        assert KU_C in blocked.text, domain


async def test_an_activity_lateral_write_still_lands(world: World) -> None:
    """The factory keeps the writes of a domain with an owner to verify."""
    one = await create(world.client, "tasks", f"{MARK} one")
    two = await create(world.client, "tasks", f"{MARK} two")

    created = await world.client.post(
        f"/api/tasks/{one}/lateral/complementary",
        data={"target_uid": two, "synergy_description": "same trip"},
    )
    assert created.status_code == 201, created.text
    assert "COMPLEMENTARY_TO" in {edge.type for edge in await edges_between(world.driver, one, two)}

    deleted = await world.client.delete(f"/api/tasks/{one}/lateral/complementary/{two}")
    assert deleted.status_code == 200, deleted.text
    assert await edges_between(world.driver, one, two) == []
