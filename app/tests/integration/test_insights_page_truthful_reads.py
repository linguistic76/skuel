"""The insights page, its load-more and its JSON reads tell the truth about the whole
active set (testcontainer Neo4j).

Thirty active insights — more than three pages — are seeded through the real
``InsightStore.create_insight``, beside one expired, one dismissed and one actioned
insight of the same learner and one active insight of another learner. The real
route handlers then read them back: every filter selects from the whole active set,
not from its first page; load-more returns exactly the next ten matches; a filter
value outside its vocabulary is a 400; ``GET /api/insights/active`` reports the
whole matching total; and the critical / high figures count active insights only.

The expected answers are derived from the seed in Python, by the order the read
promises: impact (critical first), then confidence, then newest first, then uid.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from urllib.parse import parse_qsl, urlsplit

import pytest
import pytest_asyncio
from fasthtml.common import to_xml
from starlette.responses import Response

from adapters.inbound.insights_api import create_insights_api_routes
from adapters.inbound.insights_ui import create_insights_ui_routes
from adapters.persistence.neo4j.insight_backend import InsightBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.constants import QueryLimit
from core.models.insight.persisted_insight import InsightImpact, InsightType, PersistedInsight
from core.services.insight.insight_store import InsightStore

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

USER = "user_insight_truthful"
OTHER = "user_insight_truthful_other"
PAGE = 10

Handler = Callable[..., Awaitable[Any]]

_IMPACTS = [InsightImpact.CRITICAL, InsightImpact.HIGH, InsightImpact.MEDIUM, InsightImpact.LOW]
_DOMAINS = ["habits", "tasks", "goals", "user_entry", "choices"]
_BASE = datetime(2026, 10, 1, 12, 0, 0)


@dataclass(frozen=True)
class _Seed:
    uid: str
    impact: InsightImpact
    insight_type: InsightType
    domain: str
    title: str
    description: str
    confidence: float
    created_at: datetime


def _seed(n: int) -> _Seed:
    """The n-th active insight: impact, type, domain and confidence rotate, so every
    filter selects a spread that the first page by impact does not contain."""
    return _Seed(
        uid=f"insight.truthful.{n:02d}",
        impact=_IMPACTS[n % 4],
        insight_type=InsightType.STREAK_PATTERN if n % 3 == 0 else InsightType.DIFFICULTY_PATTERN,
        domain=_DOMAINS[n % 5],
        title=f"Daily Meditation {n:02d}" if n % 6 == 0 else f"Insight {n:02d}",
        description="Sat with the MEDITATION cushion." if n == 13 else "A pattern in your week.",
        confidence=round(0.5 + (n % 3) * 0.1, 2),
        # n, n+12 and n+24 tie on impact, confidence and age: only the uid orders them.
        created_at=_BASE - timedelta(minutes=n % 12),
    )


ACTIVE = [_seed(n) for n in range(30)]


def _rank(seed: _Seed) -> tuple[int, float, float, str]:
    return (
        -seed.impact.get_priority_score(),
        -seed.confidence,
        -seed.created_at.timestamp(),
        seed.uid,
    )


def _ordered(seeds: list[_Seed]) -> list[str]:
    """The uids in the order the read promises."""
    return [s.uid for s in sorted(seeds, key=_rank)]


def _matching(**criteria: Any) -> list[str]:
    def keep(seed: _Seed) -> bool:
        if "impact" in criteria and seed.impact != criteria["impact"]:
            return False
        if "insight_type" in criteria and seed.insight_type != criteria["insight_type"]:
            return False
        if "domain" in criteria and seed.domain != criteria["domain"]:
            return False
        if "search" in criteria:
            needle = criteria["search"].lower()
            return needle in seed.title.lower() or needle in seed.description.lower()
        return True

    return _ordered([s for s in ACTIVE if keep(s)])


def _persisted(seed: _Seed, user_uid: str = USER, **fields: Any) -> PersistedInsight:
    return PersistedInsight(
        uid=seed.uid,
        user_uid=user_uid,
        insight_type=seed.insight_type,
        domain=seed.domain,
        title=seed.title,
        description=seed.description,
        confidence=seed.confidence,
        impact=seed.impact,
        entity_uid=f"habit.truthful_{seed.uid[-2:]}",
        created_at=seed.created_at,
        **fields,
    )


def _inactive(name: str) -> _Seed:
    """A critical, high-confidence insight that matches every filter — it would top
    every page if the active rule let it through."""
    return _Seed(
        uid=f"insight.truthful.{name}",
        impact=InsightImpact.CRITICAL,
        insight_type=InsightType.DIFFICULTY_PATTERN,
        domain="habits",
        title=f"Daily Meditation {name}",
        description="A pattern in your week.",
        confidence=0.99,
        created_at=_BASE,
    )


@pytest_asyncio.fixture
async def store(neo4j_driver, clean_neo4j) -> InsightStore:
    async with neo4j_driver.session() as session:
        # MERGE: clean_neo4j keeps User nodes, and a second learner node would fan
        # every HAS_INSIGHT edge out twice.
        await session.run("MERGE (:User {uid: $a}) MERGE (:User {uid: $b})", a=USER, b=OTHER)
    store = InsightStore(InsightBackend(Neo4jQueryExecutor(neo4j_driver)))

    # Written last-first, so a read that leaves ties to storage order is not in uid order.
    insights = [_persisted(seed) for seed in reversed(ACTIVE)]
    insights.append(
        _persisted(_inactive("expired"), expires_at=datetime.now() - timedelta(hours=1))
    )
    insights.append(_persisted(_inactive("dismissed")))
    insights.append(_persisted(_inactive("actioned")))
    insights.append(_persisted(_inactive("foreign"), user_uid=OTHER))
    for insight in insights:
        created = await store.create_insight(insight)
        assert created.is_ok, created

    dismissed = await store.dismiss_insight("insight.truthful.dismissed", USER, notes="")
    assert dismissed.is_ok, dismissed
    actioned = await store.mark_actioned("insight.truthful.actioned", USER, notes="")
    assert actioned.is_ok, actioned
    return store


def _handlers(store: InsightStore, monkeypatch: pytest.MonkeyPatch) -> dict[str, Handler]:
    """Register the real insight UI + API routes on a recorder; path → handler."""
    registered: dict[str, Handler] = {}

    def rt(path: str, methods: list[str] | None = None) -> Callable[[Handler], Handler]:
        def decorator(fn: Handler) -> Handler:
            registered[path] = fn
            return fn

        return decorator

    def _as_user(_request: Any) -> str:
        return USER

    def _identity_page(content: Any, **_kwargs: Any) -> Any:
        return content

    monkeypatch.setattr("adapters.inbound.insights_ui.require_authenticated_user", _as_user)
    monkeypatch.setattr("adapters.inbound.insights_api.require_authenticated_user", _as_user)
    monkeypatch.setattr("adapters.inbound.insights_ui.BasePage", _identity_page)

    create_insights_api_routes(SimpleNamespace(), rt, store)
    create_insights_ui_routes(
        None,
        rt,
        store,
        user_service=MagicMock(),
        context_intelligence=MagicMock(),
        ku_service=MagicMock(),
    )
    return registered


def _request(path: str, **query: str) -> SimpleNamespace:
    return SimpleNamespace(
        method="GET",
        session={"user_uid": USER},
        url=SimpleNamespace(path=path),
        query_params=query,
        headers={},
        cookies={},
    )


_CHECKBOX = re.compile(r'<input[^>]*name="insight-checkbox"[^>]*>')
_VALUE = re.compile(r'value="([^"]*)"')
_TRIGGER = re.compile(r'<div[^>]*id="load-more-trigger"[^>]*>')
_HX_GET = re.compile(r'hx-get="([^"]*)"')


def _listed(markup: str) -> list[str]:
    """The insight uids a rendered page or fragment lists, in order."""
    uids = []
    for tag in _CHECKBOX.findall(markup):
        value = _VALUE.search(tag)
        assert value is not None, tag
        uids.append(html.unescape(value.group(1)))
    return uids


def _next_query(markup: str) -> dict[str, str] | None:
    """The query the load-more trigger will send, or None when the list has ended."""
    trigger = _TRIGGER.search(markup)
    if trigger is None:
        return None
    hx_get = _HX_GET.search(trigger.group(0))
    if hx_get is None:
        return None
    return dict(parse_qsl(urlsplit(html.unescape(hx_get.group(1))).query))


async def _walk(handlers: dict[str, Handler], **query: str) -> list[list[str]]:
    """The page, then every load-more the page's own trigger leads to, until the end."""
    page = await handlers["/insights"](_request("/insights", **query))
    markup = to_xml(page)
    pages = [_listed(markup)]
    next_query = _next_query(markup)
    while next_query is not None:
        assert len(pages) <= 5, "load-more never reached the end"
        fragment = to_xml(
            await handlers["/insights/load-more"](_request("/insights/load-more", **next_query))
        )
        listed = _listed(fragment)
        if not listed:
            assert "No more insights" in fragment
            break
        pages.append(listed)
        next_query = _next_query(fragment)
    return pages


