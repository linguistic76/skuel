"""A link door admits the far end it is handed, over real HTTP and a real graph.

A link door takes the uid of an entity the caller owns and the uid of something to
link it to. The far end is admitted where the edge is written
(``UnifiedRelationshipService`` → ``core/services/mixins/link_edge_guard.py``): it
exists, is of the kind the door links to, and is owned by the source's owner or is
published shared content.

The doors:

- ``POST /api/{goals,habits,principles}/link-knowledge`` — the far end is a Ku;
- ``POST /api/events/update`` and ``POST /events/edit`` — ``milestone_celebration_for_goal``
  is a Goal, ``reinforces_habit_uid`` a Habit;
- ``POST /api/principles/link?uid=<principle>`` — ``target_uid`` is a goal, habit, Ku,
  principle or choice, per ``link_type``;
- ``POST /api/choices/link-principle`` — ``principle_uid`` is a Principle, written as
  ``(Principle)-[:INFORMS_CHOICE]->(Choice)``: the edge the principle's door writes.

The contract, per door:

- the caller's own entity of the right kind (or a shared Ku — one with no
  ``publication_state`` or one marked published) links, and the edge the door names
  is the one written;
- another user's entity is refused exactly as a uid that names nothing — same status,
  same body, same toast header — and no edge is written;
- an entity of the wrong kind is refused the same way, the caller's own included, and
  so is a Ku marked ``publication_state: draft``;
- a refused Events update changes nothing: not a property, not an existing edge.

The routes are registered through the bootstrap's own entry points over the composed
app's services, on a ``fast_app`` with real session middleware and a sign-in route.
The writers no route reaches are held to the same rule at the service, and one create
door (``POST /api/tasks/create``) to the same rule over a list: it drops the draft and
keeps the rest.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from neo4j import AsyncDriver
from starlette.responses import PlainTextResponse

from adapters.inbound.auth.session import set_current_user
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.fasthtml_types import Request
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums import PrincipleLinkType, PublicationState, RecurrencePattern
from core.models.type_hints import EntityUID, UserUID
from core.services.mixins.link_edge_guard import (
    GOAL_FAR_END,
    HABIT_FAR_END,
    KNOWLEDGE_FAR_END,
)
from core.utils.result_simplified import ErrorCategory
from tests.helpers.lateral_routes_client import without_timestamp

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

CALLER = "user_nb2b_caller"
OTHER = "user_nb2b_other"  # owns the foreign entities; never signs in
USERS = (CALLER, OTHER)

# Text only the other user's entities carry — it must reach no response.
FOREIGN_MARK = "nb2b-foreign-private"

_KINDS = ("Goal", "Habit", "Principle", "Event", "Task", "Choice")
OWN = {kind: f"{kind.lower()}_nb2b_own" for kind in _KINDS}
FOREIGN = {kind: f"{kind.lower()}_nb2b_foreign" for kind in _KINDS}
OWN_SECOND_PRINCIPLE = "principle_nb2b_own_second"
SHARED_KU = "ku_nb2b_shared"  # no publication_state: the whole pre-existing corpus
PUBLISHED_KU = "ku_nb2b_published"  # publication_state: published
DRAFT_KU = "ku_nb2b_draft"  # publication_state: draft
SHARED_STEP = "ps_nb2b_shared"

_SEEDED = (
    *OWN.values(),
    *FOREIGN.values(),
    OWN_SECOND_PRINCIPLE,
    SHARED_KU,
    PUBLISHED_KU,
    DRAFT_KU,
    SHARED_STEP,
)

OWN_EVENT_TITLE = "caller-owned Event"

# Reads every edge among the seeded nodes as ``(source, type, target)``.
EdgeReader = Callable[[], Awaitable[set[tuple[str, str, str]]]]


@dataclass(frozen=True)
class Door:
    """One link door: how to ask it, the edge it writes, and what its far end may be."""

    label: str
    url: str
    source_field: str | None  # body field naming the caller's entity; None = in the URL
    source_kind: str
    far_field: str
    relationship: str
    far_kind: str  # "Ku" or one of _KINDS
    extra: tuple[tuple[str, str], ...] = ()
    incoming: bool = False
    # Wrong kinds a door must refuse beyond the generic pair: a kind its edge type also
    # admits from another door (a habit informs a choice too, but is no principle).
    confusable: tuple[str, ...] = ()

    @property
    def source_uid(self) -> str:
        return OWN[self.source_kind]

    def body(self, far_uid: str) -> dict[str, str]:
        body = {self.far_field: far_uid, **dict(self.extra)}
        if self.source_field is not None:
            body[self.source_field] = self.source_uid
        return body

    def edge(self, far_uid: str) -> tuple[str, str, str]:
        if self.incoming:
            return (far_uid, self.relationship, self.source_uid)
        return (self.source_uid, self.relationship, far_uid)

    @property
    def linkable(self) -> str:
        """A far end this door links: shared content, or the caller's own of its kind."""
        if self.far_kind == "Ku":
            return SHARED_KU
        if self.far_kind == self.source_kind:
            return OWN_SECOND_PRINCIPLE
        return OWN[self.far_kind]

    @property
    def foreign(self) -> str:
        """Another user's entity — of the door's own kind where that kind is owned."""
        return FOREIGN["Task"] if self.far_kind == "Ku" else FOREIGN[self.far_kind]

    @property
    def wrong_kinds(self) -> tuple[str, ...]:
        """Uids that are not what this door links to — a Ku marked draft included."""
        if self.far_kind == "Ku":
            return (OWN["Task"], SHARED_STEP, DRAFT_KU)
        other = "Task" if self.far_kind != "Task" else "Goal"
        return (OWN[other], SHARED_KU, *self.confusable)

    @property
    def missing(self) -> str:
        return f"{self.far_kind.lower()}_nb2b_missing"


