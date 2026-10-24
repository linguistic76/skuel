"""The /insights charts and smart dismiss act on a learner's WHOLE active set (testcontainer Neo4j).

A learner here holds 230 active insights — more than any page the store reads —
plus one expired, one dismissed and one actioned insight that are not active.
Every insight is written by the real ``InsightStore.create_insight`` (the
``HAS_INSIGHT`` edge, ``dismissed``/``actioned`` false, a native ``expires_at``).

The charts are read through the real route handlers, so the figures pinned are
the ones a learner's browser receives. Each count is a grouped count of the
active set: impact in its fixed Critical/High/Medium/Low order, domain and type
by count descending with a tie ordered by name.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio

from adapters.inbound.insights_api import create_insights_api_routes
from adapters.persistence.neo4j.insight_backend import InsightBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.insight.persisted_insight import InsightImpact, InsightType, PersistedInsight
from core.services.insight.insight_store import InsightStore
from tests.helpers.seed_uids import seed_user_uid

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

USER = seed_user_uid("insight_whole_set")
ACTIVE_COUNT = 230
IMPACTS = [InsightImpact.CRITICAL, InsightImpact.HIGH, InsightImpact.MEDIUM, InsightImpact.LOW]
TYPES = [InsightType.DIFFICULTY_PATTERN, InsightType.LEARNING_PROGRESS, InsightType.KNOWLEDGE_GAP]
DOMAINS = ["habits", "tasks", "goals"]

Handler = Callable[..., Awaitable[Any]]


def _insight(uid: str, n: int, **fields: Any) -> PersistedInsight:
    return PersistedInsight(
        uid=uid,
        user_uid=USER,
        insight_type=TYPES[n % 3],
        domain=DOMAINS[n % 3],
        title=f"Insight {n}",
        description="Seeded for the whole-set count.",
        confidence=0.5,
        impact=IMPACTS[n % 4],
        entity_uid=None,
        **fields,
    )


# Inactive insights, each LOW impact in the habits domain with the
# difficulty-pattern type — values every chart already shows, so a count that
# ignored the active predicate would raise a pinned figure.
INACTIVE = {
    "insight.whole-set.expired": {"expires_at": datetime.now(UTC) - timedelta(days=1)},
    "insight.whole-set.dismissed": {"dismissed": True},
    "insight.whole-set.actioned": {"actioned": True},
}


@pytest_asyncio.fixture
async def store(neo4j_driver, clean_neo4j) -> InsightStore:
    async with neo4j_driver.session() as session:
        # User nodes survive `clean_neo4j`; MERGE keeps the learner single.
        await session.run("MERGE (:User {uid: $uid})", uid=USER)
    store = InsightStore(InsightBackend(Neo4jQueryExecutor(neo4j_driver)))

    seeds = [_insight(f"insight.whole-set.{n}", n) for n in range(ACTIVE_COUNT)]
    seeds += [
        PersistedInsight(
            uid=uid,
            user_uid=USER,
            insight_type=InsightType.DIFFICULTY_PATTERN,
            domain="habits",
            title=uid,
            description="Not active.",
            confidence=0.5,
            impact=InsightImpact.LOW,
            entity_uid=None,
            **fields,
        )
        for uid, fields in INACTIVE.items()
    ]
    for start in range(0, len(seeds), 25):
        created = await asyncio.gather(
            *(store.create_insight(s) for s in seeds[start : start + 25])
        )
        assert all(r.is_ok for r in created), created

    # The premise: every seeded insight hangs off the learner, and the expired
    # one's expiry is a stored native in the past.
    async with neo4j_driver.session() as session:
        record = await (
            await session.run(
                "MATCH (:User {uid: $uid})-[:HAS_INSIGHT]->(i:Insight) "
                "RETURN count(i) AS n, "
                "count(CASE WHEN i.expires_at < datetime() THEN 1 END) AS expired",
                uid=USER,
            )
        ).single()
    assert record is not None
    assert (record["n"], record["expired"]) == (ACTIVE_COUNT + len(INACTIVE), 1)
    return store


def _route_handlers(store: InsightStore) -> dict[str, Handler]:
    registered: dict[str, Handler] = {}

    def rt(path: str, methods: list[str] | None = None) -> Callable[[Handler], Handler]:
        def decorator(fn: Handler) -> Handler:
            registered[path] = fn
            return fn

        return decorator

    create_insights_api_routes(SimpleNamespace(), rt, store)
    return registered


def _request(path: str) -> SimpleNamespace:
    return SimpleNamespace(
        method="GET",
        session={"user_uid": USER},
        url=SimpleNamespace(path=path),
        query_params={},
        headers={},
        cookies={},
    )


async def _chart(store: InsightStore, path: str) -> tuple[list[str], list[int]]:
    response = await _route_handlers(store)[path](_request(path))
    assert response.status_code == 200, response.body
    data = json.loads(response.body)["data"]
    return data["labels"], data["datasets"][0]["data"]


async def _active_low_count(neo4j_driver: Any) -> int:
    async with neo4j_driver.session() as session:
        record = await (
            await session.run(
                "MATCH (:User {uid: $uid})-[:HAS_INSIGHT]->(i:Insight {impact: 'low'}) "
                "WHERE i.dismissed = false AND i.actioned = false "
                "AND (i.expires_at IS NULL OR i.expires_at > datetime()) "
                "RETURN count(i) AS n",
                uid=USER,
            )
        ).single()
    assert record is not None
    return int(record["n"])


class TestChartsCountTheWholeActiveSet:
    async def test_impact_chart(self, store) -> None:
        labels, data = await _chart(store, "/api/insights/charts/impact-distribution")

        assert labels == ["Critical", "High", "Medium", "Low"]
        assert data == [58, 58, 57, 57]

    async def test_domain_chart_orders_a_tie_by_name(self, store) -> None:
        labels, data = await _chart(store, "/api/insights/charts/domain-distribution")

        assert labels == ["Habits", "Tasks", "Goals"]
        assert data == [77, 77, 76]

    async def test_type_chart_orders_a_tie_by_name(self, store) -> None:
        labels, data = await _chart(store, "/api/insights/charts/type-distribution")

        assert labels == ["Difficulty Pattern", "Learning Progress", "Knowledge Gap"]
        assert data == [77, 77, 76]


class TestSmartDismissDismissesTheWholeMatchingSet:
    async def test_every_active_match_is_dismissed_and_nothing_else(
        self, store, neo4j_driver
    ) -> None:
        assert await _active_low_count(neo4j_driver) == 57

        result = await store.smart_dismiss(USER, "impact", "low")

        assert result.is_ok, result
        assert result.value == {
            "dismissed_count": 57,
            "filter": {"type": "impact", "value": "low"},
        }
        assert await _active_low_count(neo4j_driver) == 0
        # The other impacts are untouched, and an expired low insight is not
        # re-stamped: only the active set is matched.
        _, data = await _chart(store, "/api/insights/charts/impact-distribution")
        assert data == [58, 58, 57, 0]
        async with neo4j_driver.session() as session:
            record = await (
                await session.run(
                    "MATCH (i:Insight {uid: 'insight.whole-set.expired'}) "
                    "RETURN i.dismissed AS dismissed, i.dismissed_at AS at",
                )
            ).single()
        assert record is not None
        assert (record["dismissed"], record["at"]) == (False, None)

    async def test_type_filter_matches_the_insight_type_property(self, store) -> None:
        result = await store.smart_dismiss(USER, "type", "knowledge_gap")

        assert result.is_ok, result
        assert result.value["dismissed_count"] == 76
        labels, _ = await _chart(store, "/api/insights/charts/type-distribution")
        assert "Knowledge Gap" not in labels

    async def test_no_match_dismisses_nothing(self, store) -> None:
        result = await store.smart_dismiss(USER, "domain", "finance")

        assert result.is_ok, result
        assert result.value["dismissed_count"] == 0
        _, data = await _chart(store, "/api/insights/charts/domain-distribution")
        assert sum(data) == ACTIVE_COUNT