def _chunks(uids: list[str]) -> list[list[str]]:
    return [uids[i : i + PAGE] for i in range(0, len(uids), PAGE)] or [[]]


class TestThePageAndLoadMore:
    @pytest.mark.parametrize(
        ("query", "criteria"),
        [
            ({}, {}),
            ({"impact": "low"}, {"impact": InsightImpact.LOW}),
            (
                {"type": "difficulty_pattern"},
                {"insight_type": InsightType.DIFFICULTY_PATTERN},
            ),
            ({"domain": "user_entry"}, {"domain": "user_entry"}),
            ({"search": "meditation"}, {"search": "meditation"}),
            (
                {"impact": "critical", "type": "difficulty_pattern", "domain": "habits"},
                {
                    "impact": InsightImpact.CRITICAL,
                    "insight_type": InsightType.DIFFICULTY_PATTERN,
                    "domain": "habits",
                },
            ),
            (
                {"type": "difficulty_pattern", "search": "Insight"},
                {"insight_type": InsightType.DIFFICULTY_PATTERN, "search": "Insight"},
            ),
        ],
    )
    async def test_every_filter_pages_through_exactly_its_matches(
        self, store, monkeypatch, query: dict[str, str], criteria: dict[str, Any]
    ) -> None:
        expected = _matching(**criteria)
        assert expected, "the seed must give every case at least one match"

        pages = await _walk(_handlers(store, monkeypatch), **query)

        assert pages == _chunks(expected)

    async def test_the_subtitle_counts_every_match_not_the_page(self, store, monkeypatch) -> None:
        handlers = _handlers(store, monkeypatch)

        unfiltered = to_xml(await handlers["/insights"](_request("/insights")))
        filtered = to_xml(
            await handlers["/insights"](_request("/insights", type="difficulty_pattern"))
        )

        assert "30 active insights" in unfiltered
        assert f"{len(_matching(insight_type=InsightType.DIFFICULTY_PATTERN))} of 30" in filtered

    @pytest.mark.parametrize(
        "query",
        [
            {"impact": "urgent"},
            {"type": "completion_streak"},
            {"domain": "knowledge"},
            {"offset": "-1"},
            {"offset": "10001"},
            # Past Neo4j's 64-bit integer: refused at the door, never sent to the driver.
            {"offset": "9223372036854775808"},
        ],
    )
    async def test_a_value_outside_its_vocabulary_is_a_400(
        self, store, monkeypatch, query: dict[str, str]
    ) -> None:
        handlers = _handlers(store, monkeypatch)
        for path in ("/insights", "/insights/load-more", "/api/insights/active"):
            response = await handlers[path](_request(path, **query))
            assert isinstance(response, Response), (path, response)
            assert response.status_code == 400, (path, response.body)

    async def test_a_blank_value_is_no_filter(self, store, monkeypatch) -> None:
        pages = await _walk(_handlers(store, monkeypatch), impact="", type="", domain="", search="")

        assert pages == _chunks(_matching())


