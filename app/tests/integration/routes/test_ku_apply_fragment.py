"""Where you can apply this, and the free time method 8 ranks against — over a real graph.

The Ku reading page mounts ``/explore/ku/{uid}/apply`` for a signed-in reader; the
fragment builds the hub from the reader's rich context (the MEGA-QUERY over this
graph) and answers with method 3. Seeded for one user, every kind it answers with:
a goal requiring the Ku, a habit applying it, a habit supporting that goal, an
upcoming event reinforcing that habit (read through ``events_by_habit``) and a
cancelled one, an event dated today that ended at midnight, a pending choice and a made one informed by it, a principle grounded in
it, and a task applying it.

The calendar half: ``CalendarService.event_items_in_range`` reads a low-priority
event with its real duration — the week view's membership floor would hide it.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import pytest_asyncio
from starlette.responses import PlainTextResponse

from adapters.inbound.auth.session import set_current_user
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.fasthtml_types import Request
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.event.calendar_models import CalendarView
from core.models.type_hints import UserUID
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

USER = "user_kuapply_reader"
KU = "ku.kuapply.anchor"
GOAL = "goal_kuapply_requires"
HABIT_APPLIES = "habit_kuapply_applies"
HABIT_SUPPORTS = "habit_kuapply_supports"
EVENT = "event_kuapply_reinforces"
EVENT_CANCELLED = "event_kuapply_cancelled"
EVENT_OVER = "event_kuapply_over"
TASK = "task_kuapply_applies"
CHOICE_PENDING = "choice_kuapply_pending"
CHOICE_MADE = "choice_kuapply_made"
PRINCIPLE = "principle_kuapply_held"
LOW_EVENT = "event_kuapply_low"
UPCOMING = date(2099, 1, 5)
UIDS = (
    USER,
    KU,
    GOAL,
    HABIT_APPLIES,
    HABIT_SUPPORTS,
    EVENT,
    EVENT_CANCELLED,
    EVENT_OVER,
    TASK,
    CHOICE_PENDING,
    CHOICE_MADE,
    PRINCIPLE,
    LOW_EVENT,
)
_STAMP = "2000-01-01T00:00:00+00:00"


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid IN $uids OR n.user_uid = $user DETACH DELETE n",
            uids=list(UIDS),
            user=USER,
        )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def graph(skuel_app: Any) -> AsyncIterator[AsyncDriver]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    await _wipe(driver)
    async with driver.session() as session:
        await session.run(
            "MERGE (u:User {uid: $uid}) SET u.username = $uid, u.title = $uid", uid=USER
        )
        await session.run(
            """
            MERGE (k:Entity:Ku {uid: $ku})
            SET k.title = 'kuapply anchor concept', k.entity_type = 'ku', k.status = 'active',
                k.created_at = $stamp, k.updated_at = $stamp
            """,
            ku=KU,
            stamp=_STAMP,
        )
        for uid, title, label, status in (
            (GOAL, "kuapply goal", "Goal", "active"),
            (HABIT_APPLIES, "kuapply applying habit", "Habit", "active"),
            (HABIT_SUPPORTS, "kuapply supporting habit", "Habit", "active"),
            (EVENT, "kuapply reinforcing event", "Event", "scheduled"),
            (EVENT_CANCELLED, "kuapply cancelled event", "Event", "cancelled"),
            (EVENT_OVER, "kuapply ended event", "Event", "scheduled"),
            (TASK, "kuapply applying task", "Task", "active"),
            (CHOICE_PENDING, "kuapply pending choice", "Choice", "active"),
            (CHOICE_MADE, "kuapply made choice", "Choice", "completed"),
            (PRINCIPLE, "kuapply held principle", "Principle", "active"),
        ):
            await session.run(
                f"""
                MATCH (u:User {{uid: $u}})
                CREATE (n:Entity:{label} {{uid: $uid}})
                SET n.title = $title, n.entity_type = $kind, n.user_uid = $u,
                    n.status = $status, n.created_at = $stamp, n.updated_at = $stamp
                MERGE (u)-[:OWNS]->(n)
                """,
                u=USER,
                uid=uid,
                title=title,
                kind=label.lower(),
                status=status,
                stamp=_STAMP,
            )
        await session.run(
            """
            MATCH (k:Ku {uid: $ku}), (g:Goal {uid: $goal}), (ha:Habit {uid: $ha}),
                  (hs:Habit {uid: $hs}), (e:Event {uid: $event}), (cp:Choice {uid: $cp}),
                  (cm:Choice {uid: $cm}), (p:Principle {uid: $p}),
                  (ec:Event {uid: $ec}), (eo:Event {uid: $eo}), (t:Task {uid: $task})
            SET e.event_date = $upcoming, e.start_time = localtime('10:00'),
                e.end_time = localtime('11:00'), cm.decided_at = $stamp,
                ec.event_date = $upcoming, ec.start_time = localtime('10:00'),
                ec.end_time = localtime('11:00'),
                eo.event_date = $today, eo.start_time = localtime('00:00'),
                eo.end_time = localtime('00:00')
            MERGE (g)-[:REQUIRES_KNOWLEDGE]->(k)
            MERGE (ha)-[:APPLIES_KNOWLEDGE]->(k)
            MERGE (hs)-[:SUPPORTS_GOAL]->(g)
            MERGE (e)-[:REINFORCES_HABIT]->(hs)
            MERGE (ec)-[:REINFORCES_HABIT]->(hs)
            MERGE (t)-[:APPLIES_KNOWLEDGE]->(k)
            MERGE (eo)-[:APPLIES_KNOWLEDGE]->(k)
            MERGE (cp)-[:INFORMED_BY_KNOWLEDGE]->(k)
            MERGE (cm)-[:INFORMED_BY_KNOWLEDGE]->(k)
            MERGE (p)-[:GROUNDED_IN_KNOWLEDGE]->(k)
            """,
            ku=KU,
            goal=GOAL,
            ha=HABIT_APPLIES,
            hs=HABIT_SUPPORTS,
            event=EVENT,
            cp=CHOICE_PENDING,
            cm=CHOICE_MADE,
            p=PRINCIPLE,
            ec=EVENT_CANCELLED,
            eo=EVENT_OVER,
            today=today_in(current_zone()).isoformat(),
            task=TASK,
            upcoming=UPCOMING.isoformat(),
            stamp=_STAMP,
        )
    yield driver
    await _wipe(driver)


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def app(skuel_app: Any, graph: AsyncDriver) -> Any:
    """The whole route tree, wired by the bootstrap's own entry point."""
    from fasthtml.common import fast_app

    from scripts.dev.bootstrap import _wire_all_routes

    container = skuel_app.state.container
    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="kuapply-test-key")
    await _wire_all_routes(
        app, rt, container.services, container.config, container.prometheus_metrics
    )

    @rt("/sign-in/{uid}")
    def sign_in(request: Request, uid: str) -> PlainTextResponse:
        set_current_user(request, user_uid=uid)
        return PlainTextResponse("ok")

    return app


