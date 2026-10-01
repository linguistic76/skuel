"""The intelligence route set, per scope, over real HTTP.

``IntelligenceRouteFactory`` registers context and insights for a domain at
either scope, and analytics — the signed-in user's own aggregate — for a
user-owned domain alone. Shared curriculum has no per-user set to aggregate, so
PathSteps and LearningPaths have no ``/analytics`` route.

The routes are registered here through the bootstrap's own entry points
(``create_pathways_routes`` and the six ``create_{activity}_routes``) over the
composed app's services, on a ``fast_app`` with real session middleware and a
sign-in route — so each domain's ``DomainRouteConfig`` reaches the factory as it
does in the app. The composed app's own route table is read too.

The contract:

- ``GET /api/path-steps/analytics`` and ``GET /api/pathways/analytics`` are 404;
- the same two domains' ``/context`` and ``/insights`` answer 200 for a real
  PathStep and LearningPath, neither insights payload carries
  ``min_confidence``, and a path's insights count its ``HAS_STEP`` steps;
- the six Activity domains answer 200 on ``/analytics``, and on ``/context``
  and ``/insights`` for an entity the caller owns.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from starlette.responses import PlainTextResponse

from adapters.inbound.auth.session import set_current_user
from adapters.inbound.fasthtml_types import Request
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

USER = "user_f7b1_reader"
KU = "ku.f7b1.atom"
PS = "ps.f7b1.step"
LP = "lp.f7b1.path"

ACTIVITY_DOMAINS = ("tasks", "goals", "habits", "events", "choices", "principles")
ACTIVITY_ANCHORS = {
    "tasks": ("Task", "task", "task_f7b1_owned"),
    "goals": ("Goal", "goal", "goal_f7b1_owned"),
    "habits": ("Habit", "habit", "habit_f7b1_owned"),
    "events": ("Event", "event", "event_f7b1_owned"),
    "choices": ("Choice", "choice", "choice_f7b1_owned"),
    "principles": ("Principle", "principle", "principle_f7b1_owned"),
}
CURRICULUM_ANCHORS = {"path-steps": PS, "pathways": LP}
_UIDS = [USER, KU, PS, LP, *(uid for _, _, uid in ACTIVITY_ANCHORS.values())]


@pytest_asyncio.fixture(loop_scope="session")
async def seeded_graph(skuel_app):
    """One LearningPath holding one PathStep that uses one Ku, and one owned
    entity per Activity domain."""
    driver = skuel_app.state.services.neo4j_driver
    async with driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=_UIDS)
        await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=USER)
        await session.run(
            """
            MERGE (ku:Entity:Ku {uid: $ku})
            SET ku.title = 'F7b-1 atom', ku.entity_type = 'ku', ku.status = 'active'
            MERGE (ps:Entity:PathStep {uid: $ps})
            SET ps.title = 'F7b-1 step', ps.entity_type = 'path_step', ps.status = 'active'
            MERGE (lp:Entity:LearningPath {uid: $lp})
            SET lp.title = 'F7b-1 path', lp.entity_type = 'learning_path', lp.status = 'active'
            MERGE (lp)-[:HAS_STEP {sequence: 1}]->(ps)
            MERGE (ps)-[:USES_KU]->(ku)
            """,
            ku=KU,
            ps=PS,
            lp=LP,
        )
        for label, entity_type, uid in ACTIVITY_ANCHORS.values():
            await session.run(
                f"""
                MATCH (u:User {{uid: $user}})
                MERGE (e:Entity:{label} {{uid: $uid}})
                SET e.title = $uid, e.entity_type = $entity_type, e.status = 'active',
                    e.user_uid = $user
                MERGE (u)-[:OWNS]->(e)
                """,
                user=USER,
                uid=uid,
                entity_type=entity_type,
            )
    yield
    async with driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=_UIDS)


@pytest_asyncio.fixture(loop_scope="session")
async def client(skuel_app, seeded_graph):
    """An HTTP client over the eight routed domains' routes, signed in as ``USER``."""
    from fasthtml.common import fast_app

    from adapters.inbound.choices_routes import create_choices_routes
    from adapters.inbound.events_routes import create_events_routes
    from adapters.inbound.goals_routes import create_goals_routes
    from adapters.inbound.habits_routes import create_habits_routes
    from adapters.inbound.pathways_routes import create_pathways_routes
    from adapters.inbound.principles_routes import create_principles_routes
    from adapters.inbound.tasks_routes import create_tasks_routes

    services = skuel_app.state.services
    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="f7b1-route-set-test-key")
    create_pathways_routes(app, rt, services, None)
    create_tasks_routes(app, rt, services)
    create_goals_routes(app, rt, services)
    create_habits_routes(app, rt, services)
    create_events_routes(app, rt, services)
    create_choices_routes(app, rt, services)
    create_principles_routes(app, rt, services)

    @rt("/sign-in/{uid}")
    def sign_in(request: Request, uid: str) -> PlainTextResponse:
        set_current_user(request, user_uid=uid)
        return PlainTextResponse("ok")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        assert (await http.get(f"/sign-in/{USER}")).status_code == 200
        yield http


