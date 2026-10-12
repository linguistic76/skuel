"""The intelligence payloads answer the shapes their services declare, over the bootstrapped app.

Each Activity domain's ``get_performance_analytics`` (``GET /api/{domain}/analytics``) and
the Ku's ``get_domain_insights`` (``GET /api/ku/insights``) name their payload as a TypedDict
family in ``core/ports/query_types.py``. These tests hold the body a client receives to it,
nested summaries included.

Tasks' analytics also suggests a duration buffer from the user's learned duration ratio
(ADR-048) once enough completions back it. The ratio is written by the task-completion
handler's own writer (``update_user_learning_state``) onto the User node.

Entities are created at the domains' real create doors (``_activity_link_rig.py``); the Ku is
seeded as the content vault writes shared content.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.constants import LearningLoop
from core.ports.query_types import (
    ChoiceAnalyticsSummary,
    ChoicePerformanceAnalytics,
    EventAnalyticsSummary,
    EventPerformanceAnalytics,
    GoalAnalyticsSummary,
    GoalPerformanceAnalytics,
    HabitAnalyticsSummary,
    HabitLearnedInsights,
    HabitPerformanceAnalytics,
    KuDomainInsights,
    KuUsageSummary,
    PrincipleAnalyticsSummary,
    PrinciplePerformanceAnalytics,
    TaskAnalyticsMetadata,
    TaskLearningState,
    TaskOptimizationOpportunity,
    TaskPerformanceAnalytics,
    TaskPerformanceMetrics,
    TaskPerformanceTrends,
)
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone
from tests.integration._activity_link_rig import create, signed_in_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzintpay"
USER = f"user_{MARK}"
FEW_MARK = "zzzintfew"
FEW_USER = f"user_{FEW_MARK}"
KU = f"ku.{MARK}.atom"

LONG_RATIO = 1.5  # tasks take half again as long as estimated


def _keys(payload: Any) -> set[str]:  # boundary: any TypedDict class
    """Every key a TypedDict class declares."""
    return set(payload.__required_keys__ | payload.__optional_keys__)


async def _learned(skuel_app: Any, user_uid: str, count: int) -> None:  # boundary: fasthtml-app
    """The learning state as the task-completion handler writes it."""
    backend = skuel_app.state.services.tasks.backend
    written = await backend.update_user_learning_state(
        user_uid,
        {
            "task_duration_ratio": LONG_RATIO,
            "task_completion_count": count,
            "task_duration_updated_at": "2026-10-01T09:00:00",
        },
    )
    assert written.is_ok, written


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def client(skuel_app: Any) -> AsyncIterator[httpx.AsyncClient]:  # boundary: fasthtml-app
    driver = skuel_app.state.services.neo4j_driver
    async with signed_in_client(skuel_app, USER, MARK) as http:
        for segment in ("tasks", "goals", "habits", "choices", "principles"):
            await create(http, segment, f"{MARK} {segment}")
        await create(
            http,
            "events",
            f"{MARK} events",
            event_date=today_in(current_zone()).isoformat(),
            start_time="09:00",
            end_time="10:00",
        )
        await _learned(skuel_app, USER, LearningLoop.MIN_SAMPLES_TASK_DURATION + 1)
        async with driver.session() as session:
            await session.run(
                """
                MERGE (k:Entity:Ku {uid: $uid})
                SET k.title = 'Payload atom', k.entity_type = 'ku', k.status = 'active',
                    k.publication_state = 'published', k.aliases = ['atom']
                """,
                uid=KU,
            )
        yield http


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def few_client(skuel_app: Any) -> AsyncIterator[httpx.AsyncClient]:  # boundary: fasthtml-app
    async with signed_in_client(skuel_app, FEW_USER, FEW_MARK) as http:
        await create(http, "tasks", f"{FEW_MARK} task")
        await _learned(skuel_app, FEW_USER, LearningLoop.MIN_SAMPLES_TASK_DURATION - 1)
        yield http


async def _analytics(client: httpx.AsyncClient, domain: str) -> dict[str, Any]:  # boundary: JSON
    response = await client.get(f"/api/{domain}/analytics")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()  # boundary: JSON
    return body


async def test_task_analytics_answer_their_family(client: httpx.AsyncClient) -> None:
    body = await _analytics(client, "tasks")

    assert set(body) == _keys(TaskPerformanceAnalytics)
    assert set(body["metrics"]) == _keys(TaskPerformanceMetrics)
    assert set(body["trends"]) == _keys(TaskPerformanceTrends)
    assert set(body["learning_state"]) == _keys(TaskLearningState)
    assert set(body["metadata"]) == _keys(TaskAnalyticsMetadata)
    for opportunity in body["optimization_opportunities"]:
        assert set(opportunity) <= _keys(TaskOptimizationOpportunity)


async def test_a_learned_long_ratio_suggests_a_buffer(client: httpx.AsyncClient) -> None:
    body = await _analytics(client, "tasks")

    assert body["learning_state"]["learned_duration_ratio"] == LONG_RATIO
    assert body["learning_state"]["has_sufficient_learning_data"] is True
    duration = [o for o in body["optimization_opportunities"] if o["area"] == "duration_estimation"]
    assert len(duration) == 1, body["optimization_opportunities"]
    assert duration[0]["learned_ratio"] == LONG_RATIO


async def test_a_ratio_on_too_few_completions_suggests_nothing(
    few_client: httpx.AsyncClient,
) -> None:
    body = await _analytics(few_client, "tasks")

    assert body["learning_state"]["learned_duration_ratio"] == LONG_RATIO
    assert body["learning_state"]["has_sufficient_learning_data"] is False
    assert "duration_estimation" not in {o["area"] for o in body["optimization_opportunities"]}


@pytest.mark.parametrize(
    ("domain", "payload", "summary"),
    [
        ("goals", GoalPerformanceAnalytics, GoalAnalyticsSummary),
        ("habits", HabitPerformanceAnalytics, HabitAnalyticsSummary),
        ("events", EventPerformanceAnalytics, EventAnalyticsSummary),
        ("choices", ChoicePerformanceAnalytics, ChoiceAnalyticsSummary),
        ("principles", PrinciplePerformanceAnalytics, PrincipleAnalyticsSummary),
    ],
)
async def test_activity_analytics_answer_their_family(
    client: httpx.AsyncClient,
    domain: str,
    payload: Any,  # boundary: a TypedDict class
    summary: Any,  # boundary: a TypedDict class
) -> None:
    body = await _analytics(client, domain)

    assert set(body) == _keys(payload)
    assert set(body["analytics"]) == _keys(summary)
    assert body["user_uid"] == USER
    if domain == "habits":
        assert set(body["learned_insights"]) == _keys(HabitLearnedInsights)


async def test_ku_insights_answer_their_family(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/ku/insights", params={"uid": KU})

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == _keys(KuDomainInsights)
    assert set(body["usage"]) == _keys(KuUsageSummary)
    assert body["alias_count"] == 1
    assert body["organization_depth"] == 0
