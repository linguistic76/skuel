"""A door reads its input or refuses it — never a 500, never a silent default.

Over the bootstrapped app, through the real routes:

- **One rule for a parameter a route reads** (query string, or a bound handler
  parameter). Missing or blank is its default; present but malformed — or outside
  its domain bounds (``month=13``) — is a 400; a limit, window or depth above the
  server's cap is the cap. FastHTML never casts these: each route reads the value
  itself through the ``route_helpers`` strict readers.
- **An HTML route answers a malformed parameter with a bare 400** — plain text, no
  refusal header, so HTMX leaves its target as it was.
- **A score a write stores is read or refused.** A lateral edge's ``confidence`` /
  ``strength`` / ``synergy_score`` that is not a finite number in 0.0-1.0 is a 400 and
  no edge is written.
- **The settings save refuses what the editor could not have sent** — 400, nothing
  saved — instead of storing a default or any string.
- **A JSON body is read as the client sent it.** FastHTML merges the query string into
  the JSON body it caches; a body reader that read that cache took ``?title=`` over the
  body's ``title``.

Each refusal has its positive control: the same door with a readable value succeeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.type_hints import UserUID
from core.models.user import UserPreferences
from tests.integration._activity_link_rig import (
    create,
    seed_published_learning_path,
    seed_published_path_step,
    signed_in_client,
)

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

MARK = "doorval"
USER = f"user_{MARK}_caller"
ADMIN = f"user_{MARK}_admin"
ADMIN_MARK = f"{MARK}admin"
LP = f"lp.{MARK}.path"
PS = f"ps.{MARK}.step"


@dataclass
class World:
    client: httpx.AsyncClient
    admin: httpx.AsyncClient
    driver: AsyncDriver
    uids: dict[str, str]


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
async def world(skuel_app: Any) -> AsyncIterator[World]:  # boundary: fasthtml-app
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with (
        signed_in_client(skuel_app, USER, MARK) as client,
        signed_in_client(skuel_app, ADMIN, ADMIN_MARK) as admin,
    ):
        await _set_admin(driver, ADMIN)
        await seed_published_learning_path(driver, LP, f"{MARK} path")
        await seed_published_path_step(driver, PS, f"{MARK} step")
        uids = {
            "goal": await create(client, "goals", f"{MARK} goal"),
            "other_goal": await create(client, "goals", f"{MARK} other goal"),
            "habit": await create(client, "habits", f"{MARK} habit"),
            "other_habit": await create(client, "habits", f"{MARK} other habit"),
            "lp": LP,
            "ps": PS,
        }
        yield World(client=client, admin=admin, driver=driver, uids=uids)


# =============================================================================
# A parameter a route reads: its default when missing, a 400 when malformed
# =============================================================================

#: ``(caller, method, path, body kind, body)`` — the malformed value, then the readable one.
_READS: list[tuple[str, str, str, str, dict[str, str]]] = [
    ("admin", "GET", "/api/admin/users?active_only=maybe", "", {}),
    ("admin", "GET", "/api/admin/users?limit=lots", "", {}),
    ("admin", "GET", "/api/admin/users?offset=x", "", {}),
    ("admin", "GET", "/performance/scale-test?concurrent_users=many", "", {}),
    ("admin", "GET", "/performance/scale-test?duration_seconds=x", "", {}),
    ("user", "POST", "/api/search/unified", "json", {"query": "x", "tags_match_all": "maybe"}),
    ("user", "POST", "/api/search/unified", "json", {"query": "x", "limit": "lots"}),
    ("user", "GET", "/search/results?query=x&limit=lots", "", {}),
    ("user", "GET", "/api/goals/list?limit=lots", "", {}),
    ("user", "GET", "/api/goals/list?offset=x", "", {}),
    ("user", "GET", "/api/search/intelligent?q=x&limit=lots", "", {}),
    ("user", "GET", "/api/insights/active?limit=lots", "", {}),
    ("user", "GET", "/api/user-entries?limit=lots", "", {}),
    ("user", "GET", "/api/user-entries?offset=x", "", {}),
    ("user", "GET", "/api/lp/{lp}/children?parent_depth=x", "", {}),
    ("user", "GET", "/api/explore/search?offset=x", "", {}),
    ("user", "GET", "/api/path-steps/prerequisites?step_uid={ps}&depth=x", "", {}),
    ("user", "GET", "/api/path-steps/curriculum/self_awareness?limit=x", "", {}),
    ("user", "GET", "/api/path-steps/curriculum-html/self_awareness?limit=x", "", {}),
    ("user", "GET", "/api/goals/analytics?period_days=x", "", {}),
    ("user", "GET", "/api/goals/context?uid={goal}&depth=x", "", {}),
    ("user", "GET", "/api/goals/insights?uid={goal}&min_confidence=x", "", {}),
    ("user", "GET", "/api/goals/{goal}/lateral/graph?depth=x", "", {}),
    ("user", "GET", "/api/goals/stalled?max_progress=x", "", {}),
    ("user", "GET", "/api/goals/knowledge-patterns?timeframe_days=x", "", {}),
    ("user", "GET", "/api/habits/history?uid={habit}&days=x", "", {}),
    ("user", "GET", "/api/habits/completion-calendar?uid={habit}&month=x", "", {}),
    ("user", "GET", "/cal/item-details/{habit}?date=notadate", "", {}),
    ("user", "GET", "/insights/load-more?offset=x", "", {}),
    ("user", "POST", "/journals/save", "form", {"summon_canon": "maybe"}),
    ("user", "POST", "/journals/follow-up", "form", {"user_reply": "hi", "summon_vault": "x"}),
    ("user", "POST", "/journals/stage2", "form", {"raw_entry": "x", "summon_canon": "x"}),
    ("user", "POST", "/journals/stage3", "form", {"raw_entry": "x", "summon_vault": "x"}),
]

#: The readable spelling of every value the malformed cases send.
_READABLE = {
    "maybe": "true",
    "lots": "5",
    "many": "5",
    "x": "1",
    "notadate": "2026-01-05",
}


def _readable(text: str) -> str:
    for bad, good in _READABLE.items():
        text = text.replace(f"={bad}", f"={good}")
    return text


async def _send(
    world: World, caller: str, method: str, path: str, kind: str, body: dict[str, str]
) -> httpx.Response:
    http = world.admin if caller == "admin" else world.client
    url = path.format(**world.uids)
    if kind == "json":
        return await http.request(method, url, json=body)
    if kind == "form":
        return await http.request(method, url, data=body)
    return await http.request(method, url)


@pytest.mark.parametrize(
    ("caller", "method", "path", "kind", "body"),
    _READS,
    ids=[f"{method} {path} {sorted(body)}" for _, method, path, _, body in _READS],
)
async def test_a_malformed_value_is_refused(
    world: World, caller: str, method: str, path: str, kind: str, body: dict[str, str]
) -> None:
    response = await _send(world, caller, method, path, kind, body)
    assert response.status_code == 400, response.text[:300]

    # The control: the same door with a readable value answers.
    readable = await _send(
        world,
        caller,
        method,
        _readable(path),
        kind,
        {key: _READABLE.get(value, value) for key, value in body.items()},
    )
    assert readable.status_code == 200, readable.text[:300]


@pytest.mark.parametrize(
    ("query", "read"),
    [("", 50), ("limit=", 50), ("limit=%20", 50), ("limit=3", 3), ("limit=1", 1)],
)
async def test_a_missing_or_blank_value_is_its_default(world: World, query: str, read: int) -> None:
    """The list echoes the limit it read: the default when missing or blank, the
    number sent when it reads."""
    response = await world.client.get(f"/api/user-entries?{query}")

    assert response.status_code == 200, response.text[:300]
    assert response.json()["limit"] == read


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ("/api/user-entries?limit=0", "limit"),
        ("/api/user-entries?limit=-5", "limit"),
        ("/api/user-entries?offset=-1", "offset"),
        ("/api/goals/list?limit=0", "limit"),
        ("/api/habits/completion-calendar?uid={habit}&month=13", "month"),
        ("/api/habits/completion-calendar?uid={habit}&month=0", "month"),
        ("/api/goals/insights?uid={goal}&min_confidence=1.5", "min_confidence"),
        ("/api/goals/stalled?max_progress=nan", "max_progress"),
    ],
)
async def test_a_value_outside_its_bounds_is_refused(world: World, path: str, field: str) -> None:
    """A domain bound is an input rule: a month 13 names no month, a limit of 0 asks
    for nothing — a 400 naming the field, not the nearest bound."""
    response = await world.client.get(path.format(**world.uids))

    assert response.status_code == 400, response.text[:300]
    assert field in response.text


@pytest.mark.parametrize(
    ("path", "key", "read"),
    [
        ("/api/goals/list?limit=10000", "limit", 500),
        ("/api/goals/list?limit=500", "limit", 500),
        ("/api/goals/knowledge-patterns?timeframe_days=1000", "timeframe_days", 365),
        ("/api/goals/knowledge-patterns?timeframe_days=7", "timeframe_days", 7),
    ],
)
async def test_a_value_above_its_cap_is_the_cap(
    world: World, path: str, key: str, read: int
) -> None:
    """A cap is server policy, not an input error: the route answers, with the cap."""
    response = await world.client.get(path)

    assert response.status_code == 200, response.text[:300]
    assert response.json()[key] == read


async def test_a_fragment_route_answers_a_bare_400(world: World) -> None:
    """An HTMX fragment route's refusal is plain text with no refusal header, so the
    client's swap listener leaves the tree as it was; the readable value renders rows."""
    url = f"/api/lp/{world.uids['lp']}/children"

    refused = await world.client.get(f"{url}?parent_depth=deep", headers={"HX-Request": "true"})

    assert refused.status_code == 400
    assert refused.headers["content-type"].startswith("text/plain")
    assert "X-SKUEL-Refusal" not in refused.headers
    assert "parent_depth" in refused.text

    rendered = await world.client.get(f"{url}?parent_depth=0", headers={"HX-Request": "true"})
    assert rendered.status_code == 200, rendered.text[:300]
    assert rendered.headers["content-type"].startswith("text/html")


