"""The presence record, its two writers, its reads, its backfill and its erasure.

``(:User)-[:PRESENT_IN {sign_ins, days, last_day}]->(:Month {key})`` says a user
signed in during a UTC month, or had a live session seen in it. These tests run
the production statements against the testcontainer graph:

- the sign-in write (``SessionBackend.create_session``) and the presence write
  (``SessionBackend.validate_session_token``);
- the grouped reads behind ``/admin/analytics`` (``AdminStatsService.get_growth``
  and ``get_retention``);
- the one-shot backfill from the sign-in audit trail;
- erasure, which takes the account's auth events and presence edges and leaves
  the shared month nodes.

Each test lives in months of its own, far in the future, so what other tests
leave on the shared graph is in none of them. The clock is moved with
``time_machine``: the writers read the Python clock for the month and the day,
and a session minted in the future is not expired to the server.
"""

from __future__ import annotations

import asyncio
import importlib
from datetime import UTC, datetime

import pytest
import pytest_asyncio
import time_machine

from adapters.persistence.neo4j.neo4j_schema_manager import Neo4jSchemaManager
from core.models.auth.auth_event import AuthEventType, create_auth_event
from core.models.auth.session import create_session
from core.services.admin_stats_service import AdminStatsService
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

backfill = importlib.import_module("scripts.migrations.backfill_presence_months_2026_11")

_BROWSER = "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/130.0"
_SCRIPT = "python-httpx/0.27.0"


def _at(stamp: str) -> time_machine.travel:
    """The Python clock held at a UTC instant."""
    return time_machine.travel(datetime.fromisoformat(stamp).replace(tzinfo=UTC), tick=False)


@pytest_asyncio.fixture(loop_scope="session")
async def presence(neo4j_driver):
    """The production backends, a user seeder, and a teardown of what the test wrote."""
    constraint = await Neo4jSchemaManager(neo4j_driver).ensure_month_key_is_unique()
    assert constraint.is_ok, f"Month key constraint: {constraint.error}"
    backends = build_production_backends(neo4j_driver)
    seeded: list[str] = []

    async def seed(name: str, *, created_at: str = "2089-01-01T00:00:00", active: bool = True):
        uid = seed_user_uid(f"presence-{name}")
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (u:User {uid: $uid})
                SET u.title = $title, u.email = $email, u.is_active = $active,
                    u.created_at = $created_at, u.role = 'registered'
                """,
                uid=uid,
                title=f"presence_{name}",
                email=f"presence_{name}@example.com",
                active=active,
                created_at=created_at,
            )
        seeded.append(uid)
        return uid

    async def wipe() -> None:
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (u:User) WHERE u.uid IN $uids
                OPTIONAL MATCH (u)-[:HAS_SESSION]->(s:Session)
                OPTIONAL MATCH (u)-[:HAD_AUTH_EVENT]->(e:AuthEvent)
                DETACH DELETE s, e, u
                """,
                uids=seeded,
            )
            await session.run("MATCH (e:AuthEvent) WHERE e.user_uid IN $uids DELETE e", uids=seeded)
            await session.run("MATCH (m:Month) WHERE m.key >= '2089' DETACH DELETE m")
            await session.run(
                "MATCH (r:MigrationRecord {name: $name}) DELETE r", name=backfill.PRESENCE_BACKFILL
            )

    await wipe()
    yield backends, seed
    await wipe()


async def _edge(neo4j_driver, user_uid: str, month: str) -> dict[str, object] | None:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (:User {uid: $uid})-[p:PRESENT_IN]->(:Month {key: $month}) "
            "RETURN properties(p) AS p",
            uid=user_uid,
            month=month,
        )
        record = await result.single()
    return dict(record["p"]) if record else None


async def _scalar(neo4j_driver, query: str, **params: object) -> int:
    async with neo4j_driver.session() as session:
        record = await (await session.run(query, **params)).single()
    assert record is not None
    return int(record[0])


async def _sign_in(backends, user_uid: str) -> str:
    """Mint a session through the sign-in statement; the raw token it validates by."""
    session = create_session(user_uid=user_uid, ip_address="test", user_agent=_BROWSER)
    created = await backends["session_backend"].create_session(session)
    assert created.is_ok, f"create_session failed: {created.error}"
    return session.session_token


