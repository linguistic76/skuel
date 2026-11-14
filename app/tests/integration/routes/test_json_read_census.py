"""No GET route carries an entity's embedding vector, and none answers 5xx on a user's own entities.

The JSON boundary leaves the embedding fields out of every ``Entity`` it serializes
(``jsonable_content``). The rule is type-based: a door that turned an entity into a
plain dict first, or returned raw node properties, would carry the vector past it.
This census holds the invariant by behaviour. Over the bootstrapped app, signed in, it
reads every GET route in the app's own route table with a user's seeded entities, and
fails on

- a body carrying the seeded vector (any route, JSON or page), and
- a 5xx answer, named with its route, its uid and the traceback tail the boundary's
  catch-all logged (or, for a failed ``Result``, the text of the refusal).

A census reaches only the shapes its seed stores, so the seed stores every shape the
real writers produce. The six Activities come from their create doors (an Event's
``start_time`` is a native LOCAL TIME) and their edges from the create, link and
lateral doors (ISO-string stamps); the Event is linked through every family
``EVENTS_CONFIG`` names. The learner's edges come from the learning-state doors, the
entry's and the task's inferred knowledge edges and grounding stamps from the grounding
writers and the vector from the embedding writer, each stamping a native ``datetime()``. The curriculum and the entry are seeded
by hand, their edges in the vault's shapes (an Edge YAML file's through
``prepare_edge_data``). Last, every seeded node gets a native ``updated_at =
datetime()``, as a vault re-ingest stamps it.

Each request names its seed as every path parameter and under every uid query name a
door could read, with ``q`` / ``query`` / ``search`` / ``term`` set to a word in every
seeded title. A route takes a uid when its path has a parameter, its handler binds a
uid-named one, or its handler's source names a uid key or hands the query on whole;
it is read once per seed. Any other route is read once. ``/logout`` is read last,
since it ends the session.

The tree is then read a second time with a stored ``status`` on every seed that no
``EntityStatus`` names, as a raw-Cypher write or a retired member would leave it. A
read that builds a model refuses the node (``UnreadableStoredValueError``) rather than
hand the value on, so that pass fails on

- an exception that escapes the app instead of answering an error, and
- a route that serves the stray value other than the readers that hand on raw node
  properties without building a model (``RAW_PROPERTY_READERS``).
"""

from __future__ import annotations

import inspect
import logging
import re
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from starlette.routing import Route

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums import NeoLabel
from core.models.enums.pipeline import Pipeline
from core.models.relationship_names import RelationshipName
from core.services.ingestion.preparer import prepare_edge_data
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import create, signed_in_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

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

MARK = "jsoncensus"
READER = seed_user_uid(f"{MARK}_reader")
# The word in every seeded title, sent as each search door's term.
WORD = MARK

KU = f"ku.{MARK}.breath"
KU_NEXT = f"ku.{MARK}.stillness"
STEP = f"ps.{MARK}.breath"
PATH = f"lp.{MARK}.calm"
EXERCISE = f"ex.{MARK}.breath-log"
ENTRY = f"ue.{MARK}.note"

SEED_KINDS = (
    "habit",
    "goal",
    "principle",
    "task",
    "choice",
    "event",
    "ku",
    "path_step",
    "learning_path",
    "exercise",
    "user_entry",
)

# The seeded vector: one distinctive float, 1,024 times. Any body carrying the vector
# carries this literal, whatever serializer wrote it.
VECTOR_VALUE = 0.0617283945
VECTOR_TEXT = repr(VECTOR_VALUE)
DIMENSION = 1024

# The stored status of the second pass: a value no EntityStatus member names.
STRAY_STATUS = f"{MARK}-stray-status"
# The routes that serve a node's stored properties as they are, building no model —
# each serves the stray status of the second pass, and nothing else may.
RAW_PROPERTY_READERS: dict[str, str] = {
    "/api/ku/{uid}/lateral/graph": "the lateral graph's nodes are raw property maps",
    "/api/lp/{uid}/lateral/graph": "the lateral graph's nodes are raw property maps",
    "/api/ps/{uid}/lateral/graph": "the lateral graph's nodes are raw property maps",
}

