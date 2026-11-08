"""DATA_FLOW_WALKTHROUGH.md is read against the request it describes.

The page's own request body goes to the bootstrapped app while a profiler records every
first-party function it reaches. Each table must name stops that run, in that order, in
the file it says; the stored node and the response must be the ones the page shows. The
page's sample cannot expire unnoticed, and a renamed stop fails here.

``app/docs/tutorials/DATA_FLOW_WALKTHROUGH.md`` is in CI's ``py`` path filter, so a
docs-only edit to the page still runs this module.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

import httpx
import pytest
import pytest_asyncio

from adapters.inbound.fasthtml_types import FastHTMLApp
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.task.task import Task
from core.services.principles._embodiment_mixin import _EmbodimentMixin
from core.services.tasks.task_relationships import TaskRelationships
from tests.helpers.run_clock import RUN_TODAY
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import signed_in_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable
    from types import FrameType

    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.usefixtures("held_run_clock"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

_ROOT = Path(__file__).resolve().parents[3]
_DOC = (_ROOT / "docs" / "tutorials" / "DATA_FLOW_WALKTHROUGH.md").read_text()
_SOURCE_ROOTS = (f"{_ROOT}/core/", f"{_ROOT}/adapters/")

MARK = "dfwalk"
CALLER = seed_user_uid(f"{MARK}_caller")
STRANGER = seed_user_uid(f"{MARK}_stranger")
DRAFT_KU = f"ku.{MARK}.draft"
INFERRED_KU = f"ku.{MARK}.inferred"
UNKNOWN_KU = f"ku.{MARK}.unknown"
PATH_STEP = f"ps.{MARK}.step"

#: A value on the page that a run fills in and the page does not predict.
_UNPREDICTED = frozenset({"<now>"})

#: The keyword-inference properties no writer stores on a task: its knowledge is its edges.
_KEYWORD_INFERENCE_KEYS = frozenset(
    {"knowledge_confidence_scores", "knowledge_inference_metadata", "learning_opportunities_count"}
)

#: The ``Entity`` fields the embedding writer fills, which no JSON response carries.
_EMBEDDING_KEYS = frozenset({"embedding", "embedding_model", "embedding_updated_at"})


def _section(heading: str) -> str:
    return _DOC.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]


def _json_fence(heading: str) -> dict[str, object]:
    match = re.search(r"```json\n(.*?)\n```", _section(heading), re.DOTALL)
    assert match, f"no json block under {heading!r}"
    return json.loads(match.group(1))


def _listed(body: Mapping[str, object], key: str) -> list[str]:
    values = body[key]
    assert isinstance(values, list), key
    return [str(value) for value in values]


def _stops(heading: str) -> list[tuple[str, str]]:
    """The table under ``heading``, as ``(file, symbol)`` in the page's order."""
    rows = re.findall(
        r"^\| (\d+) \| `([^`]+)` \| `/([^`]+)` \|", _section(heading), flags=re.MULTILINE
    )
    assert [int(number) for number, _, _ in rows] == list(range(1, len(rows) + 1))
    return [(file, symbol) for _, symbol, file in rows]