# =============================================================================
# A score a lateral edge stores: read or refused
# =============================================================================


async def _edge_scores(
    driver: AsyncDriver, source: str, target: str
) -> list[dict[str, Any]]:  # boundary: neo4j rows
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH ({uid: $source})-[r]->({uid: $target})
            RETURN type(r) AS type, r.confidence AS confidence, r.strength AS strength,
                   r.synergy_score AS synergy_score
            """,
            source=source,
            target=target,
        )
        return [dict(row) async for row in result]


async def _clear_edges(driver: AsyncDriver, source: str, target: str) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH ({uid: $source})-[r]-({uid: $target}) DELETE r", source=source, target=target
        )


#: ``(source, target, segment, fields, the score field under test)``
_SCORED_WRITES: list[tuple[str, str, str, dict[str, str], str]] = [
    ("goal", "other_goal", "goals/{goal}/lateral/blocks", {"reason": "r"}, "confidence"),
    ("goal", "other_goal", "goals/{goal}/lateral/prerequisites", {}, "strength"),
    ("goal", "other_goal", "goals/{goal}/lateral/prerequisites", {}, "confidence"),
    (
        "goal",
        "other_goal",
        "goals/{goal}/lateral/alternatives",
        {"comparison_criteria": "c"},
        "confidence",
    ),
    (
        "goal",
        "other_goal",
        "goals/{goal}/lateral/complementary",
        {"synergy_description": "s"},
        "synergy_score",
    ),
    ("habit", "other_habit", "habits/{habit}/lateral/stacks", {}, "strength"),
]


@pytest.mark.parametrize(
    ("source", "target", "segment", "fields", "score"),
    _SCORED_WRITES,
    ids=[f"{segment.split('/')[-1]}:{score}" for _, _, segment, _, score in _SCORED_WRITES],
)
@pytest.mark.parametrize("bad", ["high", "2", "-0.1", "nan", "inf"])
async def test_a_score_that_is_not_a_number_in_range_is_refused(
    world: World,
    source: str,
    target: str,
    segment: str,
    fields: dict[str, str],
    score: str,
    bad: str,
) -> None:
    source_uid, target_uid = world.uids[source], world.uids[target]
    await _clear_edges(world.driver, source_uid, target_uid)
    url = "/api/" + segment.format(**world.uids)

    refused = await world.client.post(url, json={"target_uid": target_uid, **fields, score: bad})

    assert refused.status_code == 400, refused.text[:300]
    assert score in refused.text
    assert await _edge_scores(world.driver, source_uid, target_uid) == []

    # The control: a readable score is written as sent.
    written = await world.client.post(url, json={"target_uid": target_uid, **fields, score: 0.25})
    assert written.status_code == 201, written.text[:300]
    rows = await _edge_scores(world.driver, source_uid, target_uid)
    assert [row[score] for row in rows] == [0.25]
    await _clear_edges(world.driver, source_uid, target_uid)


async def test_a_score_from_a_form_post_is_read(world: World) -> None:
    """A form post carries the score as text; the readable text is the number."""
    source_uid, target_uid = world.uids["goal"], world.uids["other_goal"]
    await _clear_edges(world.driver, source_uid, target_uid)
    url = f"/api/goals/{source_uid}/lateral/blocks"

    written = await world.client.post(
        url, data={"target_uid": target_uid, "reason": "r", "confidence": "0.75"}
    )

    assert written.status_code == 201, written.text[:300]
    assert [
        row["confidence"] for row in await _edge_scores(world.driver, source_uid, target_uid)
    ] == [0.75]
    await _clear_edges(world.driver, source_uid, target_uid)


# =============================================================================
# The settings save: read every field or refuse
# =============================================================================

_SETTINGS: dict[str, str] = {
    "learning_level": "advanced",
    "preferred_time_of_day": "evening",
    "available_minutes_daily": "45",
    "reminder_minutes_before": "10",
    "daily_summary_time": "08:30",
    "theme": "dark",
    "language": "fr",
    "timezone": "Asia/Bangkok",
    "weekly_task_goal": "12",
    "daily_habit_goal": "4",
    "monthly_learning_hours": "30",
    "modality_reading": "on",
}


async def _preferences(skuel_app: Any) -> UserPreferences:  # boundary: fasthtml-app
    user = await skuel_app.state.services.user.get_user(UserUID(USER))
    assert user.is_ok, user.error
    return user.value.preferences


async def test_the_settings_form_is_saved_as_posted(world: World, skuel_app) -> None:
    response = await world.client.post("/settings/save", data=_SETTINGS)

    assert response.status_code == 200, response.text[:300]
    prefs = await _preferences(skuel_app)
    assert prefs.learning_level == "advanced"
    assert prefs.preferred_time_of_day == "evening"
    assert prefs.available_minutes_daily == 45
    assert prefs.theme == "dark"
    assert prefs.language == "fr"
    assert prefs.timezone == "Asia/Bangkok"
    assert prefs.weekly_task_goal == 12
    assert prefs.preferred_modalities == ["reading"]
    assert prefs.enable_reminders is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("available_minutes_daily", "sixty"),
        ("reminder_minutes_before", "99999"),
        ("weekly_task_goal", ""),
        ("daily_habit_goal", "-1"),
        ("monthly_learning_hours", "lots"),
        ("learning_level", "wizard"),
        ("preferred_time_of_day", "teatime"),
        ("theme", "');alert(1);//"),
        ("language", "klingon"),
        ("daily_summary_time", "8 o'clock"),
        ("timezone", "Mars/Olympus"),
    ],
)
async def test_a_settings_value_the_editor_could_not_send_is_refused(
    world: World,
    skuel_app,
    field: str,
    value: str,
) -> None:
    saved = await world.client.post("/settings/save", data=_SETTINGS)
    assert saved.status_code == 200, saved.text[:300]
    before = await _preferences(skuel_app)

    refused = await world.client.post("/settings/save", data={**_SETTINGS, field: value})

    assert refused.status_code == 400, refused.text[:300]
    assert await _preferences(skuel_app) == before, "a refused save wrote something"


# =============================================================================
# A JSON body: the body, never the query string
# =============================================================================


async def test_a_query_parameter_does_not_replace_a_body_field(world: World) -> None:
    response = await world.client.post(
        "/api/tasks/create?title=from-the-query", json={"title": f"{MARK} from the body"}
    )

    assert response.status_code == 201, response.text[:300]
    assert response.json()["title"] == f"{MARK} from the body"