# The GET routes the crawl leaves out, each with why it reads no entity. Two more are
# never in the crawl: the static files are a ``Mount`` and the websockets are
# ``WebSocketRoute``s, not ``Route``s, and the rig's ``/sign-in`` is not in the app's
# own table.
SKIPPED_PREFIXES: dict[str, str] = {
    "/metrics": "Prometheus text exposition; no entity",
    "/health": "liveness and readiness probes; no entity",
}
# A GET that ends the session: read last, so every route before it is read signed in.
SESSION_ENDING = ("/logout",)
SEARCH_NAMES = ("q", "query", "search", "term")
_PATH_PARAM = re.compile(r"\{([^}:]+)(?::[^}]+)?\}")
_UID_NAME = re.compile(r"^[a-z_]*uids?$")
# A uid name written as a string: a key some code reads, off the query string or not.
_UID_LITERAL = re.compile(r"[\"']([a-z_]*uids?)[\"']")
# The query mapping handed on whole, to a parser or into a dict.
_WHOLE_QUERY = re.compile(r"query_params\s*[),]")
_INBOUND = Path(__file__).resolve().parents[3] / "adapters" / "inbound"


@dataclass
class Census:
    """What one pass over the route tree, as the seeded user, answered."""

    requests: int = 0
    carried_vector: dict[str, set[str]] = field(default_factory=dict)
    server_errors: dict[str, list[str]] = field(default_factory=dict)
    json_answers: set[str] = field(default_factory=set)
    # seed kind -> the routes whose JSON answer named it
    seen_in_json: dict[str, set[str]] = field(default_factory=dict)
    # the routes whose answer below 500 carried the stray status
    served_stray: set[str] = field(default_factory=set)
    # read just before the first session-ending route
    signed_in_before_logout: bool | None = None
    query_names: tuple[str, ...] = ()
    routes: int = 0
    # the routes read with every seed; the rest are read once
    uid_routes: int = 0
    # skip prefix -> the GET routes it left out
    skipped: dict[str, set[str]] = field(default_factory=dict)


class _BoundaryLog(logging.Handler):
    """The records ``adapters.inbound.boundary``'s catch-all logs during one request.

    The catch-all logs through the stdlib logger, not structlog, so a 5xx's traceback
    reaches only a handler attached here.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def tail(self) -> str | None:
        """The last three lines of the request's last logged traceback, if any."""
        for record in reversed(self.records):
            if record.exc_info:
                lines = "".join(traceback.format_exception(*record.exc_info)).strip()
                return " | ".join(lines.splitlines()[-3:])
        return None


@dataclass(frozen=True)
class ReadRoute:
    """One GET route, and how its handler can take a uid."""

    path: str
    # uid-named parameters FastHTML binds from the query string
    bound_uid_names: frozenset[str]
    # a path parameter, a bound uid name, or a uid key in the handler's own source
    takes_uid: bool


def _handler(
    route: Route,
) -> tuple[Callable[..., Any], inspect.Signature]:  # boundary: any route handler
    """The handler FastHTML calls for ``route``, and the signature it binds.

    Both are free variables of FastHTML's endpoint wrapper (``_endp``'s ``f`` and
    ``sig``); a route registered some other way fails here rather than read as one
    that takes nothing.
    """
    endpoint = route.endpoint
    cells = dict(
        zip(
            endpoint.__code__.co_freevars,
            (cell.cell_contents for cell in endpoint.__closure__ or ()),
            strict=True,
        )
    )
    handler, signature = cells.get("f"), cells.get("sig")
    assert callable(handler) and isinstance(signature, inspect.Signature), route.path
    return handler, signature


def _may_read_a_uid(handler: Callable[..., Any]) -> bool:  # boundary: any route handler
    """Whether the handler's own source names a uid key or hands the query on whole."""
    try:
        source = inspect.getsource(inspect.unwrap(handler))
    except OSError, TypeError:
        return True  # no source to read: count it as taking a uid
    return bool(_UID_LITERAL.search(source) or _WHOLE_QUERY.search(source))