# ----------------------------------------------------------------------------
# The sign-in write
# ----------------------------------------------------------------------------


async def test_sign_in_counts_the_sign_in_and_each_new_day(neo4j_driver, presence):
    backends, seed = presence
    user = await seed("counts")

    with _at("2090-03-10T09:00:00"):
        await _sign_in(backends, user)
    assert await _edge(neo4j_driver, user, "2090-03") == {
        "sign_ins": 1,
        "days": 1,
        "last_day": "2090-03-10",
    }

    with _at("2090-03-10T23:59:00"):
        await _sign_in(backends, user)
    assert await _edge(neo4j_driver, user, "2090-03") == {
        "sign_ins": 2,
        "days": 1,
        "last_day": "2090-03-10",
    }

    with _at("2090-03-11T00:01:00"):
        await _sign_in(backends, user)
    assert await _edge(neo4j_driver, user, "2090-03") == {
        "sign_ins": 3,
        "days": 2,
        "last_day": "2090-03-11",
    }


async def test_concurrent_sign_ins_in_a_fresh_month_share_one_month_node(neo4j_driver, presence):
    backends, seed = presence
    one = await seed("race-one")
    two = await seed("race-two")

    with _at("2090-05-02T12:00:00"):
        await asyncio.gather(
            _sign_in(backends, one),
            _sign_in(backends, one),
            _sign_in(backends, two),
            _sign_in(backends, two),
        )

    assert await _scalar(neo4j_driver, "MATCH (m:Month {key: '2090-05'}) RETURN count(m)") == 1
    for user in (one, two):
        edge = await _edge(neo4j_driver, user, "2090-05")
        assert edge is not None and edge["sign_ins"] == 2 and edge["days"] == 1, edge
        assert (
            await _scalar(
                neo4j_driver,
                "MATCH (:User {uid: $uid})-[p:PRESENT_IN]->(:Month {key: '2090-05'}) "
                "RETURN count(p)",
                uid=user,
            )
            == 1
        )


async def test_a_deactivated_users_sign_in_writes_nothing(neo4j_driver, presence):
    backends, seed = presence
    user = await seed("inactive", active=False)

    with _at("2090-06-01T08:00:00"):
        session = create_session(user_uid=user, ip_address="test", user_agent=_BROWSER)
        created = await backends["session_backend"].create_session(session)

    assert created.is_error
    assert await _edge(neo4j_driver, user, "2090-06") is None
    assert await _scalar(neo4j_driver, "MATCH (m:Month {key: '2090-06'}) RETURN count(m)") == 0


# ----------------------------------------------------------------------------
# The presence write
# ----------------------------------------------------------------------------


async def test_a_session_seen_in_a_new_month_marks_its_user_present_once(neo4j_driver, presence):
    backends, seed = presence
    user = await seed("seen")
    sessions = backends["session_backend"]

    with _at("2090-07-28T10:00:00"):
        token = await _sign_in(backends, user)
        # The sign-in already saw the session in its own month: nothing more to write.
        assert (await sessions.validate_session_token(token)).value is not None
    assert await _edge(neo4j_driver, user, "2090-07") == {
        "sign_ins": 1,
        "days": 1,
        "last_day": "2090-07-28",
    }

    with _at("2090-08-03T10:00:00"):
        identity = await sessions.validate_session_token(token)
    assert identity.is_ok and identity.value is not None
    assert identity.value["user_uid"] == user
    assert await _edge(neo4j_driver, user, "2090-08") == {
        "sign_ins": 0,
        "days": 1,
        "last_day": "2090-08-03",
    }

    # A later request in the same month, on a later day, writes nothing.
    with _at("2090-08-09T10:00:00"):
        assert (await sessions.validate_session_token(token)).value is not None
    assert await _edge(neo4j_driver, user, "2090-08") == {
        "sign_ins": 0,
        "days": 1,
        "last_day": "2090-08-03",
    }
    assert (
        await _scalar(
            neo4j_driver, "MATCH (:User {uid: $uid})-[p:PRESENT_IN]->() RETURN count(p)", uid=user
        )
        == 2
    )