def _principle_link(link_type: str, relationship: str, far_kind: str, **kw: bool) -> Door:
    return Door(
        f"POST /api/principles/link [{link_type}]",
        f"/api/principles/link?uid={OWN['Principle']}",
        None,
        "Principle",
        "target_uid",
        relationship,
        far_kind,
        extra=(("link_type", link_type),),
        incoming=kw.get("incoming", False),
    )


DOORS = (
    Door(
        "POST /api/goals/link-knowledge",
        "/api/goals/link-knowledge",
        "goal_uid",
        "Goal",
        "knowledge_uid",
        "REQUIRES_KNOWLEDGE",
        "Ku",
    ),
    Door(
        "POST /api/habits/link-knowledge",
        "/api/habits/link-knowledge",
        "habit_uid",
        "Habit",
        "knowledge_uid",
        "REINFORCES_KNOWLEDGE",
        "Ku",
    ),
    Door(
        "POST /api/principles/link-knowledge",
        "/api/principles/link-knowledge",
        "principle_uid",
        "Principle",
        "knowledge_uid",
        "GROUNDED_IN_KNOWLEDGE",
        "Ku",
    ),
    Door(
        "POST /api/events/update [goal]",
        f"/api/events/update?uid={OWN['Event']}",
        None,
        "Event",
        "milestone_celebration_for_goal",
        "CELEBRATES_GOAL",
        "Goal",
    ),
    Door(
        "POST /api/events/update [habit]",
        f"/api/events/update?uid={OWN['Event']}",
        None,
        "Event",
        "reinforces_habit_uid",
        "REINFORCES_HABIT",
        "Habit",
    ),
    _principle_link("goal", "SUPPORTS_GOAL", "Goal"),
    _principle_link("habit", "INSPIRES_HABIT", "Habit"),
    _principle_link("knowledge", "GROUNDED_IN_KNOWLEDGE", "Ku"),
    _principle_link("principle", "SUPPORTS_PRINCIPLE", "Principle", incoming=True),
    _principle_link("choice", "INFORMS_CHOICE", "Choice"),
    Door(
        "POST /api/choices/link-principle",
        "/api/choices/link-principle",
        "choice_uid",
        "Choice",
        "principle_uid",
        "INFORMS_CHOICE",
        "Principle",
        incoming=True,
        confusable=(OWN["Habit"], SHARED_STEP),
    ),
)
_DOOR_IDS = [door.label for door in DOORS]

_WRONG_KIND_CASES = [(door, uid) for door in DOORS for uid in door.wrong_kinds]
_WRONG_KIND_IDS = [f"{door.label} <- {uid}" for door, uid in _WRONG_KIND_CASES]

