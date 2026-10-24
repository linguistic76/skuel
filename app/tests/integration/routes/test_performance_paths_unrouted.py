"""No ``/performance/*`` path is routed; the admin surface beside it answers.

Live performance is ``/metrics`` (Prometheus) and ``/health/ready``. An admin who asks
for ``/performance/metrics``, ``/cache-stats``, ``/optimize`` or ``/scale-test`` gets a
404, while another admin route on the same client answers 200 — the control that
proves the 404s come from unrouted paths, not from a client that cannot reach the app.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import signed_in_client

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

MARK = "perfgone"
ADMIN = seed_user_uid(f"{MARK}_admin")

PERFORMANCE_PATHS = [
    ("GET", "/performance/metrics"),
    ("GET", "/performance/cache-stats"),
    ("POST", "/performance/optimize"),
    ("GET", "/performance/scale-test"),
]


async def _set_admin(driver: AsyncDriver, uid: str) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (u:User {uid: $uid})
            SET u.username = $uid, u.display_name = $uid, u.email = $uid + '@example.com',
                u.role = 'admin', u.created_at = datetime(), u.updated_at = datetime()
            """,
            uid=uid,
        )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def admin(skuel_app: Any) -> AsyncIterator[httpx.AsyncClient]:  # boundary: fasthtml-app
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with signed_in_client(skuel_app, ADMIN, MARK) as client:
        await _set_admin(driver, ADMIN)
        yield client


@pytest.mark.parametrize(
    ("method", "path"), PERFORMANCE_PATHS, ids=[path for _, path in PERFORMANCE_PATHS]
)
async def test_a_performance_path_answers_404(
    admin: httpx.AsyncClient, method: str, path: str
) -> None:
    response = await admin.request(method, path)
    assert response.status_code == 404, (method, path, response.status_code)


async def test_another_admin_route_answers(admin: httpx.AsyncClient) -> None:
    response = await admin.get("/api/admin/users")
    assert response.status_code == 200, response.text
