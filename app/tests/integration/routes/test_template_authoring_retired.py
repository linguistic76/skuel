"""Activity Templates are authored only in the content vault (ADR-091 S8).

No template JSON path is registered: for each kind, ``/api/pathstep-{kind}-templates/``
create, get, update, delete and list, and the PathStep attach, detach and list-by-ps,
answer 404 or 405 to an admin, sent a well-formed body, and leave the graph unchanged.

Controls: the vault sync writes the template and its edge — an ``_tmpl.md`` file
writes the template node and a PathStep's ``{domain}_template_uids:`` writes its
``HAS_*_TEMPLATE`` edge — and the teacher's templates panel reads them. The panel
and the engagement spawn's loader bind both ends of the edge by kind, so an edge
written past the vault (by raw Cypher here) never hands either one another user's
Goal.
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
    signed_in_client,
    sync_vault,
    touch_forward,
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

MARK = "zzztplretired"
ADMIN = f"user_{MARK}"
# The other user's client wipes every uid carrying its own mark, so neither mark may
# contain the other.
OTHER_MARK = "zzzothertpl"
OTHER = f"user_{OTHER_MARK}"
PS = f"ps.{MARK}.host"
FOREIGN_GOAL_TITLE = f"{OTHER_MARK}-goal"

# (kind, uid prefix, PathStep frontmatter field, edge)
KINDS: tuple[tuple[str, str, str, str], ...] = (
    ("task", "tt", "task_template_uids", "HAS_TASK_TEMPLATE"),
    ("goal", "gt", "goal_template_uids", "HAS_GOAL_TEMPLATE"),
    ("habit", "ht", "habit_template_uids", "HAS_HABIT_TEMPLATE"),
    ("event", "et", "event_template_uids", "HAS_EVENT_TEMPLATE"),
    ("choice", "ct", "choice_template_uids", "HAS_CHOICE_TEMPLATE"),
    ("principle", "pt", "principle_template_uids", "HAS_PRINCIPLE_TEMPLATE"),
)


def attached(prefix: str) -> str:
    return f"{prefix}.{MARK}.attached"


def spare(prefix: str) -> str:
    return f"{prefix}.{MARK}.spare"


def _write(vault: Path, name: str, text: str) -> None:
    path = vault / name
    path.write_text(text)
    touch_forward(path)


def _vault(vault: Path) -> None:
    """Per kind, one template the PathStep attaches and one it does not."""
    for kind, prefix, _field, _edge in KINDS:
        for uid, role in ((attached(prefix), "attached"), (spare(prefix), "spare")):
            _write(
                vault,
                f"{prefix}_{role}_tmpl.md",
                f"---\ntype: {kind}_template\nuid: {uid}\ntitle: {MARK} {kind} {role}\n---\n"
                "Body.\n",
            )
    lines = ["type: ps", f"uid: {PS}", f"title: {MARK} host"]
    for _kind, prefix, field, _edge in KINDS:
        lines += [f"{field}:", f"  - {attached(prefix)}"]
    _write(vault, "host.md", "---\n" + "\n".join(lines) + "\n---\nThe lesson.\n")


async def _graph(driver: AsyncDriver) -> dict[str, Any]:  # boundary: raw graph read
    """Every marked node with its title, every edge between marked nodes, and the
    number of template nodes in the graph — what any template write would change.

    The marked reads name no label in the pattern, so no ``uid`` index is planned
    for the ``CONTAINS`` while the boot's index sync may still be building one."""
    async with driver.session() as session:
        record = await (
            await session.run(
                """
                CALL () {
                    MATCH (n) WHERE n.uid CONTAINS $mark AND 'Entity' IN labels(n)
                    WITH n ORDER BY n.uid
                    RETURN collect([n.uid, n.title]) AS nodes
                }
                CALL () {
                    MATCH (a)-[r]->(b)
                    WHERE a.uid CONTAINS $mark AND b.uid CONTAINS $mark
                      AND 'Entity' IN labels(a) AND 'Entity' IN labels(b)
                    WITH a.uid AS source, type(r) AS type, b.uid AS target
                    ORDER BY source, type, target
                    RETURN collect([source, type, target]) AS edges
                }
                CALL () {
                    MATCH (t:Entity) WHERE t.entity_type ENDS WITH '_template'
                    RETURN count(t) AS templates
                }
                RETURN nodes, edges, templates
                """,
                mark=MARK,
            )
        ).single()
    assert record is not None
    return dict(record)