async def test_sign_ins_and_first_requests_of_a_month_do_not_deadlock(neo4j_driver, presence):
    """Sign-ins and sessions' first requests of a month, all at once, all land.

    Each writer takes its locks in one order: the user node, the session, the
    month node, and the month node before the edge to it. Neither statement is
    retried, so a writer out of that order fails a request here with a deadlock.
    """
    backends, seed = presence
    sessions = backends["session_backend"]
    users = [await seed(f"mixed-{n}") for n in range(5)]

    for round_ in range(1, 5):
        with _at(f"2094-{round_:02d}-02T12:00:00"):
            minted = [
                create_session(user_uid=user, ip_address="test", user_agent=_BROWSER)
                for user in users
                for _ in range(3)
            ]
            created = await asyncio.gather(*(sessions.create_session(s) for s in minted))
        assert not [r.error for r in created if r.is_error]

        month = f"2095-{round_:02d}"
        with _at(f"{month}-02T12:00:00"):
            more = [
                create_session(user_uid=user, ip_address="test", user_agent=_BROWSER)
                for user in users
                for _ in range(2)
            ]
            results = await asyncio.gather(
                *(sessions.validate_session_token(s.session_token) for s in minted for _ in (1, 2)),
                *(sessions.create_session(s) for s in more),
            )
        assert not [r.error for r in results if r.is_error]
        assert all(r.value is not None for r in results)

        assert (
            await _scalar(neo4j_driver, "MATCH (m:Month {key: $k}) RETURN count(m)", k=month) == 1
        )
        edges = "MATCH (:User)-[p:PRESENT_IN]->(:Month {key: $k}) RETURN "
        assert await _scalar(neo4j_driver, edges + "count(p)", k=month) == 5
        assert await _scalar(neo4j_driver, edges + "sum(p.sign_ins)", k=month) == 10
        assert await _scalar(neo4j_driver, edges + "sum(p.days)", k=month) == 5


async def test_a_session_with_no_seen_month_marks_presence_on_its_next_request(
    neo4j_driver, presence
):
    """A session that carries no ``seen_month`` is marked on its next request."""
    backends, seed = presence
    user = await seed("legacy")

    with _at("2090-09-05T10:00:00"):
        token = await _sign_in(backends, user)
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (u:User {uid: $uid})-[:HAS_SESSION]->(s:Session) REMOVE s.seen_month "
                "WITH u MATCH (u)-[p:PRESENT_IN]->() DELETE p",
                uid=user,
            )
        assert (await backends["session_backend"].validate_session_token(token)).value is not None

    assert await _edge(neo4j_driver, user, "2090-09") == {
        "sign_ins": 0,
        "days": 1,
        "last_day": "2090-09-05",
    }


# ----------------------------------------------------------------------------
# The reads
# ----------------------------------------------------------------------------


async def test_growth_counts_accounts_by_signup_month(neo4j_driver, presence):
    backends, seed = presence
    await seed("g1", created_at="2091-01-03T10:00:00")
    await seed("g2", created_at="2091-01-30T23:59:59", active=False)
    await seed("g3", created_at="2091-03-01T00:00:00")
    service = AdminStatsService(backend=backends["cross_domain_backend"])

    rows = await backends["cross_domain_backend"].get_accounts_by_signup_month()
    assert rows.is_ok, rows.error
    by_month = {row.month: row for row in rows.value}
    assert (by_month["2091-01"].new_accounts, by_month["2091-01"].deactivated) == (2, 1)
    assert "2091-02" not in by_month
    assert (by_month["2091-03"].new_accounts, by_month["2091-03"].deactivated) == (1, 0)

    with _at("2091-03-15T12:00:00"):
        growth = await service.get_growth()
    assert growth.is_ok, growth.error
    report = growth.value
    assert len(report.months) == 12
    december, january, february, march = report.months[-4:]
    assert [line.month for line in report.months[-4:]] == [
        "2090-12",
        "2091-01",
        "2091-02",
        "2091-03",
    ]
    assert (january.new_accounts, january.change) == (2, 2)
    assert (february.new_accounts, february.change) == (0, -2)
    assert (march.new_accounts, march.change) == (1, 1)
    # The deactivated account is in its month and in every total after it.
    assert january.total - december.total == 2
    assert february.total == january.total
    assert march.total - december.total == 3
    assert report.total_accounts == march.total
    assert report.deactivated_accounts >= 1
    assert report.new_this_month == 1