def _read_routes(app: FastHTMLApp, skipped: dict[str, set[str]]) -> list[ReadRoute]:
    """Every GET route but the skipped ones, the session-ending ones last.

    ``skipped`` is filled with what each skip prefix left out.
    """
    routes: list[ReadRoute] = []
    for route in app.router.routes:
        if not isinstance(route, Route) or "GET" not in (route.methods or set()):
            continue
        prefix = next((p for p in SKIPPED_PREFIXES if route.path.startswith(p)), None)
        if prefix is not None:
            skipped.setdefault(prefix, set()).add(route.path)
            continue
        handler, signature = _handler(route)
        in_path = set(_PATH_PARAM.findall(route.path))
        bound = frozenset(
            name for name in signature.parameters if _UID_NAME.match(name) and name not in in_path
        )
        takes_uid = bool(in_path or bound) or _may_read_a_uid(handler)
        routes.append(ReadRoute(route.path, bound, takes_uid))
    return sorted(routes, key=_crawl_order)


def _crawl_order(route: ReadRoute) -> tuple[bool, str]:
    return route.path in SESSION_ENDING, route.path


def _query_names(routes: list[ReadRoute]) -> tuple[str, ...]:
    """Every uid name a read door could take from the query string.

    A handler's parameters that are not path parameters are bound from the query; a
    handler, or a helper it calls, may also read one by hand, off ``query_params`` or a
    dict of it. Every uid-named string in ``adapters/inbound`` is sent: a door ignores
    a name it does not read.
    """
    names = set().union(*(route.bound_uid_names for route in routes))
    for source in _INBOUND.rglob("*.py"):
        names |= set(_UID_LITERAL.findall(source.read_text()))
    return tuple(sorted(names))


async def _run(
    driver: AsyncDriver,
    query: str,
    **params: Any,  # boundary: Cypher parameters of any type
) -> list[dict[str, Any]]:  # boundary: raw neo4j rows
    async with driver.session() as session:
        result = await session.run(query, **params)
        return [dict(record) async for record in result]


async def _post_ok(
    client: httpx.AsyncClient,
    path: str,
    **kwargs: Any,  # boundary: httpx request keywords (json=, params=)
) -> None:
    response = await client.post(path, **kwargs)
    assert response.status_code in (200, 201), (path, response.status_code, response.text)


async def _seed_curriculum(driver: AsyncDriver) -> None:
    """A published Ku pair, PathStep, LearningPath and Exercise, and the user's entry.

    Each node stores what its writer stores: ISO-string ``created_at``, the publish
    switch, and (curriculum) no owner. The edges are the vault's shapes.
    """
    created = datetime.now(UTC).isoformat()
    lateral = prepare_edge_data(
        {"from": KU, "to": KU_NEXT, "relationship": RelationshipName.PREREQUISITE_FOR.value}
    )
    await _run(
        driver,
        """
        UNWIND $kus AS ku
        MERGE (k:Entity:Ku {uid: ku.uid})
        SET k.title = ku.title, k.entity_type = 'ku', k.status = 'active',
            k.publication_state = 'published', k.created_at = $created,
            k.description = ku.title + ' description'
        WITH count(*) AS _
        MERGE (s:Entity:PathStep {uid: $step})
        SET s.title = 'Jsoncensus breath step', s.entity_type = 'path_step',
            s.status = 'active', s.publication_state = 'published', s.created_at = $created,
            s.description = 'Jsoncensus step description'
        MERGE (p:Entity:LearningPath {uid: $path})
        SET p.title = 'Jsoncensus calm path', p.entity_type = 'learning_path',
            p.status = 'active', p.publication_state = 'published', p.created_at = $created
        MERGE (x:Entity:Exercise {uid: $exercise})
        SET x.title = 'Jsoncensus breath log', x.entity_type = 'exercise', x.status = 'active',
            x.scope = 'curriculum', x.instructions = 'Log three breaths.',
            x.publication_state = 'published', x.created_at = $created
        WITH s, p, x
        MATCH (k:Ku {uid: $ku}), (n:Ku {uid: $ku_next})
        MERGE (s)-[:USES_KU]->(k)
        MERGE (s)-[:REQUIRES_KNOWLEDGE]->(n)
        MERGE (s)-[o:ORGANIZES]->(k) SET o.order = 0
        MERGE (s)-[:HAS_EXERCISE]->(x)
        MERGE (p)-[h:HAS_STEP]->(s) SET h.sequence = 0
        MERGE (k)-[l:PREREQUISITE_FOR]->(n) SET l += $lateral
        """,
        kus=[
            {"uid": KU, "title": "Jsoncensus breath awareness"},
            {"uid": KU_NEXT, "title": "Jsoncensus stillness"},
        ],
        created=created,
        step=STEP,
        path=PATH,
        exercise=EXERCISE,
        ku=KU,
        ku_next=KU_NEXT,
        lateral=lateral["properties"],
    )
    await _run(
        driver,
        """
        MATCH (u:User {uid: $user})
        MERGE (e:Entity:UserEntry {uid: $entry})
        SET e.title = 'Jsoncensus evening note', e.entity_type = 'user_entry',
            e.status = 'completed', e.user_uid = $user, e.pipeline = $pipeline,
            e.content = 'Three slow breaths before sleep.', e.created_at = $created
        MERGE (u)-[r:OWNS]->(e) SET r.created_at = $created
        """,
        user=READER,
        entry=ENTRY,
        pipeline=Pipeline.knowledge_grounded()[0].value,
        created=created,
    )