class World:
    def __init__(
        self,
        driver: AsyncDriver,
        admin: httpx.AsyncClient,
        foreign_goal: str,
        foreign_task: str,
    ) -> None:
        self.driver = driver
        self.admin = admin
        self.foreign_goal = foreign_goal
        self.foreign_task = foreign_task

    async def panel(self) -> httpx.Response:
        return await self.admin.get(f"/teaching/ps/{PS}/templates")


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(
    skuel_app: Any,  # boundary: fasthtml-app
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[World]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    vault = tmp_path_factory.mktemp("content_vault")
    async with (
        signed_in_client(skuel_app, OTHER, OTHER_MARK) as other,
        signed_in_client(skuel_app, ADMIN, MARK) as admin,
    ):
        async with driver.session() as session:
            await session.run(
                """
                MATCH (u:User {uid: $uid})
                SET u.username = $uid, u.display_name = $uid, u.email = $uid + '@example.com',
                    u.role = 'admin', u.created_at = datetime(), u.updated_at = datetime()
                """,
                uid=ADMIN,
            )
        foreign_goal = await create(other, "goals", FOREIGN_GOAL_TITLE)
        foreign_task = await create(other, "tasks", f"{OTHER_MARK}-task")
        _vault(vault)
        await sync_vault(driver, vault)
        yield World(driver, admin, foreign_goal, foreign_task)


def _unregistered_paths() -> dict[str, tuple[str, str, dict[str, Any] | None]]:  # boundary: JSON
    """Each unregistered path of each kind with a well-formed body, aimed at the
    vault's templates: a spare to attach, the attached one to update, detach and
    delete. ``delete`` runs last, so each write finds the node or edge it names."""
    doors: dict[str, tuple[str, str, dict[str, Any] | None]] = {}  # boundary: JSON bodies
    for kind, prefix, _field, _edge in KINDS:
        base = f"/api/pathstep-{kind}-templates"
        mine = attached(prefix)
        doors |= {
            f"{kind}-create": ("POST", f"{base}/create", {"title": f"{MARK} {kind} created"}),
            f"{kind}-get": ("GET", f"{base}/get?uid={mine}", None),
            f"{kind}-list": ("GET", f"{base}/list", None),
            f"{kind}-list-by-ps": ("GET", f"{base}/list-by-ps?ps_uid={PS}", None),
            f"{kind}-update": ("POST", f"{base}/update?uid={mine}", {"title": "Renamed"}),
            f"{kind}-attach": (
                "POST",
                f"{base}/attach?ps_uid={PS}&template_uid={spare(prefix)}",
                None,
            ),
            f"{kind}-detach": ("POST", f"{base}/detach?ps_uid={PS}&template_uid={mine}", None),
            f"{kind}-delete": ("POST", f"{base}/delete?uid={mine}", None),
        }
    return doors


UNREGISTERED = _unregistered_paths()


async def test_the_vault_writes_the_templates_and_their_edges(world: World) -> None:
    graph = await _graph(world.driver)

    edges = {tuple(edge) for edge in graph["edges"]}
    for kind, prefix, _field, edge in KINDS:
        assert [attached(prefix), f"{MARK} {kind} attached"] in graph["nodes"]
        assert [spare(prefix), f"{MARK} {kind} spare"] in graph["nodes"]
        assert (PS, edge, attached(prefix)) in edges
        assert (PS, edge, spare(prefix)) not in edges


@pytest.mark.parametrize("door", UNREGISTERED)
async def test_an_unregistered_path_answers_nothing_and_writes_nothing(
    world: World, door: str
) -> None:
    method, url, body = UNREGISTERED[door]
    before = await _graph(world.driver)

    response = await world.admin.request(method, url, json=body)

    assert response.status_code in (404, 405), (url, response.status_code, response.text)
    assert await _graph(world.driver) == before


async def test_the_templates_panel_reads_what_the_vault_attached(world: World) -> None:
    response = await world.panel()

    assert response.status_code == 200, response.text
    for kind, _prefix, _field, _edge in KINDS:
        assert f"{MARK} {kind} attached" in response.text
        assert f"{MARK} {kind} spare" not in response.text


async def test_the_panel_never_reads_a_stray_edges_far_node(world: World) -> None:
    """An edge to another user's Goal does not hand the panel that Goal."""
    await write_edge(world.driver, PS, "HAS_GOAL_TEMPLATE", world.foreign_goal)
    try:
        response = await world.panel()
        assert response.status_code == 200, response.text
        assert f"{MARK} goal attached" in response.text
        assert FOREIGN_GOAL_TITLE not in response.text
        assert world.foreign_goal not in response.text
    finally:
        async with world.driver.session() as session:
            await session.run(
                "MATCH (:PathStep {uid: $ps})-[r:HAS_GOAL_TEMPLATE]->(:Goal) DELETE r", ps=PS
            )


async def test_the_spawn_loader_never_reads_a_stray_edges_far_node(world: World) -> None:
    """The template loader the engagement spawn walks binds both ends as the panel does.

    A stray edge from the step to another user's Goal, and a template hung off another
    user's Task posing as the step, are neither a template of this step nor a step at
    all: the loader returns the real template alone, and nothing for the Task.
    """
    from adapters.persistence.neo4j.backends.templates_backends import (
        ChoiceTemplateBackend,
        EventTemplateBackend,
        GoalTemplateBackend,
        HabitTemplateBackend,
        PrincipleTemplateBackend,
        TaskTemplateBackend,
    )
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from adapters.persistence.neo4j.ps_engagement_backend import PsEngagementBackend
    from core.models.enums.neo_labels import NeoLabel
    from core.models.templates import (
        ChoiceTemplate,
        EventTemplate,
        GoalTemplate,
        HabitTemplate,
        PrincipleTemplate,
        TaskTemplate,
    )
    from core.services.ps_engagement._template_loader import _TemplateLoader

    driver = world.driver
    loader = _TemplateLoader(
        PsEngagementBackend(Neo4jQueryExecutor(driver)),
        TaskTemplateBackend(
            driver, NeoLabel.TASK_TEMPLATE, TaskTemplate, base_label=NeoLabel.ENTITY
        ),
        GoalTemplateBackend(
            driver, NeoLabel.GOAL_TEMPLATE, GoalTemplate, base_label=NeoLabel.ENTITY
        ),
        HabitTemplateBackend(
            driver, NeoLabel.HABIT_TEMPLATE, HabitTemplate, base_label=NeoLabel.ENTITY
        ),
        EventTemplateBackend(
            driver, NeoLabel.EVENT_TEMPLATE, EventTemplate, base_label=NeoLabel.ENTITY
        ),
        ChoiceTemplateBackend(
            driver, NeoLabel.CHOICE_TEMPLATE, ChoiceTemplate, base_label=NeoLabel.ENTITY
        ),
        PrincipleTemplateBackend(
            driver, NeoLabel.PRINCIPLE_TEMPLATE, PrincipleTemplate, base_label=NeoLabel.ENTITY
        ),
    )
    await write_edge(driver, PS, "HAS_GOAL_TEMPLATE", world.foreign_goal)
    await write_edge(driver, world.foreign_task, "HAS_GOAL_TEMPLATE", attached("gt"))
    try:
        bundle = await loader.load(PS)
        assert bundle.is_ok, bundle
        assert [goal.uid for goal in bundle.value.goals] == [attached("gt")]

        posing = await loader.load(world.foreign_task)
        assert posing.is_ok, posing
        assert posing.value.goals == ()
    finally:
        async with driver.session() as session:
            await session.run(
                "MATCH (:PathStep {uid: $ps})-[r:HAS_GOAL_TEMPLATE]->(:Goal) DELETE r", ps=PS
            )
            await session.run(
                "MATCH ({uid: $task})-[r:HAS_GOAL_TEMPLATE]->() DELETE r", task=world.foreign_task
            )