class TestCurriculumHasNoAnalyticsRoute:
    @pytest.mark.parametrize("domain", sorted(CURRICULUM_ANCHORS))
    async def test_analytics_is_not_found(self, client: httpx.AsyncClient, domain: str) -> None:
        response = await client.get(f"/api/{domain}/analytics")

        assert response.status_code == 404, response.text

    @pytest.mark.parametrize("domain", sorted(CURRICULUM_ANCHORS))
    async def test_the_composed_app_registers_no_analytics_path(
        self, skuel_app, domain: str
    ) -> None:
        paths = {getattr(route, "path", None) for route in skuel_app.routes}

        assert f"/api/{domain}/analytics" not in paths
        assert f"/api/{domain}/context" in paths
        assert f"/api/{domain}/insights" in paths


class TestCurriculumKeepsContextAndInsights:
    @pytest.mark.parametrize(("domain", "uid"), sorted(CURRICULUM_ANCHORS.items()))
    async def test_context_answers(self, client: httpx.AsyncClient, domain: str, uid: str) -> None:
        response = await client.get(f"/api/{domain}/context", params={"uid": uid})

        assert response.status_code == 200, response.text
        assert response.json()["entity"]["uid"] == uid

    @pytest.mark.parametrize(("domain", "uid"), sorted(CURRICULUM_ANCHORS.items()))
    async def test_insights_answer_without_the_threshold_echo(
        self, client: httpx.AsyncClient, domain: str, uid: str
    ) -> None:
        response = await client.get(
            f"/api/{domain}/insights", params={"uid": uid, "min_confidence": "0.9"}
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert uid in payload.values()
        assert "min_confidence" not in payload

    async def test_path_insights_count_the_paths_steps(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/pathways/insights", params={"uid": LP})

        assert response.status_code == 200, response.text
        assert response.json()["total_steps"] == 1


class TestActivityRouteSet:
    @pytest.mark.parametrize("domain", ACTIVITY_DOMAINS)
    async def test_analytics_answers(self, client: httpx.AsyncClient, domain: str) -> None:
        response = await client.get(f"/api/{domain}/analytics")

        assert response.status_code == 200, response.text

    @pytest.mark.parametrize("domain", ACTIVITY_DOMAINS)
    async def test_the_composed_app_registers_all_three(self, skuel_app, domain: str) -> None:
        paths = {getattr(route, "path", None) for route in skuel_app.routes}

        assert {
            f"/api/{domain}/analytics",
            f"/api/{domain}/context",
            f"/api/{domain}/insights",
        } <= paths

    @pytest.mark.parametrize("domain", ACTIVITY_DOMAINS)
    async def test_context_answers_for_an_owned_entity(
        self, client: httpx.AsyncClient, domain: str
    ) -> None:
        uid = ACTIVITY_ANCHORS[domain][2]

        response = await client.get(f"/api/{domain}/context", params={"uid": uid})

        assert response.status_code == 200, response.text
        assert response.json()["entity"]["uid"] == uid

    @pytest.mark.parametrize("domain", ACTIVITY_DOMAINS)
    async def test_insights_answer_for_an_owned_entity(
        self, client: httpx.AsyncClient, domain: str
    ) -> None:
        uid = ACTIVITY_ANCHORS[domain][2]

        response = await client.get(f"/api/{domain}/insights", params={"uid": uid})

        assert response.status_code == 200, response.text