async def _seed_activities(client: httpx.AsyncClient, driver: AsyncDriver) -> dict[str, str]:
    """One of each Activity at its create door, linked through the app's own doors."""
    habit = await create(client, "habits", "Jsoncensus breathe daily", linked_knowledge_uids=[KU])
    goal = await create(
        client,
        "goals",
        "Jsoncensus calm mornings",
        required_knowledge_uids=[KU],
        supporting_habit_uids=[habit],
    )
    principle = await create(client, "principles", "Jsoncensus breath before speech")
    task = await create(
        client,
        "tasks",
        "Jsoncensus practise box breathing",
        contributes_to_goal_uids=[goal],
        reinforces_habit_uid=habit,
        applies_knowledge_uids=[KU],
        aligned_principle_uids=[principle],
        prerequisite_knowledge_uids=[KU_NEXT],
    )
    blocker = await create(client, "tasks", "Jsoncensus clear a quiet corner")
    choice = await create(
        client, "choices", "Jsoncensus morning or evening practice", informed_by_knowledge_uids=[KU]
    )
    day = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
    event = await create(
        client,
        "events",
        "Jsoncensus breathing class",
        event_date=day,
        start_time="09:30:00",
        end_time="10:15:00",
        reinforces_habit_uid=habit,
        practices_knowledge_uids=[KU],
        contributes_to_goal_uids=[goal],
        milestone_celebration_for_goal=goal,
    )
    rival = await create(
        client,
        "events",
        "Jsoncensus overlapping meeting",
        event_date=day,
        start_time="09:45:00",
        end_time="10:30:00",
    )
    await _post_ok(
        client, "/api/goals/link-principle", json={"goal_uid": goal, "principle_uid": principle}
    )
    await _post_ok(
        client, "/api/habits/link-principle", json={"habit_uid": habit, "principle_uid": principle}
    )
    await _post_ok(client, "/api/choices/link-goal", json={"choice_uid": choice, "goal_uid": goal})
    await _post_ok(
        client,
        "/api/choices/link-principle",
        json={"choice_uid": choice, "principle_uid": principle},
    )
    await _post_ok(
        client,
        "/api/principles/link-knowledge",
        json={"principle_uid": principle, "knowledge_uid": KU},
    )
    await _post_ok(
        client,
        f"/api/tasks/{blocker}/lateral/blocks",
        params={"target_uid": task, "reason": "Jsoncensus a quiet place first"},
    )
    await _post_ok(
        client,
        f"/api/events/{event}/lateral/conflicts",
        params={"target_uid": rival, "conflict_type": "time"},
    )
    await _post_ok(client, "/api/lifepath/designate", json={"life_path_uid": PATH})
    await _post_ok(
        client, "/api/goals/link-life-path", json={"goal_uid": goal, "life_path_uid": PATH}
    )
    # The event families EVENTS_CONFIG names that no door writes, as an Edge YAML file
    # writes them.
    for relationship, target in (
        (RelationshipName.EXECUTES_TASK, task),
        (RelationshipName.TRIGGERS_CHOICE, choice),
        (RelationshipName.DEMONSTRATES_PRINCIPLE, principle),
        (RelationshipName.SERVES_LIFE_PATH, PATH),
    ):
        edge = prepare_edge_data({"from": event, "to": target, "relationship": relationship.value})
        await _run(
            driver,
            f"MATCH (a {{uid: $a}}), (b {{uid: $b}}) MERGE (a)-[r:{relationship.value}]->(b) "
            "SET r += $props",
            a=event,
            b=target,
            props=edge["properties"],
        )
    edge = prepare_edge_data(
        {"from": choice, "to": event, "relationship": RelationshipName.SCHEDULES_EVENT.value}
    )
    await _run(
        driver,
        "MATCH (a {uid: $a}), (b {uid: $b}) MERGE (a)-[r:SCHEDULES_EVENT]->(b) SET r += $props",
        a=choice,
        b=event,
        props=edge["properties"],
    )
    return {
        "habit": habit,
        "goal": goal,
        "principle": principle,
        "task": task,
        "choice": choice,
        "event": event,
    }