_KU_DOORS = [door for door in DOORS if door.far_kind == "Ku"]
_PUBLISHED_CASES = [(door, uid) for door in _KU_DOORS for uid in (SHARED_KU, PUBLISHED_KU)]
_PUBLISHED_IDS = [f"{door.label} <- {uid}" for door, uid in _PUBLISHED_CASES]


def _toast(response: httpx.Response, uid: str) -> str:
    """The error message the boundary mirrors into a header, with the requested uid masked."""
    return response.headers["X-Toast-Message"].replace(uid, "<uid>")


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid IN $uids OR n.user_uid IN $users DETACH DELETE n",
            uids=[*USERS, *_SEEDED],
            users=list(USERS),
        )


async def _seed_owned(driver: AsyncDriver, *, kind: str, uid: str, owner: str, title: str) -> None:
    async with driver.session() as session:
        await session.run(
            f"""
            MATCH (u:User {{uid: $owner}})
            MERGE (e:Entity:{kind} {{uid: $uid}})
            SET e.title = $title, e.description = $title + ' description',
                e.entity_type = $entity_type, e.status = 'active', e.user_uid = $owner,
                e.recurrence_pattern = 'daily', e.event_date = date('2026-06-15'),
                e.priority = 'medium'
            MERGE (u)-[:OWNS]->(e)
            """,
            uid=uid,
            owner=owner,
            title=title,
            entity_type=kind.lower(),
        )


async def _seed_shared(
    driver: AsyncDriver,
    *,
    label: str,
    entity_type: str,
    uid: str,
    publication_state: PublicationState | None = None,
) -> None:
    async with driver.session() as session:
        await session.run(
            f"""
            MERGE (e:Entity:{label} {{uid: $uid}})
            SET e.title = $uid, e.entity_type = $entity_type, e.status = 'active',
                e.publication_state = $publication_state
            """,
            uid=uid,
            entity_type=entity_type,
            publication_state=publication_state.value if publication_state else None,
        )


@pytest_asyncio.fixture(loop_scope="session")
async def driver(skuel_app) -> AsyncDriver:
    """Two users owning one entity of each Activity kind, plus shared Kus and a PathStep.

    The three Kus are the three publication states a node can read as: no property
    (published), ``published``, and ``draft``.
    """
    graph: AsyncDriver = skuel_app.state.services.neo4j_driver
    await _wipe(graph)
    async with graph.session() as session:
        for uid in USERS:
            await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=uid)
    for kind in _KINDS:
        await _seed_owned(
            graph, kind=kind, uid=OWN[kind], owner=CALLER, title=f"caller-owned {kind}"
        )
        await _seed_owned(
            graph, kind=kind, uid=FOREIGN[kind], owner=OTHER, title=f"{FOREIGN_MARK} {kind}"
        )
    await _seed_owned(
        graph,
        kind="Principle",
        uid=OWN_SECOND_PRINCIPLE,
        owner=CALLER,
        title="caller-owned second Principle",
    )
    await _seed_shared(graph, label="Ku", entity_type="ku", uid=SHARED_KU)
    await _seed_shared(
        graph,
        label="Ku",
        entity_type="ku",
        uid=PUBLISHED_KU,
        publication_state=PublicationState.PUBLISHED,
    )
    await _seed_shared(
        graph, label="Ku", entity_type="ku", uid=DRAFT_KU, publication_state=PublicationState.DRAFT
    )
    await _seed_shared(graph, label="PathStep", entity_type="path_step", uid=SHARED_STEP)
    yield graph
    await _wipe(graph)