def _client(app: Any) -> httpx.AsyncClient:
    token = mint_token()
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
        timeout=120,
    )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def anonymous(app: Any) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(app) as client:
        yield client


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def reader(app: Any) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(app) as client:
        assert (await client.get(f"/sign-in/{USER}")).status_code == 200
        yield client


async def test_the_reading_page_mounts_the_section_for_a_signed_in_reader(
    reader: httpx.AsyncClient, anonymous: httpx.AsyncClient
) -> None:
    signed_in = await reader.get(f"/explore/ku/{KU}/content")
    signed_out = await anonymous.get(f"/explore/ku/{KU}/content")

    assert signed_in.status_code == 200, signed_in.text[:300]
    assert f'hx-get="/explore/ku/{KU}/apply"' in signed_in.text
    assert signed_out.status_code == 200, signed_out.text[:300]
    assert "/apply" not in signed_out.text


async def test_the_fragment_needs_a_signed_in_reader(anonymous: httpx.AsyncClient) -> None:
    assert (await anonymous.get(f"/explore/ku/{KU}/apply")).status_code == 401


async def test_every_kind_linked_to_the_ku_is_named_and_linked(
    reader: httpx.AsyncClient,
) -> None:
    fragment = await reader.get(f"/explore/ku/{KU}/apply")

    assert fragment.status_code == 200, fragment.text[:300]
    assert "Where you can apply this" in fragment.text
    for title, href in (
        ("kuapply applying task", f"/tasks/detail?uid={TASK}"),
        ("kuapply goal", f"/goals/detail?uid={GOAL}"),
        ("kuapply applying habit", f"/habits/detail?uid={HABIT_APPLIES}"),
        ("kuapply supporting habit", f"/habits/detail?uid={HABIT_SUPPORTS}"),
        ("kuapply reinforcing event", f"/events/detail?uid={EVENT}"),
        ("kuapply pending choice", f"/choices/detail?uid={CHOICE_PENDING}"),
        ("kuapply held principle", f"/principles/detail?uid={PRINCIPLE}"),
    ):
        assert title in fragment.text, title
        assert f'href="{href}"' in fragment.text, href
    # A choice already made, a cancelled event and one already over are not
    # opportunities.
    assert "kuapply made choice" not in fragment.text
    assert "kuapply cancelled event" not in fragment.text
    assert "kuapply ended event" not in fragment.text