async def _seed_learner_state(client: httpx.AsyncClient, driver: AsyncDriver) -> None:
    """The learner's edges, from the learning-state doors and the grounding writer.

    Marking the Ku understood masters the step that uses it, which ends the step's
    enrolment; the second Ku is the one left in progress.
    """
    for path in (
        f"/api/path-steps/{STEP}/start",
        f"/api/path-steps/{STEP}/mark-read",
        f"/api/path-steps/{STEP}/bookmark",
        f"/api/ku/{KU}/mark-understood",
        f"/api/ku/{KU_NEXT}/mark-studying",
    ):
        await _post_ok(client, path)
    grounding = build_production_backends(driver)["entry_grounding_backend"]
    written = await grounding.write_applies_knowledge(ENTRY, KU, 0.82)
    assert written.is_ok and written.value, written
    rows = await _run(
        driver,
        "MATCH (:User {uid: $user})-[r]->(n) WHERE n.uid IN $uids RETURN type(r) AS t, n.uid AS uid",
        user=READER,
        uids=[STEP, KU, KU_NEXT],
    )
    assert {(row["t"], row["uid"]) for row in rows} == {
        ("MASTERED", STEP),
        ("MARKED_AS_READ", STEP),
        ("BOOKMARKED", STEP),
        ("MASTERED", KU),
        ("IN_PROGRESS", KU_NEXT),
    }


async def _embed_and_restamp(driver: AsyncDriver, seeds: dict[str, str]) -> None:
    """The embedding writer's five properties on every seed, the grounding pass's stamp
    on the entry, then re-ingest's stamp on every node."""
    embeddings = build_production_backends(driver)["embeddings_backend"]
    labels = {
        "habit": NeoLabel.HABIT,
        "goal": NeoLabel.GOAL,
        "principle": NeoLabel.PRINCIPLE,
        "task": NeoLabel.TASK,
        "choice": NeoLabel.CHOICE,
        "event": NeoLabel.EVENT,
        "ku": NeoLabel.KU,
        "path_step": NeoLabel.PATH_STEP,
        "learning_path": NeoLabel.LEARNING_PATH,
        "exercise": NeoLabel.EXERCISE,
        "user_entry": NeoLabel.USER_ENTRY,
    }
    for kind, uid in seeds.items():
        stored = await embeddings.store_embedding_metadata(
            labels[kind],
            uid,
            [VECTOR_VALUE] * DIMENSION,
            "v1",
            "text-embedding-3-small",
            f"{MARK}-hash",
        )
        assert stored.is_ok and stored.value, (kind, stored)
    # The grounding passes' completion stamps, over the entry's and the task's
    # embedding text, and the task's inferred edge: the task grounding writer's shape
    # (its owner's link to KU rides from the create door, so the inferred one is the
    # Ku the task requires).
    backends = build_production_backends(driver)
    stamped = await backends["entry_grounding_backend"].stamp_grounded(ENTRY, f"{MARK}-hash", 1)
    assert stamped.is_ok, stamped
    task_grounding = backends["task_grounding_backend"]
    inferred = await task_grounding.write_applies_knowledge(seeds["task"], KU_NEXT, 0.79)
    assert inferred.is_ok and inferred.value, inferred
    task_stamped = await task_grounding.stamp_grounded(seeds["task"], f"{MARK}-hash", 1)
    assert task_stamped.is_ok, task_stamped
    rows = await _run(
        driver,
        """
        MATCH (n:Entity) WHERE n.uid IN $uids
        SET n.updated_at = datetime()
        RETURN n.uid AS uid, size(n.embedding) AS dimension, n.embedding[0] AS first,
               n.grounded_at IS NOT NULL AS grounded
        """,
        uids=[*seeds.values(), KU_NEXT],
    )
    assert {row["uid"] for row in rows} == {*seeds.values(), KU_NEXT}
    assert all(
        row["dimension"] == DIMENSION and row["first"] == VECTOR_VALUE
        for row in rows
        if row["uid"] != KU_NEXT
    )
    assert {row["uid"] for row in rows if row["grounded"]} == {ENTRY, seeds["task"]}


