"""An insight's native stamps survive the read, end to end (testcontainer Neo4j).

The insight writer stores ``created_at`` through ``datetime($created_at)`` — a native —
so every read hands ``PersistedInsight.from_dict`` a neo4j ``DateTime``, which it
turns into a Python ``datetime`` before ``priority_score`` measures an age against
now. Nothing is stubbed between the writer and the route here: the real
``InsightStore`` writes, and the real ``GET /api/insights/active`` handler reads it
back and must answer 200.

``expires_at`` is a native too, stored through ``datetime($expires_at)``, so the
``datetime(i.expires_at)`` in every active-insight read parses it and the TTL is
honoured. The history read decodes the JSON fields as its three siblings do, so the
page renders an insight's recommended actions.

Each test first reads the raw property back and asserts its type, so it pins its
own premise.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from fasthtml.common import to_xml

from adapters.inbound.insights_api import create_insights_api_routes
from adapters.persistence.neo4j.insight_backend import InsightBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.insight.persisted_insight import InsightImpact, InsightType, PersistedInsight
from core.services.insight.insight_store import InsightStore
from ui.insights.insight_card import InsightCard

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

USER = "user_insight_native"
ACTIVE_PATH = "/api/insights/active"

Handler = Callable[..., Awaitable[Any]]


def _insight(uid: str, **fields: Any) -> PersistedInsight:
    return PersistedInsight(
        uid=uid,
        user_uid=USER,
        insight_type=InsightType.DIFFICULTY_PATTERN,
        domain="habits",
        title="Habit difficulty detected",
        description="Missed five of the last fourteen days.",
        confidence=0.85,
        impact=InsightImpact.HIGH,
        entity_uid="habit.utc_native",
        recommended_actions=[{"action": "Reduce frequency", "rationale": "Build momentum first"}],
        **fields,
    )


def _route_handlers(store: InsightStore) -> dict[str, Handler]:
    """Register the real insight routes on a recorder; path → handler."""
    registered: dict[str, Handler] = {}

    def rt(path: str, methods: list[str] | None = None) -> Callable[[Handler], Handler]:
        def decorator(fn: Handler) -> Handler:
            registered[path] = fn
            return fn

        return decorator

    create_insights_api_routes(SimpleNamespace(), rt, store)
    return registered


def _request() -> SimpleNamespace:
    """Session-backed request stub for ``require_authenticated_user``."""
    return SimpleNamespace(
        method="GET",
        session={"user_uid": USER},
        url=SimpleNamespace(path=ACTIVE_PATH),
        query_params={},
        headers={},
        cookies={},
    )


async def _value_types(neo4j_driver: Any, prop: str) -> dict[str, str]:
    async with neo4j_driver.session() as session:
        result = await session.run(
            f"MATCH (i:Insight {{user_uid: $user}}) RETURN i.uid AS uid, valueType(i.{prop}) AS t",
            user=USER,
        )
        return {record["uid"]: record["t"] async for record in result}


@pytest_asyncio.fixture
async def store(neo4j_driver, clean_neo4j) -> InsightStore:
    return InsightStore(InsightBackend(Neo4jQueryExecutor(neo4j_driver)))


class TestActiveRouteOverNativeStamps:
    async def test_the_route_serves_an_insight_whose_created_at_is_native(
        self, store, neo4j_driver
    ) -> None:
        created = await store.create_insight(_insight("insight.utc.native_created"))
        assert created.is_ok, created
        # The premise: the real writer stores a native, not a string.
        types = await _value_types(neo4j_driver, "created_at")
        assert types["insight.utc.native_created"].startswith("ZONED DATETIME"), types

        response = await _route_handlers(store)[ACTIVE_PATH](_request())

        assert response.status_code == 200, response.body
        payload = json.loads(response.body)
        assert payload["count"] == 1
        served = payload["insights"][0]
        assert served["uid"] == "insight.utc.native_created"
        assert served["is_active"] is True
        assert served["priority_score"] > 0


class TestExpiryIsANative:
    async def test_an_expiry_is_stored_as_a_native_and_honoured(self, store, neo4j_driver) -> None:
        live = PersistedInsight.with_default_expiry(
            days=1,
            uid="insight.utc.expires_tomorrow",
            user_uid=USER,
            insight_type=InsightType.STREAK_PATTERN,
            domain="habits",
            title="Streak building",
            description="Three days running.",
            confidence=0.7,
            impact=InsightImpact.MEDIUM,
            entity_uid="habit.utc_native",
        )
        lapsed = _insight("insight.utc.expired", expires_at=datetime.now() - timedelta(hours=1))
        forever = _insight("insight.utc.no_expiry")
        for insight in (live, lapsed, forever):
            created = await store.create_insight(insight)
            assert created.is_ok, created

        types = await _value_types(neo4j_driver, "expires_at")
        assert types["insight.utc.expires_tomorrow"].startswith("ZONED DATETIME"), types
        assert types["insight.utc.expired"].startswith("ZONED DATETIME"), types
        # A null expiry is no property at all — the insight never expires.
        assert types["insight.utc.no_expiry"] == "NULL", types

        active = await store.get_active_insights(USER)

        assert active.is_ok, active
        assert {i.uid for i in active.value} == {
            "insight.utc.expires_tomorrow",
            "insight.utc.no_expiry",
        }
        expiring = next(i for i in active.value if i.uid == "insight.utc.expires_tomorrow")
        assert type(expiring.expires_at) is datetime
        assert expiring.is_expired() is False


class TestHistoryRead:
    async def test_the_history_read_decodes_json_fields_and_renders(self, store) -> None:
        created = await store.create_insight(_insight("insight.utc.dismissed"))
        assert created.is_ok, created
        dismissed = await store.dismiss_insight("insight.utc.dismissed", USER, notes="later")
        assert dismissed.is_ok, dismissed

        history = await store.get_insight_history(USER, history_type="dismissed")

        assert history.is_ok, history
        [insight] = history.value
        assert insight.recommended_actions == [
            {"action": "Reduce frequency", "rationale": "Build momentum first"}
        ]
        assert type(insight.dismissed_at) is datetime
        assert "Reduce frequency" in to_xml(InsightCard(insight))
