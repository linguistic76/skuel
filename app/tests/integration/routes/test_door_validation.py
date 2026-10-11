"""A door reads its input or refuses it — never a 500, never a stored default.

Over the bootstrapped app, through the real routes:

- **A typed handler parameter is not bound by FastHTML.** FastHTML casts a handler
  parameter by calling its annotation on the raw text: an unreadable ``bool`` raised
  (500), an unreadable ``int`` / ``float`` answered a bare-text 404. Each route here
  reads the value itself through the query-param helpers, so an unreadable value is
  its default (``API_VALIDATION_PATTERNS`` § Query Params: 200).
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
# A typed handler parameter: read by the route, its default when unreadable
# =============================================================================

#: ``(caller, method, path, body kind, body)`` — the bad value, then the readable one.
_READS: list[tuple[str, str, str, str, dict[str, str]]] = [
    ("admin", "GET", "/api/admin/users?active_only=maybe&limit=lots&offset=x", "", {}),
    ("admin", "GET", "/performance/scale-test?concurrent_users=many&duration_seconds=x", "", {}),
    ("user", "POST", "/api/search/unified", "json", {"query": "x", "tags_match_all": "maybe"}),
    ("user", "POST", "/api/search/unified", "json", {"query": "x", "limit": "lots"}),
    ("user", "GET", "/search/results?query=x&limit=lots", "", {}),
    ("user", "GET", "/api/goals/list?limit=lots&offset=x", "", {}),
    ("user", "GET", "/api/search/intelligent?q=x&limit=lots", "", {}),
    ("user", "GET", "/api/insights/active?limit=lots", "", {}),
    ("user", "GET", "/api/user-entries?limit=lots&offset=x", "", {}),
    ("user", "GET", "/api/lp/{lp}/children?parent_depth=x", "", {}),
    ("user", "GET", "/api/explore/search?offset=x", "", {}),
    ("user", "GET", "/api/path-steps/prerequisites?step_uid={ps}&depth=x", "", {}),
    ("user", "GET", "/api/path-steps/curriculum/self_awareness?limit=x", "", {}),
    ("user", "GET", "/api/path-steps/curriculum-html/self_awareness?limit=x", "", {}),
    ("user", "GET", "/api/goals/analytics?period_days=x", "", {}),
    ("user", "GET", "/api/goals/context?uid={goal}&depth=x", "", {}),
    ("user", "GET", "/api/goals/insights?uid={goal}&min_confidence=x", "", {}),
    ("user", "GET", "/api/goals/{goal}/lateral/graph?depth=x", "", {}),
    ("user", "POST", "/journals/save", "form", {"summon_canon": "maybe"}),
    ("user", "POST", "/journals/follow-up", "form", {"user_reply": "hi", "summon_vault": "x"}),
    ("user", "POST", "/journals/stage2", "form", {"raw_entry": "x", "summon_canon": "x"}),
    ("user", "POST", "/journals/stage3", "form", {"raw_entry": "x", "summon_vault": "x"}),
]

#: The readable spelling of every value the bad cases send.
_READABLE = {
    "maybe": "true",
    "lots": "5",
    "many": "5",
    "x": "1",
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
    ids=[f"{method} {path.split('?')[0]} {sorted(body)}" for _, method, path, _, body in _READS],
)
async def test_an_unreadable_value_is_its_default(
    world: World, caller: str, method: str, path: str, kind: str, body: dict[str, str]
) -> None:
    response = await _send(world, caller, method, path, kind, body)
    assert response.status_code == 200, response.text[:300]

    # The control: the same door with a readable value answers the same way.
    readable = await _send(
        world,
        caller,
        method,
        _readable(path),
        kind,
        {key: _READABLE.get(value, value) for key, value in body.items()},
    )
    assert readable.status_code == 200, readable.text[:300]


@pytest.mark.parametrize(("sent", "read"), [("lots", 50), ("", 50), ("3", 3), ("0", 1), ("-5", 1)])
async def test_the_route_reads_the_value_it_was_sent(world: World, sent: str, read: int) -> None:
    """The instrument's own control: the list echoes the limit it read — the sent
    number when readable (at least 1), the default when not."""
    response = await world.client.get(f"/api/user-entries?limit={sent}")

    assert response.status_code == 200, response.text[:300]
    assert response.json()["limit"] == read


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