async def test_the_ended_event_is_upcoming_by_its_date(skuel_app: Any, graph: AsyncDriver) -> None:
    """The premise of the ended event's absence: the context counts it as upcoming."""
    context = await skuel_app.state.services.user.get_rich_unified_context(UserUID(USER))

    assert context.is_ok, context
    assert EVENT_OVER in context.value.upcoming_event_uids


async def test_a_ku_nothing_links_to_says_so(reader: httpx.AsyncClient) -> None:
    fragment = await reader.get("/explore/ku/ku.kuapply.unlinked/apply")

    assert fragment.status_code == 200, fragment.text[:300]
    assert "Nothing you track is linked to this concept yet" in fragment.text


async def test_the_calendar_reads_a_low_priority_event_with_its_real_duration(
    skuel_app: Any, graph: AsyncDriver
) -> None:
    async with graph.session() as session:
        await session.run(
            """
            MATCH (u:User {uid: $u})
            CREATE (e:Entity:Event {uid: $uid})
            SET e.title = 'kuapply low event', e.entity_type = 'event', e.user_uid = $u,
                e.status = 'scheduled', e.priority = 'low', e.event_date = $day,
                e.start_time = localtime('13:00'), e.end_time = localtime('14:30'),
                e.created_at = $stamp, e.updated_at = $stamp
            MERGE (u)-[:OWNS]->(e)
            """,
            u=USER,
            uid=LOW_EVENT,
            day=UPCOMING.isoformat(),
            stamp=_STAMP,
        )
    calendar = skuel_app.state.services.calendar

    read = await calendar.event_items_in_range(UserUID(USER), UPCOMING, UPCOMING)
    week = await calendar.get_calendar_view(UserUID(USER), UPCOMING, UPCOMING, CalendarView.WEEK)

    assert read.is_ok, read
    (low,) = [item for item in read.value if item.source_uid == LOW_EVENT]
    assert low.start_time == datetime.combine(UPCOMING, time(13, 0))
    assert low.end_time == datetime.combine(UPCOMING, time(14, 30))
    # The premise: the week view's floor hides it, so the free time must not read the view.
    assert week.is_ok, week
    assert LOW_EVENT not in {item.source_uid for item in week.value.items}