async def _crawl(client: httpx.AsyncClient, app: FastHTMLApp, seeds: dict[str, str]) -> Census:
    """Read every route with each seed, or once (with the task) when it takes no uid.

    A route that takes no uid answers the same whichever seed the query names, so
    reading it with every seed would only repeat one answer.
    """
    skipped: dict[str, set[str]] = {}
    routes = _read_routes(app, skipped)
    census = Census(routes=len(routes), query_names=_query_names(routes), skipped=skipped)
    log = _BoundaryLog()
    boundary = logging.getLogger("adapters.inbound.boundary")
    boundary.addHandler(log)
    try:
        for route in routes:
            if route.path in SESSION_ENDING and census.signed_in_before_logout is None:
                census.signed_in_before_logout = await _still_signed_in(client, seeds["task"])
            uids = list(seeds.values()) if route.takes_uid else [seeds["task"]]
            census.uid_routes += route.takes_uid
            for uid in uids:
                log.records.clear()
                await _read(client, census, route.path, uid, seeds, log)
    finally:
        boundary.removeHandler(log)
    return census


async def _read(
    client: httpx.AsyncClient,
    census: Census,
    path: str,
    uid: str,
    seeds: dict[str, str],
    log: _BoundaryLog,
) -> None:
    """One GET of ``path`` naming ``uid`` everywhere a door could read it."""
    params = {**dict.fromkeys(SEARCH_NAMES, WORD), **dict.fromkeys(census.query_names, uid)}
    census.requests += 1
    try:
        response = await client.get(_PATH_PARAM.sub(uid, path), params=params)
    except Exception as error:  # safety-net: an exception that escapes the app is a finding
        tail = " | ".join("".join(traceback.format_exception(error)).strip().splitlines()[-3:])
        census.server_errors.setdefault(path, []).append(f"{uid}: raised: {tail}")
        return
    if response.status_code >= 500:
        # An exception's traceback, or the refusal a failed Result answered with.
        detail = log.tail() or " ".join(response.text.split())[:200]
        census.server_errors.setdefault(path, []).append(f"{uid}: {response.status_code}: {detail}")
    body = response.text
    if STRAY_STATUS in body and response.status_code < 500:
        census.served_stray.add(path)
    if VECTOR_TEXT in body:
        census.carried_vector.setdefault(path, set()).add(uid)
    content_type = response.headers.get("content-type", "")
    if response.status_code == 200 and content_type.startswith("application/json"):
        census.json_answers.add(path)
        for kind, seed in seeds.items():
            if seed in body:
                census.seen_in_json.setdefault(kind, set()).add(path)


async def _still_signed_in(client: httpx.AsyncClient, task_uid: str) -> bool:
    response = await client.get("/api/tasks/get", params={"uid": task_uid})
    return response.status_code == 200 and response.json().get("uid") == task_uid