@pytest_asyncio.fixture(loop_scope="session")
async def edges(driver: AsyncDriver) -> EdgeReader:
    """Clears every link edge among the seeded nodes, and reads them back."""

    async def read() -> set[tuple[str, str, str]]:
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (a)-[r]->(b)
                WHERE a.uid IN $uids AND b.uid IN $uids
                RETURN a.uid AS source, type(r) AS rel, b.uid AS target
                """,
                uids=list(_SEEDED),
            )
            return {(row["source"], row["rel"], row["target"]) async for row in result}

    async with driver.session() as session:
        await session.run(
            "MATCH (a)-[r]->(b) WHERE a.uid IN $uids AND b.uid IN $uids DELETE r",
            uids=list(_SEEDED),
        )
        await session.run(
            "MATCH (e:Event {uid: $uid}) SET e.title = $title",
            uid=OWN["Event"],
            title=OWN_EVENT_TITLE,
        )
    return read


def _app(skuel_app):
    from fasthtml.common import fast_app

    from adapters.inbound.choices_routes import create_choices_routes
    from adapters.inbound.events_routes import create_events_routes
    from adapters.inbound.goals_routes import create_goals_routes
    from adapters.inbound.habits_routes import create_habits_routes
    from adapters.inbound.principles_routes import create_principles_routes
    from adapters.inbound.tasks_routes import create_tasks_routes

    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="nb2b-link-door-test-key")
    services = skuel_app.state.services
    for create_routes in (
        create_choices_routes,
        create_goals_routes,
        create_habits_routes,
        create_principles_routes,
        create_events_routes,
        create_tasks_routes,
    ):
        create_routes(app, rt, services)

    @rt("/sign-in/{uid}")
    def sign_in(request: Request, uid: str) -> PlainTextResponse:
        set_current_user(request, user_uid=uid)
        return PlainTextResponse("ok")

    return app


@pytest_asyncio.fixture(loop_scope="session")
async def client(skuel_app, driver):
    """An HTTP client signed in as ``CALLER``, carrying a CSRF cookie and header."""
    token = mint_token()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(skuel_app)),
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
    ) as http:
        assert (await http.get(f"/sign-in/{CALLER}")).status_code == 200
        yield http


class TestOwnOrSharedFarEnd:
    @pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
    async def test_links_and_writes_the_edge_the_door_names(
        self, client: httpx.AsyncClient, edges: EdgeReader, door: Door
    ) -> None:
        response = await client.post(door.url, json=door.body(door.linkable))

        assert response.status_code == 200, response.text
        assert await edges() == {door.edge(door.linkable)}


class TestPublishedKu:
    """A Ku with no ``publication_state`` and one marked published both link."""

    @pytest.mark.parametrize(("door", "ku_uid"), _PUBLISHED_CASES, ids=_PUBLISHED_IDS)
    async def test_links(
        self, client: httpx.AsyncClient, edges: EdgeReader, door: Door, ku_uid: str
    ) -> None:
        response = await client.post(door.url, json=door.body(ku_uid))

        assert response.status_code == 200, response.text
        assert await edges() == {door.edge(ku_uid)}


class TestAnotherUsersFarEnd:
    @pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
    async def test_is_refused_as_a_missing_uid_is_and_writes_no_edge(
        self, client: httpx.AsyncClient, edges: EdgeReader, door: Door
    ) -> None:
        foreign = await client.post(door.url, json=door.body(door.foreign))
        missing = await client.post(door.url, json=door.body(door.missing))

        assert foreign.status_code == 404, foreign.text
        assert FOREIGN_MARK not in foreign.text
        assert missing.status_code == 404, missing.text
        assert without_timestamp(foreign) == without_timestamp(missing)
        assert _toast(foreign, door.foreign) == _toast(missing, door.missing)
        assert await edges() == set()


class TestWrongKindFarEnd:
    @pytest.mark.parametrize(("door", "far_uid"), _WRONG_KIND_CASES, ids=_WRONG_KIND_IDS)
    async def test_is_refused_as_a_missing_uid_is_and_writes_no_edge(
        self, client: httpx.AsyncClient, edges: EdgeReader, door: Door, far_uid: str
    ) -> None:
        wrong = await client.post(door.url, json=door.body(far_uid))
        missing = await client.post(door.url, json=door.body(door.missing))

        assert wrong.status_code == 404, wrong.text
        assert without_timestamp(wrong) == without_timestamp(missing)
        assert _toast(wrong, far_uid) == _toast(missing, door.missing)
        assert await edges() == set()


class TestTheSourceItself:
    async def test_a_principle_is_not_linked_to_itself(
        self, client: httpx.AsyncClient, edges: EdgeReader
    ) -> None:
        response = await client.post(
            f"/api/principles/link?uid={OWN['Principle']}",
            json={"link_type": "principle", "target_uid": OWN["Principle"]},
        )

        assert response.status_code == 400, response.text
        assert await edges() == set()

    async def test_the_query_uid_names_the_principle_and_the_body_the_target(
        self, client: httpx.AsyncClient, edges: EdgeReader
    ) -> None:
        response = await client.post(
            f"/api/principles/link?uid={OWN['Principle']}",
            json={"link_type": "knowledge", "target_uid": SHARED_KU},
        )

        assert response.status_code == 200, response.text
        assert response.json() == {
            "principle_uid": OWN["Principle"],
            "target_uid": SHARED_KU,
            "link_type": "knowledge",
        }
        assert await edges() == {(OWN["Principle"], "GROUNDED_IN_KNOWLEDGE", SHARED_KU)}


class TestPrincipleLinkTypes:
    """``link_type`` is one of ``PrincipleLinkType`` on the write and on the read."""

    async def test_an_unknown_link_type_is_a_bad_request_and_writes_no_edge(
        self, client: httpx.AsyncClient, edges: EdgeReader
    ) -> None:
        response = await client.post(
            f"/api/principles/link?uid={OWN['Principle']}",
            json={"link_type": "task", "target_uid": OWN["Task"]},
        )

        assert response.status_code == 400, response.text
        assert await edges() == set()

    @pytest.mark.parametrize("link_type", list(PrincipleLinkType))
    async def test_the_links_read_returns_what_the_link_door_wrote(
        self, client: httpx.AsyncClient, edges: EdgeReader, link_type: PrincipleLinkType
    ) -> None:
        door = next(door for door in DOORS if ("link_type", link_type.value) in door.extra)
        linked = await client.post(door.url, json=door.body(door.linkable))
        assert linked.status_code == 200, linked.text

        of_type = await client.get(
            f"/api/principles/links?uid={OWN['Principle']}&link_type={link_type.value}"
        )
        every = await client.get(f"/api/principles/links?uid={OWN['Principle']}")

        expected = [{"target_uid": door.linkable, "link_type": link_type.value}]
        assert of_type.status_code == 200, of_type.text
        assert of_type.json() == expected
        assert every.json() == expected

    async def test_the_links_read_refuses_an_unknown_link_type(
        self, client: httpx.AsyncClient, edges: EdgeReader
    ) -> None:
        response = await client.get(f"/api/principles/links?uid={OWN['Principle']}&link_type=task")

        assert response.status_code == 400, response.text


class TestRefusedEventUpdate:
    """A refused link is refused before the update's first write."""

    @pytest.mark.parametrize(
        ("field", "far_uid"),
        [
            ("milestone_celebration_for_goal", FOREIGN["Goal"]),
            ("reinforces_habit_uid", FOREIGN["Habit"]),
            ("reinforces_habit_uid", FOREIGN["Task"]),
            ("reinforces_habit_uid", OWN["Task"]),
        ],
    )
    async def test_changes_no_property_and_no_existing_edge(
        self,
        client: httpx.AsyncClient,
        driver: AsyncDriver,
        edges: EdgeReader,
        field: str,
        far_uid: str,
    ) -> None:
        linked = await client.post(
            f"/api/events/update?uid={OWN['Event']}",
            json={
                "milestone_celebration_for_goal": OWN["Goal"],
                "reinforces_habit_uid": OWN["Habit"],
            },
        )
        assert linked.status_code == 200, linked.text
        before = await edges()
        assert before == {
            (OWN["Event"], "CELEBRATES_GOAL", OWN["Goal"]),
            (OWN["Event"], "REINFORCES_HABIT", OWN["Habit"]),
        }

        refused = await client.post(
            f"/api/events/update?uid={OWN['Event']}",
            json={"title": "renamed by a refused update", field: far_uid},
        )

        assert refused.status_code == 404, refused.text
        assert FOREIGN_MARK not in refused.text
        assert await edges() == before
        async with driver.session() as session:
            row = await (
                await session.run("MATCH (e {uid: $uid}) RETURN e.title AS title", uid=OWN["Event"])
            ).single()
        assert row["title"] == OWN_EVENT_TITLE

    async def test_a_cleared_link_is_still_cleared(
        self, client: httpx.AsyncClient, edges: EdgeReader
    ) -> None:
        linked = await client.post(
            f"/api/events/update?uid={OWN['Event']}",
            json={"milestone_celebration_for_goal": OWN["Goal"]},
        )
        assert linked.status_code == 200, linked.text
        assert await edges() == {(OWN["Event"], "CELEBRATES_GOAL", OWN["Goal"])}

        cleared = await client.post(
            f"/api/events/update?uid={OWN['Event']}",
            json={"milestone_celebration_for_goal": None},
        )

        assert cleared.status_code == 200, cleared.text
        assert await edges() == set()


