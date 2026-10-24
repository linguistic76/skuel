"""PathSteps and learning paths are authored only in the content vault.

ADR-091 S8: the admin PathStep doors (attach to and detach from a path, a semantic
relationship, content, tags, organize, unorganize, reorder) and the form-template
link and unlink to a PathStep are gone. Each answers 404 or 405 to an admin, sent
with a body the retired door accepted, and the graph is unchanged.

Controls: the vault sync writes what those doors wrote — a learning path file's
``connections.contains_steps`` writes ``HAS_STEP``, a step file's ``organizes``
writes ``ORGANIZES``, and an Edge YAML file writes ``EMBEDS_FORM`` (R7.3) — and the
PathStep reads and the FormTemplate CRUD (N5) still answer the same admin.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import signed_in_client, sync_vault, touch_forward

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

MARK = "zzzpslpretired"
ADMIN = seed_user_uid(f"{MARK}")
KU = f"ku.{MARK}.idea"
STEP_ONE = f"ps.{MARK}.one"
STEP_TWO = f"ps.{MARK}.two"
STEP_THREE = f"ps.{MARK}.three"
PATH = f"lp.{MARK}.path"


def _write(vault: Path, name: str, text: str) -> None:
    path = vault / name
    path.write_text(text)
    touch_forward(path)


def _vault(vault: Path, form_uid: str) -> None:
    _write(vault, "idea.md", f"---\ntype: ku\nuid: {KU}\ntitle: {MARK} idea\n---\nAn idea.\n")
    _write(
        vault,
        "one.md",
        f"---\ntype: ps\nuid: {STEP_ONE}\ntitle: {MARK} one\nuses_kus:\n  - {KU}\n"
        f"organizes:\n  - {STEP_THREE}\ntags:\n  - kept\n---\nThe first lesson.\n",
    )
    for uid, name in ((STEP_TWO, "two"), (STEP_THREE, "three")):
        _write(
            vault,
            f"{name}.md",
            f"---\ntype: ps\nuid: {uid}\ntitle: {MARK} {name}\n---\nA lesson.\n",
        )
    _write(
        vault,
        "path.md",
        f"---\ntype: lp\nuid: {PATH}\ntitle: {MARK} path\nconnections:\n  contains_steps:\n"
        f"    - {STEP_ONE}\n---\nA path.\n",
    )
    _write(
        vault,
        "one-embeds-form.yaml",
        f"type: Edge\nfrom: {STEP_ONE}\nto: {form_uid}\nrelationship: EMBEDS_FORM\n",
    )


async def _graph(driver: AsyncDriver, form_uid: str) -> dict[str, Any]:  # boundary: raw graph read
    """Every edge between this file's nodes, with its properties, and the first step's
    authored fields — what any retired door would change."""
    async with driver.session() as session:
        edges = await (
            await session.run(
                """
                MATCH (a:Entity)-[r]->(b:Entity)
                WHERE (a.uid CONTAINS $mark OR a.uid = $form)
                  AND (b.uid CONTAINS $mark OR b.uid = $form)
                WITH a.uid AS from_uid, type(r) AS type, b.uid AS to_uid, properties(r) AS props
                ORDER BY from_uid, type, to_uid
                RETURN collect([from_uid, type, to_uid, props]) AS rows
                """,
                mark=MARK,
                form=form_uid,
            )
        ).single()
        step = await (
            await session.run(
                "MATCH (s:Entity {uid: $uid}) RETURN s.title AS title, s.content AS content, "
                "s.tags AS tags",
                uid=STEP_ONE,
            )
        ).single()
    assert edges is not None and step is not None
    return {"edges": edges["rows"], "step": dict(step)}


def _edge_types(graph: dict[str, Any]) -> set[tuple[str, str, str]]:  # boundary: raw graph read
    return {(row[0], row[1], row[2]) for row in graph["edges"]}


class World:
    def __init__(self, driver: AsyncDriver, client: httpx.AsyncClient, form_uid: str) -> None:
        self.driver = driver
        self.client = client
        self.form_uid = form_uid


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
        # The FormTemplate comes from its own door, which stays (N5).
        created = await client.post(
            "/api/form-templates/create",
            json={
                "title": f"{MARK} form",
                "form_schema": [{"name": "reflection", "type": "text", "label": "Reflection"}],
            },
        )
        assert created.status_code == 201, created.text
        form_uid = created.json()["uid"]
        try:
            _vault(vault, form_uid)
            await sync_vault(driver, vault)
            yield World(driver, client, form_uid)
        finally:
            async with driver.session() as session:
                await session.run("MATCH (n {uid: $uid}) DETACH DELETE n", uid=form_uid)


# Each retired door with a body it accepted, aimed at the vault-written graph.
# ``FORM`` stands for the FormTemplate's generated uid, known only at run time.
# ``reorder`` runs before ``unorganize``: each must find the edge it would change.
FORM = "<form-template-uid>"
RETIRED: dict[str, tuple[str, str, dict[str, Any]]] = {  # boundary: JSON bodies
    "attach-to-path": (
        "POST",
        f"/api/path-steps/attach-to-path?step_uid={STEP_TWO}",
        {"path_uid": PATH, "sequence": 3},
    ),
    "detach-from-path": (
        "POST",
        f"/api/path-steps/detach-from-path?step_uid={STEP_ONE}",
        {"path_uid": PATH},
    ),
    "relationships": (
        "POST",
        f"/api/path-steps/relationships?uid={STEP_ONE}",
        {"target_uid": STEP_TWO, "type": "cross:related_to", "strength": 0.8},
    ),
    "content": (
        "POST",
        f"/api/path-steps/content?uid={STEP_ONE}",
        {"content": "Rewritten", "title": "Renamed"},
    ),
    "add-tags": ("POST", f"/api/path-steps/tags?uid={STEP_ONE}", {"tags": ["added"]}),
    "remove-tags": ("DELETE", f"/api/path-steps/tags?uid={STEP_ONE}", {"tags": ["kept"]}),
    "organize": (
        "POST",
        "/api/path-steps/organize",
        {"parent_uid": STEP_ONE, "child_uid": STEP_TWO, "order": 1},
    ),
    "reorder": (
        "POST",
        "/api/path-steps/reorder",
        {"parent_uid": STEP_ONE, "child_uid": STEP_THREE, "new_order": 5},
    ),
    "unorganize": (
        "POST",
        "/api/path-steps/unorganize",
        {"parent_uid": STEP_ONE, "child_uid": STEP_THREE},
    ),
    "link-form": (
        "POST",
        "/api/form-templates/link-path-step",
        {"form_template_uid": FORM, "ps_uid": STEP_TWO},
    ),
    "unlink-form": (
        "POST",
        "/api/form-templates/unlink-path-step",
        {"form_template_uid": FORM, "ps_uid": STEP_ONE},
    ),
}


async def test_the_vault_writes_the_edges_the_retired_doors_wrote(world: World) -> None:
    graph = await _graph(world.driver, world.form_uid)

    assert {
        (PATH, "HAS_STEP", STEP_ONE),
        (STEP_ONE, "ORGANIZES", STEP_THREE),
        (STEP_ONE, "EMBEDS_FORM", world.form_uid),
        (STEP_ONE, "USES_KU", KU),
    } <= _edge_types(graph)
    assert graph["step"]["tags"] == ["kept"]


@pytest.mark.parametrize("door", RETIRED)
async def test_a_retired_door_answers_nothing_and_writes_nothing(world: World, door: str) -> None:
    method, url, template = RETIRED[door]
    body = {key: world.form_uid if value == FORM else value for key, value in template.items()}
    before = await _graph(world.driver, world.form_uid)

    response = await world.client.request(method, url, json=body)

    assert response.status_code in (404, 405), (url, response.status_code, response.text)
    assert await _graph(world.driver, world.form_uid) == before


async def test_the_reads_and_the_form_crud_still_answer_the_admin(world: World) -> None:
    children = await world.client.get(f"/api/path-steps/{STEP_ONE}/organized-children")
    assert children.status_code == 200, children.text
    assert STEP_THREE in children.text

    form = await world.client.get(f"/api/form-templates/get?uid={world.form_uid}")
    assert form.status_code == 200, form.text