async def test_retention_reads_who_came_back_the_month_after(neo4j_driver, presence):
    backends, seed = presence
    a = await seed("r1")
    b = await seed("r2")
    c = await seed("r3", active=False)
    present = {"2092-01": [a, b, c], "2092-02": [a, b], "2092-04": [a]}
    async with neo4j_driver.session() as session:
        for month, users in present.items():
            await session.run(
                """
                MERGE (m:Month {key: $month})
                WITH m UNWIND $users AS uid
                MATCH (u:User {uid: uid})
                MERGE (u)-[p:PRESENT_IN]->(m)
                SET p.sign_ins = 1, p.days = 1, p.last_day = $month + '-01'
                """,
                month=month,
                users=users,
            )
    service = AdminStatsService(backend=backends["cross_domain_backend"])

    with _at("2092-04-15T12:00:00"):
        retention = await service.get_retention()
    assert retention.is_ok, retention.error
    report = retention.value
    assert len(report.months) == 12
    january, february, march, april = report.months[-4:]

    assert (january.present, january.returned, january.next_month_in_progress) == (3, 2, False)
    assert january.rate == pytest.approx(2 / 3)
    assert (february.present, february.returned) == (2, 0)
    assert february.rate == 0.0
    # No one was present in March: a line all the same, and no rate to show.
    assert (march.present, march.returned, march.next_month_in_progress) == (0, 0, True)
    assert march.rate is None
    # The current month has no month after it yet.
    assert (april.present, april.returned) == (1, None)
    assert april.rate is None
    assert report.present_this_month == 1
    # A month before the first presence: nobody, counted as nobody.
    assert (report.months[0].present, report.months[0].returned) == (0, 0)


# ----------------------------------------------------------------------------
# Erasure
# ----------------------------------------------------------------------------


async def test_erasure_takes_auth_events_and_presence_edges_and_leaves_the_month(
    neo4j_driver, presence
):
    backends, seed = presence
    user = await seed("erased")
    other = await seed("kept")

    with _at("2090-11-11T11:00:00"):
        await _sign_in(backends, user)
        await _sign_in(backends, other)
        for uid in (user, other):
            logged = await backends["session_backend"].log_auth_event(
                create_auth_event(
                    event_type=AuthEventType.LOGIN_SUCCESS,
                    ip_address="203.0.113.7",
                    user_agent=_BROWSER,
                    user_uid=uid,
                    email=f"{uid}@example.com",
                )
            )
            assert logged.is_ok, logged.error

    erased = await backends["users_backend"].hard_delete_user(user)
    assert erased.is_ok and erased.value >= 1, erased.error

    assert (
        await _scalar(
            neo4j_driver, "MATCH (e:AuthEvent {user_uid: $uid}) RETURN count(e)", uid=user
        )
        == 0
    )
    assert (
        await _scalar(
            neo4j_driver, "MATCH (e:AuthEvent {user_uid: $uid}) RETURN count(e)", uid=other
        )
        == 1
    )
    assert await _scalar(neo4j_driver, "MATCH (m:Month {key: '2090-11'}) RETURN count(m)") == 1
    assert (
        await _scalar(
            neo4j_driver, "MATCH (:User)-[p:PRESENT_IN]->(:Month {key: '2090-11'}) RETURN count(p)"
        )
        == 1
    )
    assert await _edge(neo4j_driver, other, "2090-11") is not None


# ----------------------------------------------------------------------------
# The backfill
# ----------------------------------------------------------------------------


async def _log(backends, stamp: str, *, user_uid: str | None, agent: str) -> str:
    with _at(stamp):
        event = create_auth_event(
            event_type=AuthEventType.LOGIN_SUCCESS,
            ip_address="203.0.113.7",
            user_agent=agent,
            user_uid=user_uid,
            email="backfill@example.com",
        )
    logged = await backends["session_backend"].log_auth_event(event)
    assert logged.is_ok, logged.error
    return event.uid