class TestEventEditForm:
    """``POST /events/edit`` — the form door onto the same update path."""

    async def test_the_callers_own_goal_and_habit_link(
        self, client: httpx.AsyncClient, edges: EdgeReader
    ) -> None:
        response = await client.post(
            f"/events/edit?uid={OWN['Event']}",
            data={
                "milestone_celebration_for_goal": OWN["Goal"],
                "reinforces_habit_uid": OWN["Habit"],
            },
        )

        assert response.status_code < 400, response.text
        assert await edges() == {
            (OWN["Event"], "CELEBRATES_GOAL", OWN["Goal"]),
            (OWN["Event"], "REINFORCES_HABIT", OWN["Habit"]),
        }

    @pytest.mark.parametrize(
        ("field", "far_uid"),
        [
            ("milestone_celebration_for_goal", FOREIGN["Goal"]),
            ("reinforces_habit_uid", FOREIGN["Habit"]),
            ("reinforces_habit_uid", OWN["Task"]),
        ],
    )
    async def test_another_users_or_a_wrong_kind_far_end_writes_no_edge(
        self, client: httpx.AsyncClient, edges: EdgeReader, field: str, far_uid: str
    ) -> None:
        response = await client.post(f"/events/edit?uid={OWN['Event']}", data={field: far_uid})

        assert FOREIGN_MARK not in response.text
        assert await edges() == set()


