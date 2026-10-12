"""The PathStep API registers no analytics-summary or graph-structure route.

``GET /api/path-steps/analytics/summary`` and ``GET /api/path-steps/graph/structure``
are not PathStep routes: corpus structure is read through the knowledge-health
gauge (``/admin/knowledge-health``), and a step's own figures through
``GET /api/path-steps/stats``.

The routes are registered through the bootstrap's own entry point
(``create_pathways_routes``) over the composed app's services, and the composed
app's route table is read too. A registered route that refuses answers through
``@boundary_handler`` — a JSON error body — so each of the two paths is held to the
router's own 404, which is not JSON.

The contract:

- neither path is in the composed app's route table, and ``/api/path-steps/stats``
  is;
- a GET on either path answers the router's 404;
- ``GET /api/path-steps/stats`` answers 200 with a real PathStep's figures.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

PS = "ps.r3retire.step"
UNROUTED_PATHS = ("/api/path-steps/analytics/summary", "/api/path-steps/graph/structure")


@pytest_asyncio.fixture(loop_scope="session")
async def seeded_step(skuel_app):
    """One PathStep, as the content-vault ingest writes the fields the stats read."""
    driver = skuel_app.state.services.neo4j_driver
    async with driver.session() as session:
        await session.run("MATCH (n {uid: $uid}) DETACH DELETE n", uid=PS)
        await session.run(
            """
            CREATE (ps:Entity:PathStep {uid: $uid})
            SET ps.title = 'R3 step', ps.entity_type = 'path_step', ps.status = 'active'
            """,
            uid=PS,
        )
    yield PS
    async with driver.session() as session:
        await session.run("MATCH (n {uid: $uid}) DETACH DELETE n", uid=PS)


@pytest_asyncio.fixture(loop_scope="session")
async def client(skuel_app, seeded_step):
    """An HTTP client over the PathStep routes as the bootstrap registers them."""
    from fasthtml.common import fast_app

    from adapters.inbound.pathways_routes import create_pathways_routes

    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="r3-unrouted-paths-key")
    create_pathways_routes(app, rt, skuel_app.state.services, None)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http


class TestUnroutedAnalyticsPaths:
    @pytest.mark.parametrize("path", UNROUTED_PATHS)
    async def test_the_composed_app_registers_no_such_path(self, skuel_app, path: str) -> None:
        paths = {getattr(route, "path", None) for route in skuel_app.routes}

        assert path not in paths
        assert "/api/path-steps/stats" in paths

    @pytest.mark.parametrize("path", UNROUTED_PATHS)
    async def test_a_get_answers_the_routers_404(
        self, client: httpx.AsyncClient, path: str
    ) -> None:
        response = await client.get(path, params={"period": "month", "metrics": "true"})

        assert response.status_code == 404, response.text
        assert "application/json" not in response.headers.get("content-type", "")


class TestStepStatsStillAnswers:
    async def test_stats_answer_for_a_real_step(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/path-steps/stats", params={"uid": PS})

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["uid"] == PS
        assert payload["title"] == "R3 step"