@dataclass
class _Calls:
    """Every first-party function entered while installed as the profiler, in order."""

    seen: list[tuple[str, str]] = field(default_factory=list)

    def __call__(self, frame: FrameType, event: str, _arg: object) -> None:
        code = frame.f_code
        if event == "call" and code.co_filename.startswith(_SOURCE_ROOTS):
            self.seen.append((code.co_filename.removeprefix(f"{_ROOT}/"), code.co_qualname))

    def not_reached_in_order(self, stops: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """The stops that do not run after the stop before them."""
        remaining = iter(self.seen)
        return [
            stop
            for stop in stops
            if not any(
                file == stop[0] and (name == stop[1] or name.startswith(f"{stop[1]}.<locals>."))
                for file, name in remaining
            )
        ]


async def _profiled(
    send: Callable[[], Awaitable[httpx.Response]],
) -> tuple[httpx.Response, _Calls]:
    calls = _Calls()
    previous = sys.getprofile()
    sys.setprofile(calls)
    try:
        return await send(), calls
    finally:
        sys.setprofile(previous)


class Stored(TypedDict):
    labels: set[str]
    properties: dict[str, object]
    #: ``(edge type, far-end uid)`` for every edge leaving the task
    outgoing: set[tuple[str, str]]
    #: ``(edge type, near-end uid)`` for every edge reaching the task
    incoming: set[tuple[str, str]]


async def _stored(driver: AsyncDriver, uid: str) -> Stored:
    async with driver.session() as session:
        node = await (
            await session.run("MATCH (t {uid: $uid}) RETURN labels(t) AS labels, t", uid=uid)
        ).single()
        assert node is not None, uid
        outgoing = await (
            await session.run(
                "MATCH ({uid: $uid})-[r]->(o) RETURN type(r) AS type, o.uid AS uid", uid=uid
            )
        ).data()
        incoming = await (
            await session.run(
                "MATCH (o)-[r]->({uid: $uid}) RETURN type(r) AS type, o.uid AS uid", uid=uid
            )
        ).data()
    return Stored(
        labels=set(node["labels"]),
        properties=dict(node["t"]),
        outgoing={(row["type"], row["uid"]) for row in outgoing},
        incoming={(row["type"], row["uid"]) for row in incoming},
    )


@dataclass
class World:
    client: httpx.AsyncClient
    stranger: httpx.AsyncClient
    driver: AsyncDriver
    skuel_app: FastHTMLApp
    body: dict[str, object]
    created: httpx.Response
    create_calls: _Calls
    read: httpx.Response
    read_calls: _Calls
    stored: Stored

    @property
    def uid(self) -> str:
        return str(self.created.json()["uid"])

    def known_values(self) -> dict[str, str]:
        return {"<generated>": self.uid, "<caller>": CALLER, "<today>": RUN_TODAY.isoformat()}

    def knowledge_uid(self, key: str) -> str:
        return _listed(self.body, key)[0]


async def _seed(driver: AsyncDriver, uids_and_labels: Mapping[str, tuple[str, str, str]]) -> None:
    async with driver.session() as session:
        for uid, (label, entity_type, publication_state) in uids_and_labels.items():
            await session.run(
                f"MERGE (n:Entity:{label} {{uid: $uid}}) "
                "SET n.entity_type = $entity_type, n.title = $uid, "
                "n.publication_state = $publication_state",
                uid=uid,
                entity_type=entity_type,
                publication_state=publication_state,
            )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(skuel_app: FastHTMLApp) -> AsyncIterator[World]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    body = _json_fence("The request")
    seeds = {
        uid: ("Ku", "ku", "published")
        for key in ("applies_knowledge_uids", "prerequisite_knowledge_uids")
        for uid in _listed(body, key)
    }
    async with (
        signed_in_client(skuel_app, CALLER, MARK) as client,
        signed_in_client(skuel_app, STRANGER, f"{MARK}stranger") as stranger,
    ):
        await _seed(
            driver,
            {
                **seeds,
                DRAFT_KU: ("Ku", "ku", "draft"),
                INFERRED_KU: ("Ku", "ku", "published"),
                PATH_STEP: ("PathStep", "path_step", "published"),
            },
        )

        async def create() -> httpx.Response:
            return await client.post("/api/tasks/create", json=body)

        created, create_calls = await _profiled(create)
        assert created.status_code == 201, created.text
        uid = created.json()["uid"]

        async def read() -> httpx.Response:
            return await client.get(f"/api/tasks/get?uid={uid}")

        fetched, read_calls = await _profiled(read)
        yield World(
            client=client,
            stranger=stranger,
            driver=driver,
            skuel_app=skuel_app,
            body=body,
            created=created,
            create_calls=create_calls,
            read=fetched,
            read_calls=read_calls,
            stored=await _stored(driver, uid),
        )
        async with driver.session() as session:
            await session.run(
                "UNWIND $uids AS uid MATCH (n {uid: uid}) DETACH DELETE n", uids=[*seeds]
            )


def _mismatches(
    shown: Mapping[str, object], actual: Mapping[str, object], known: Mapping[str, str]
) -> dict[str, tuple[object, object]]:
    """The shown keys whose value is not the actual one; a placeholder stands for a value."""
    found: dict[str, tuple[object, object]] = {}
    for key, value in shown.items():
        if key not in actual:
            found[key] = (value, "<absent>")
        elif isinstance(value, str) and value in _UNPREDICTED:
            continue
        else:
            wanted = known.get(value, value) if isinstance(value, str) else value
            if actual[key] != wanted:
                found[key] = (wanted, actual[key])
    return found


async def test_the_create_table_is_the_path_the_request_takes(world: World) -> None:
    assert world.create_calls.not_reached_in_order(_stops("The create path")) == []


async def test_the_read_table_is_the_path_the_read_takes(world: World) -> None:
    assert world.read.status_code == 200, world.read.text
    assert world.read_calls.not_reached_in_order(_stops("The read path")) == []


@pytest.mark.parametrize("calls", ["create_calls", "read_calls"])
async def test_neither_path_touches_a_dto(world: World, calls: str) -> None:
    recorder: _Calls = getattr(world, calls)
    reached = {file for file, _ in recorder.seen}
    assert reached  # a silent profiler would pass the next line
    assert not reached & {"core/models/task/task_dto.py", "core/models/dto_helpers.py"}


async def test_the_read_modify_write_the_page_names_uses_a_dto() -> None:
    assert "`PrinciplesService.create_principle_expression` (`_EmbodimentMixin`)" in _section(
        "Where DTOs live"
    ).replace("\n", " ")
    source = inspect.getsource(_EmbodimentMixin.create_principle_expression)
    assert "principle_data.to_dto()" in source
    assert "dto.to_dict()" in source


async def test_the_stored_node_is_the_one_the_page_shows(world: World) -> None:
    shown = _json_fence("What the graph holds")
    properties = world.stored["properties"]
    assert world.stored["labels"] == {"Entity", "Task"}
    assert set(shown) == set(properties)
    assert _mismatches(shown, properties, world.known_values()) == {}
    assert f"{len(properties)} properties" in _section("What the graph holds")


async def test_the_edges_are_the_ones_the_page_shows(world: World) -> None:
    fence = _section("What the graph holds").split("```text\n", 1)[1].split("\n```", 1)[0]
    edge_types = set(re.findall(r"\[:(\w+)\]", fence))
    applied = world.knowledge_uid("applies_knowledge_uids")
    required = world.knowledge_uid("prerequisite_knowledge_uids")
    assert world.stored["outgoing"] == {
        ("APPLIES_KNOWLEDGE", applied),
        ("REQUIRES_KNOWLEDGE", required),
    }
    assert world.stored["incoming"] == {("OWNS", CALLER)}
    assert edge_types == {"APPLIES_KNOWLEDGE", "REQUIRES_KNOWLEDGE", "OWNS"}
    assert f'[:APPLIES_KNOWLEDGE]->(:Entity:Ku {{uid: "{applied}"}})' in fence
    assert f'[:REQUIRES_KNOWLEDGE]->(:Entity:Ku {{uid: "{required}"}})' in fence


async def test_the_response_is_every_task_field(world: World) -> None:
    body = world.created.json()
    task_fields = {task_field.name for task_field in dataclasses.fields(Task)}
    assert task_fields >= _EMBEDDING_KEYS
    assert set(body) == task_fields - _EMBEDDING_KEYS
    assert _mismatches(_json_fence("The response"), body, world.known_values()) == {}
    assert f"{len(body)} keys" in _section("The response")
    assert "applies_knowledge_uids" not in body


async def test_a_read_answers_what_the_create_answered(world: World) -> None:
    assert world.read.json() == world.created.json()


async def test_an_embedded_tasks_read_carries_no_vector(world: World) -> None:
    created = await world.client.post("/api/tasks/create", json={"title": f"{MARK} embedded"})
    assert created.status_code == 201, created.text
    uid = created.json()["uid"]
    async with world.driver.session() as session:
        # The properties EmbeddingsBackend.store_embedding_metadata writes.
        await session.run(
            """
            MATCH (t:Task {uid: $uid})
            SET t.embedding = $vector, t.embedding_version = 'v1',
                t.embedding_model = 'text-embedding-3-small',
                t.embedding_updated_at = datetime(), t.embedding_text_hash = 'hash'
            """,
            uid=uid,
            vector=[0.25] * 1024,
        )
    stored = await _stored(world.driver, uid)
    assert len(stored["properties"]["embedding"]) == 1024  # the read below has one to drop
    model = await world.skuel_app.state.services.tasks.get_for_user(uid, CALLER)
    assert model.value.embedding is not None  # AI ranking reads it off the model

    fetched = await world.client.get(f"/api/tasks/get?uid={uid}")
    listed = await world.client.get("/api/tasks/list")
    assert fetched.status_code == listed.status_code == 200, (fetched.text, listed.text)
    [row] = [row for row in listed.json()["items"] if row["uid"] == uid]
    assert set(fetched.json()) == set(row) == set(world.read.json())
    assert _EMBEDDING_KEYS.isdisjoint(fetched.json())
    assert len(fetched.content) < 4096, len(fetched.content)
    read_path = _section("The read path")
    assert all(f"`{key}`" in read_path for key in _EMBEDDING_KEYS)
    assert "absent, never null" in read_path


async def test_the_relationships_sample_reads_the_lists_back(world: World) -> None:
    tasks_service = world.skuel_app.state.services.tasks
    rels = await TaskRelationships.fetch(world.uid, tasks_service.relationships)
    assert list(rels.applies_knowledge_uids) == [world.knowledge_uid("applies_knowledge_uids")]
    assert list(rels.prerequisite_knowledge_uids) == [
        world.knowledge_uid("prerequisite_knowledge_uids")
    ]


async def test_the_node_holds_no_keyword_inference(world: World) -> None:
    """The node the page shows carries none of the three keyword-inference properties."""
    assert _KEYWORD_INFERENCE_KEYS.isdisjoint(world.stored["properties"])
    assert _KEYWORD_INFERENCE_KEYS.isdisjoint(world.created.json())
    assert not any(key in _DOC for key in _KEYWORD_INFERENCE_KEYS)
    assert "<inferred>" not in _DOC


async def test_an_inferred_link_reads_back_beside_the_owners(world: World) -> None:
    """The sample's ``applies_knowledge_uids`` holds both; the removal door takes only one."""
    created = await world.client.post("/api/tasks/create", json=world.body)
    assert created.status_code == 201, created.text
    uid = created.json()["uid"]
    owners = world.knowledge_uid("applies_knowledge_uids")
    grounding = world.skuel_app.state.services.task_grounding
    written = await grounding.backend.write_applies_knowledge(uid, INFERRED_KU, 0.8)
    assert written.is_ok and written.value is True

    rels = await TaskRelationships.fetch(uid, world.skuel_app.state.services.tasks.relationships)

    assert set(rels.applies_knowledge_uids) == {owners, INFERRED_KU}
    for ku_uid, status in ((owners, 404), (INFERRED_KU, 200)):
        removed = await world.client.post(
            "/api/tasks/grounding/remove", params={"uid": uid, "ku_uid": ku_uid}
        )
        assert removed.status_code == status, (ku_uid, removed.text)
    rels = await TaskRelationships.fetch(uid, world.skuel_app.state.services.tasks.relationships)
    assert list(rels.applies_knowledge_uids) == [owners]


@pytest.mark.parametrize(
    ("refused", "keeps_known_ku"),
    [(UNKNOWN_KU, False), (UNKNOWN_KU, True), (DRAFT_KU, False), (PATH_STEP, False)],
)
async def test_a_refused_link_still_answers_201(
    world: World, refused: str, keeps_known_ku: bool
) -> None:
    known = world.knowledge_uid("applies_knowledge_uids")
    knowledge = [refused, known] if keeps_known_ku else [refused]
    response = await world.client.post(
        "/api/tasks/create",
        json={"title": f"{MARK} refused link", "applies_knowledge_uids": knowledge},
    )
    assert response.status_code == 201, response.text
    stored = await _stored(world.driver, response.json()["uid"])
    assert stored["outgoing"] == ({("APPLIES_KNOWLEDGE", known)} if keeps_known_ku else set())


async def test_a_past_due_date_answers_400(world: World) -> None:
    response = await world.client.post(
        "/api/tasks/create", json={**world.body, "due_date": "2020-01-01"}
    )
    assert response.status_code == 400, response.text


async def test_a_foreign_read_answers_the_same_404_as_a_missing_uid(world: World) -> None:
    foreign = await world.stranger.get(f"/api/tasks/get?uid={world.uid}")
    missing = await world.stranger.get("/api/tasks/get?uid=task_0000000000000000")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["code"] == missing.json()["code"]
    assert foreign.json()["message"] == missing.json()["message"]