class TestWritersNoRouteReaches:
    """The facade link methods behind no route are held to the same rule."""

    async def test_goal_to_habit(self, skuel_app, edges: EdgeReader) -> None:
        goals = skuel_app.state.services.goals

        for far_uid in (FOREIGN["Habit"], OWN["Task"], "habit_nb2b_missing"):
            refused = await goals.link_goal_to_habit(OWN["Goal"], far_uid)
            assert refused.is_error, far_uid
            assert refused.expect_error().code == "NOT_FOUND_HABIT"
        assert await edges() == set()

        linked = await goals.link_goal_to_habit(OWN["Goal"], OWN["Habit"])
        assert linked.is_ok, linked.error
        assert await edges() == {(OWN["Habit"], "SUPPORTS_GOAL", OWN["Goal"])}

    async def test_choice_to_habit(self, skuel_app, edges: EdgeReader) -> None:
        choices = skuel_app.state.services.choices

        refused = await choices.link_choice_to_habit(OWN["Choice"], FOREIGN["Habit"])
        assert refused.is_error
        assert await edges() == set()

        linked = await choices.link_choice_to_habit(OWN["Choice"], OWN["Habit"])
        assert linked.is_ok, linked.error
        assert await edges() == {(OWN["Choice"], "IMPACTS_HABIT", OWN["Habit"])}

    async def test_task_to_knowledge(self, skuel_app, edges: EdgeReader) -> None:
        tasks = skuel_app.state.services.tasks

        for far_uid in (FOREIGN["Task"], SHARED_STEP, DRAFT_KU):
            refused = await tasks.link_task_to_knowledge(OWN["Task"], far_uid)
            assert refused.is_error, far_uid
        assert await edges() == set()

        linked = await tasks.link_task_to_knowledge(OWN["Task"], SHARED_KU)
        assert linked.is_ok, linked.error
        assert await edges() == {(OWN["Task"], "APPLIES_KNOWLEDGE", SHARED_KU)}

    async def test_event_to_knowledge_writes_nothing_when_one_far_end_is_refused(
        self, skuel_app, edges: EdgeReader
    ) -> None:
        events = skuel_app.state.services.events

        refused = await events.link_event_to_knowledge(OWN["Event"], [SHARED_KU, FOREIGN["Task"]])
        assert refused.is_error
        assert await edges() == set()

        linked = await events.link_event_to_knowledge(OWN["Event"], [SHARED_KU])
        assert linked.is_ok, linked.error
        assert await edges() == {(OWN["Event"], "APPLIES_KNOWLEDGE", SHARED_KU)}

    async def test_event_to_habit(self, skuel_app, edges: EdgeReader) -> None:
        events = skuel_app.state.services.events

        refused = await events.link_event_to_habit(OWN["Event"], FOREIGN["Habit"])
        assert refused.is_error
        assert await edges() == set()

    @pytest.mark.parametrize("habit_uid", [FOREIGN["Habit"], OWN["Task"], "habit_nb2b_missing"])
    async def test_recurring_events_are_not_created_for_a_habit_that_is_not_the_users(
        self, skuel_app, driver: AsyncDriver, edges: EdgeReader, habit_uid: str
    ) -> None:
        services = skuel_app.state.services
        context = await services.user.context_builder.build(UserUID(CALLER))
        assert context.is_ok, context.error

        for_habit = await services.events.create_recurring_events_for_habit(
            habit_uid, context.value, RecurrencePattern.DAILY, days_to_create=2
        )
        scheduled = await services.events.create_recurring_events(
            UserUID(CALLER),
            "practice",
            RecurrencePattern.DAILY,
            days_to_create=2,
            reinforces_habit_uid=habit_uid,
        )

        assert for_habit.is_error
        assert scheduled.is_error
        async with driver.session() as session:
            row = await (
                await session.run(
                    "MATCH (e:Event) WHERE e.user_uid IN $users AND NOT e.uid IN $seeded "
                    "RETURN count(e) AS created",
                    users=list(USERS),
                    seeded=list(_SEEDED),
                )
            ).single()
        assert row["created"] == 0