@dataclass(frozen=True)
class Crawls:
    """The two passes over the route tree: as seeded, then with a stray stored status."""

    census: Census
    stray: Census


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def crawls(skuel_app: FastHTMLApp) -> AsyncIterator[Crawls]:
    """Two passes over every read route, each signed in as the seeded user."""
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with signed_in_client(skuel_app, READER, MARK) as client:
        # Seeded after sign-in: the rig's setup wipes every node carrying the mark.
        await _seed_curriculum(driver)
        seeds = {
            **(await _seed_activities(client, driver)),
            "ku": KU,
            "path_step": STEP,
            "learning_path": PATH,
            "exercise": EXERCISE,
            "user_entry": ENTRY,
        }
        assert tuple(seeds) == SEED_KINDS
        await _seed_learner_state(client, driver)
        await _embed_and_restamp(driver, seeds)
        census = await _crawl(client, skuel_app, seeds)

        await _run(
            driver,
            "MATCH (n:Entity) WHERE n.uid IN $uids SET n.status = $stray",
            uids=list(seeds.values()),
            stray=STRAY_STATUS,
        )
        # The first pass ended with /logout.
        assert (await client.get(f"/sign-in/{READER}")).status_code == 200
        yield Crawls(census=census, stray=await _crawl(client, skuel_app, seeds))


@pytest_asyncio.fixture(loop_scope="module")
async def census(crawls: Crawls) -> Census:
    return crawls.census


def _listing(found: dict[str, Any]) -> str:  # boundary: route -> uids or failure lines
    """Every route a finding names, one per line, with what it answered."""
    return "\n".join(f"{path}: {sorted(found[path])}" for path in sorted(found))


async def test_no_read_carries_the_embedding_vector(census: Census) -> None:
    assert not census.carried_vector, (
        f"\n{len(census.carried_vector)} routes carry the vector:\n"
        + _listing(census.carried_vector)
    )


async def test_no_read_answers_a_server_error(census: Census) -> None:
    """Every read answers each of the user's own uids, most of them the wrong kind for
    the route, with a page, a payload or an ordinary refusal."""
    assert not census.server_errors, (
        f"\n{len(census.server_errors)} routes answer 5xx:\n" + _listing(census.server_errors)
    )


async def test_the_crawl_read_every_seed_signed_in(census: Census) -> None:
    """The controls: a crawl that read nothing, or read it signed out, would pass both
    tests above."""
    assert census.routes > 400, census.routes
    # Each skip leaves a route out; one that matches nothing has gone stale.
    assert set(census.skipped) == set(SKIPPED_PREFIXES), census.skipped
    assert census.uid_routes > 300, census.uid_routes
    once = census.routes - census.uid_routes
    assert census.requests == census.uid_routes * len(SEED_KINDS) + once
    assert {"uid", "goal_uid", "habit_uid", "principle_uid", "step_uid", "task_uids"} <= set(
        census.query_names
    )
    assert census.signed_in_before_logout is True
    assert len(census.json_answers) > 100, len(census.json_answers)
    # Every seed reached a JSON answer, so its vector had a body to ride in.
    assert {kind for kind in SEED_KINDS if not census.seen_in_json.get(kind)} == set()


async def test_a_stray_stored_value_escapes_no_read(crawls: Crawls) -> None:
    """Every read meeting the stray status answers, an error or a page, and none raises
    out of the app."""
    escaped = {
        path: lines
        for path, lines in crawls.stray.server_errors.items()
        if any(": raised: " in line for line in lines)
    }
    assert not escaped, f"\n{len(escaped)} routes raise out of the app:\n" + _listing(escaped)


async def test_no_model_hands_on_a_stray_stored_value(crawls: Crawls) -> None:
    """Only the raw-property readers serve the stray status; every read that builds a
    model refuses its node. The controls: the first pass served it nowhere, the second
    read every route as often, and its typed by-uid reads refused (a signed-out read
    would answer 401, not refuse)."""
    assert not crawls.census.served_stray, crawls.census.served_stray
    assert crawls.stray.served_stray == set(RAW_PROPERTY_READERS), sorted(crawls.stray.served_stray)
    assert crawls.stray.requests == crawls.census.requests
    refused = {
        path
        for path, lines in crawls.stray.server_errors.items()
        if any(": 500: " in line for line in lines)
    }
    assert {f"/api/{domain}/get" for domain in ("tasks", "goals", "habits", "events")} <= refused