class TestTheActiveApi:
    async def test_count_is_the_whole_matching_total_and_insights_the_page(
        self, store, monkeypatch
    ) -> None:
        handler = _handlers(store, monkeypatch)["/api/insights/active"]

        whole = json.loads((await handler(_request("/api/insights/active", limit="5"))).body)
        low = json.loads(
            (await handler(_request("/api/insights/active", impact="low", limit="5"))).body
        )

        huge = json.loads(
            (await handler(_request("/api/insights/active", limit="9223372036854775808"))).body
        )

        assert whole["count"] == 30
        assert whole["limit"] == 5
        assert huge["limit"] == QueryLimit.BULK
        assert len(huge["insights"]) == 30
        assert [i["uid"] for i in whole["insights"]] == _matching()[:5]
        expected_low = _matching(impact=InsightImpact.LOW)
        assert low["count"] == len(expected_low)
        assert [i["uid"] for i in low["insights"]] == expected_low[:5]


class TestStats:
    async def test_critical_and_high_count_active_insights_only(self, store, monkeypatch) -> None:
        handler = _handlers(store, monkeypatch)["/api/insights/stats"]

        stats = json.loads((await handler(_request("/api/insights/stats"))).body)

        assert stats["critical_insights"] == sum(s.impact is InsightImpact.CRITICAL for s in ACTIVE)
        assert stats["high_insights"] == sum(s.impact is InsightImpact.HIGH for s in ACTIVE)
        assert stats["active_insights"] == 30
        # The all-time figures still see the inactive three.
        assert stats["total_insights"] == 33

    async def test_the_stats_page_names_domains_as_all_time(self, store, monkeypatch) -> None:
        page = to_xml(
            await _handlers(store, monkeypatch)["/insights/stats"](_request("/insights/stats"))
        )

        assert "Domains you&#x27;ve had insights in" in page or (
            "Domains you've had insights in" in page
        )