class TestTheOwnerIsReadFromTheSource:
    """No caller passes a user: the far end must be the source's owner's or shared."""

    async def test_an_owned_source_links_to_its_owners_entities_and_shared_content(
        self, skuel_app, driver
    ) -> None:
        relationships = skuel_app.state.services.goals.relationships
        source = EntityUID(OWN["Goal"])

        assert (await relationships.admit_far_ends(source, [OWN["Habit"]], HABIT_FAR_END)).is_ok
        assert (await relationships.admit_far_ends(source, [SHARED_KU], KNOWLEDGE_FAR_END)).is_ok
        refused = await relationships.admit_far_ends(source, [FOREIGN["Habit"]], HABIT_FAR_END)
        assert refused.is_error
        assert refused.expect_error().details["reason"] == "cross_user"

    async def test_a_shared_source_links_to_shared_content_only(self, skuel_app, driver) -> None:
        relationships = skuel_app.state.services.goals.relationships
        source = EntityUID(SHARED_STEP)

        assert (await relationships.admit_far_ends(source, [SHARED_KU], KNOWLEDGE_FAR_END)).is_ok
        for owned in (OWN["Goal"], FOREIGN["Goal"]):
            refused = await relationships.admit_far_ends(source, [owned], GOAL_FAR_END)
            assert refused.is_error, owned
            assert refused.expect_error().details["reason"] == "cross_user"

    async def test_a_draft_is_refused_from_an_owned_and_a_shared_source(
        self, skuel_app, driver
    ) -> None:
        relationships = skuel_app.state.services.goals.relationships

        for source in (OWN["Goal"], SHARED_STEP):
            refused = await relationships.admit_far_ends(
                EntityUID(source), [DRAFT_KU], KNOWLEDGE_FAR_END
            )
            assert refused.is_error, source
            assert refused.expect_error().details["reason"] == "draft"

    async def test_a_source_that_names_nothing_is_not_found(self, skuel_app, driver) -> None:
        relationships = skuel_app.state.services.goals.relationships

        refused = await relationships.admit_far_ends(
            EntityUID("goal_nb2b_missing"), [SHARED_KU], KNOWLEDGE_FAR_END
        )

        assert refused.is_error
        assert refused.expect_error().category == ErrorCategory.NOT_FOUND
        assert refused.expect_error().details["identifier"] == "goal_nb2b_missing"


class TestCreateDoor:
    """``POST /api/tasks/create`` — a create door drops the draft and keeps the rest."""

    async def test_the_draft_link_is_dropped_and_the_published_ones_kept(
        self, client: httpx.AsyncClient, driver: AsyncDriver
    ) -> None:
        response = await client.post(
            "/api/tasks/create",
            json={
                "title": "nb2f create door",
                "applies_knowledge_uids": [SHARED_KU, DRAFT_KU, PUBLISHED_KU],
            },
        )

        assert response.status_code == 201, response.text
        task_uid = response.json()["uid"]
        async with driver.session() as session:
            result = await session.run(
                "MATCH (:Task {uid: $uid})-[r:APPLIES_KNOWLEDGE]->(k) RETURN k.uid AS ku",
                uid=task_uid,
            )
            linked = {row["ku"] async for row in result}
        assert linked == {SHARED_KU, PUBLISHED_KU}