async def test_backfill_writes_browser_sign_ins_of_living_users_once(neo4j_driver, presence):
    backends, seed = presence
    person = await seed("bf-person")
    held = await seed("bf-held")
    scripted = await seed("bf-scripted")

    # Two browser sign-ins on one day and one on another: 3 sign-ins, 2 days.
    await _log(backends, "2093-01-10T08:00:00", user_uid=person, agent=_BROWSER)
    await _log(backends, "2093-01-10T20:00:00", user_uid=person, agent=_BROWSER)
    await _log(backends, "2093-01-31T23:30:00", user_uid=person, agent=_BROWSER)
    # A script's sign-in is not a person being present.
    await _log(backends, "2093-02-05T08:00:00", user_uid=person, agent=_SCRIPT)
    await _log(backends, "2093-02-06T08:00:00", user_uid=scripted, agent=_SCRIPT)
    # An erased account's event: it names the user, and no edge joins them.
    orphan = await _log(backends, "2093-03-05T08:00:00", user_uid=None, agent=_BROWSER)
    # A stamp stored with an offset is read in UTC: 00:30 at +02:00 is still April 30.
    offset = await _log(backends, "2093-05-01T08:00:00", user_uid=person, agent=_BROWSER)
    # A user-month the live writers already hold is left as it is.
    await _log(backends, "2093-01-12T08:00:00", user_uid=held, agent=_BROWSER)
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (e:AuthEvent {uid: $uid}) SET e.user_uid = $user", uid=orphan, user=person
        )
        await session.run(
            "MATCH (e:AuthEvent {uid: $uid}) "
            "SET e.timestamp = datetime('2093-05-01T00:30:00+02:00')",
            uid=offset,
        )
        await session.run(
            """
            MATCH (u:User {uid: $uid})
            MERGE (m:Month {key: '2093-01'})
            MERGE (u)-[p:PRESENT_IN]->(m)
            SET p.sign_ins = 7, p.days = 4, p.last_day = '2093-01-20'
            """,
            uid=held,
        )

    mine = {person, held, scripted}
    rows = [row for row in await backfill.read_user_months(neo4j_driver) if row.user_uid in mine]
    assert {
        (row.user_uid, row.month, row.sign_ins, row.days, row.last_day, row.held) for row in rows
    } == {
        (person, "2093-01", 3, 2, "2093-01-31", False),
        (person, "2093-04", 1, 1, "2093-04-30", False),
        (held, "2093-01", 1, 1, "2093-01-12", True),
    }
    # A dry read writes nothing.
    assert await _edge(neo4j_driver, person, "2093-01") is None
    assert not await backfill.record_is_applied(neo4j_driver)

    first = await backfill.apply_backfill(neo4j_driver)
    assert not first.already_applied
    assert await backfill.record_is_applied(neo4j_driver)
    assert await _edge(neo4j_driver, person, "2093-01") == {
        "sign_ins": 3,
        "days": 2,
        "last_day": "2093-01-31",
    }
    assert await _edge(neo4j_driver, person, "2093-04") == {
        "sign_ins": 1,
        "days": 1,
        "last_day": "2093-04-30",
    }
    assert await _edge(neo4j_driver, person, "2093-02") is None
    assert await _edge(neo4j_driver, person, "2093-03") is None
    assert await _edge(neo4j_driver, scripted, "2093-02") is None
    assert await _edge(neo4j_driver, held, "2093-01") == {
        "sign_ins": 7,
        "days": 4,
        "last_day": "2093-01-20",
    }

    # A sign-in logged after the first run is not picked up by a second.
    await _log(backends, "2093-06-01T08:00:00", user_uid=person, agent=_BROWSER)
    second = await backfill.apply_backfill(neo4j_driver)
    assert second.already_applied
    assert (second.user_months, second.sign_ins) == (0, 0)
    assert await _edge(neo4j_driver, person, "2093-06") is None
    assert await _edge(neo4j_driver, person, "2093-01") == {
        "sign_ins": 3,
        "days": 2,
        "last_day": "2093-01-31",
    }
    assert (
        await _scalar(
            neo4j_driver,
            "MATCH (r:MigrationRecord {name: $name}) RETURN count(r)",
            name=backfill.PRESENCE_BACKFILL,
        )
        == 1
    )
