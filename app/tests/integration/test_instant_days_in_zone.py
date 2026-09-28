"""An instant's day is its day in the zone, at the doors and in the graph (UTC arc, PR 3b).

Two halves, each on a UTC process (CI's host, and the pinned app's) whose default
zone is America/Vancouver — so the host's clock is not the zone's, and a read that
still takes a stamp's digits for its day, or a client's wall clock for the host's,
is red:

- **The ingest door** reads an authored offset-less ``created_at`` on the vault
  owner's clock (the sync's ``zone_scope``) and a bare day as that day's first
  instant there; the task creation rule then dates the task on the day the
  instant falls on for the owner. A door that read a naive value as UTC would
  store ``01:00`` in Bangkok seven hours late.
- **The graph's reads** compare a stored instant with a day's bounds in the zone,
  read on the stored clock (``stored_day_bounds``), never with the digits' own
  ``YYYY-MM-DD``: a habit completed at 20:00 in Vancouver (03:00Z the next day)
  is in that Vancouver day's window, and a Bangkok user's deadline at 05:00 on
  the 28th (22:00Z on the 27th) does not need deciding by the 27th. The deadline
  is written through the client door (``ClientDateTime``), which reads the
  user's ``datetime-local`` wall clock in their zone.

Rows come from the real writers (the ingest door, ``record_completion``,
``create_choice``), and each test reads its premise back raw.

See: /docs/roadmap/utc-instants-arc.md § PR 3
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.backends.activity_backends import ChoicesBackend, HabitsBackend
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.choice.choice import Choice
from core.models.choice.choice_request import ChoiceCreateRequest
from core.models.enums.neo_labels import NeoLabel
from core.models.habit.completion import HabitCompletion
from core.models.habit.habit import Habit
from core.models.type_hints import UserUID
from core.services.choices.choices_core_service import ChoicesCoreService
from core.services.habits.habits_completion_service import HabitsCompletionService
from core.services.user_service import UserService
from core.utils.timestamp_helpers import as_stored_clock
from core.utils.zone_context import zone_scope
from tests.helpers.forced_zone import forced_zone

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

VANCOUVER = ZoneInfo("America/Vancouver")
BANGKOK = ZoneInfo("Asia/Bangkok")
OWNER_UID = "user_test_integration"  # seeded by the ensure_test_users fixture

_RUN_ID = uuid.uuid4().hex[:8]


@pytest.fixture
def utc_host(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A UTC process; the default zone is Vancouver."""
    monkeypatch.delenv("SKUEL_TIMEZONE", raising=False)
    with forced_zone("UTC"):
        yield


async def _raw(neo4j_driver, query: str, **params: object) -> list[dict[str, object]]:
    async with neo4j_driver.session() as session:
        result = await session.run(query, **params)
        return [record.data() async for record in result]


# ---------------------------------------------------------------------------
# The ingest door
# ---------------------------------------------------------------------------


@pytest.fixture
def door(neo4j_driver):
    """The real ingestion service (CORE-tier shape: no bus, nothing to publish)."""
    from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
    from adapters.persistence.neo4j.ingestion_service_factory import (
        make_unified_ingestion_service,
    )
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

    return make_unified_ingestion_service(
        driver=neo4j_driver,
        ingestion_backend=IngestionBackend(executor=Neo4jQueryExecutor(neo4j_driver)),
    )


def _task_file(directory: Path, slug: str, created_at: str) -> Path:
    path = directory / f"{slug}.md"
    path.write_text(
        f"---\ntype: task\nuid: task.{slug}\ntitle: {slug}\nuser_uid: {OWNER_UID}\n"
        f"created_at: {created_at}\n---\n\nBody of {slug}.\n"
    )
    return path


async def _ingested(neo4j_driver, uid: str) -> dict[str, object]:
    rows = await _raw(
        neo4j_driver,
        "MATCH (n:Task {uid: $uid}) RETURN n.created_at AS created_at, "
        "valueType(n.created_at) AS created_type, n.due_date AS due_date",
        uid=uid,
    )
    assert len(rows) == 1, f"{uid} is not in the graph"
    return rows[0]


@pytest.mark.usefixtures("utc_host")
class TestTheIngestDoorReadsTheOwnersClock:
    async def test_an_offset_less_created_at_is_the_owners_wall_clock(
        self, clean_neo4j, neo4j_driver, door, tmp_path: Path
    ) -> None:
        """01:00 on the 27th in Bangkok is 18:00Z on the 26th; the task is due on
        the owner's 27th, though its UTC digits say the 26th."""
        slug = f"bangkok-small-hours-{_RUN_ID}"
        with zone_scope(BANGKOK):
            assert (await door.ingest_file(_task_file(tmp_path, slug, "2026-09-27T01:00:00"))).is_ok

        node = await _ingested(neo4j_driver, f"task.{slug}")
        assert str(node["created_type"]).startswith("STRING")
        assert node["created_at"] == "2026-09-26T18:00:00Z"
        assert node["due_date"] == "2026-09-27"

    async def test_a_bare_day_is_its_first_instant_in_the_owners_zone(
        self, clean_neo4j, neo4j_driver, door, tmp_path: Path
    ) -> None:
        slug = f"vancouver-bare-day-{_RUN_ID}"
        with zone_scope(VANCOUVER):
            assert (await door.ingest_file(_task_file(tmp_path, slug, "2026-09-27"))).is_ok

        node = await _ingested(neo4j_driver, f"task.{slug}")
        assert node["created_at"] == "2026-09-27T07:00:00Z"
        assert node["due_date"] == "2026-09-27"

    async def test_an_offset_bearing_created_at_keeps_its_instant(
        self, clean_neo4j, neo4j_driver, door, tmp_path: Path
    ) -> None:
        """20:00 on the 27th in Vancouver (03:00Z on the 28th): due on the owner's
        27th, not on the UTC day of the stored digits."""
        slug = f"vancouver-evening-{_RUN_ID}"
        with zone_scope(VANCOUVER):
            assert (
                await door.ingest_file(_task_file(tmp_path, slug, "2026-09-27T20:00:00-07:00"))
            ).is_ok

        node = await _ingested(neo4j_driver, f"task.{slug}")
        assert node["created_at"] == "2026-09-28T03:00:00Z"
        assert node["due_date"] == "2026-09-27"


# ---------------------------------------------------------------------------
# The graph's reads
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def users(neo4j_driver, clean_neo4j, user_service) -> AsyncIterator[UserService]:
    """The real UserService; removes the users the test registered."""
    yield user_service
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (u:User) WHERE u.uid ENDS WITH $run_id DETACH DELETE u", run_id=_RUN_ID
        )


async def _register(users: UserService, tag: str, zone: str | None = None) -> UserUID:
    created = await users.create_user(f"days_{tag}_{_RUN_ID}")
    assert created.is_ok, created
    uid = created.value.uid
    if zone is not None:
        chosen = await users.update_preferences(uid, {"timezone": zone})
        assert chosen.is_ok, chosen
    return uid


async def _zone_of(users: UserService, uid: UserUID) -> ZoneInfo:
    zone = await users.get_user_zone(uid)
    assert zone.is_ok, zone
    return zone.value


@pytest.mark.usefixtures("utc_host")
class TestAnInstantsDayInTheGraph:
    async def test_a_vancouver_evening_completion_is_in_that_days_window(
        self, neo4j_driver, users
    ) -> None:
        uid = await _register(users, "habit_window")
        zone = await _zone_of(users, uid)
        assert zone == VANCOUVER
        habits = HabitsBackend(neo4j_driver, NeoLabel.HABIT, Habit, base_label=NeoLabel.ENTITY)
        completions = HabitsCompletionService(
            habits,
            UniversalNeo4jBackend[HabitCompletion](
                neo4j_driver, NeoLabel.HABIT_COMPLETION, HabitCompletion
            ),
        )
        habit_uid = f"habit.evening_{_RUN_ID}"
        created = await habits.create(Habit(uid=habit_uid, title="Evening walk", user_uid=uid))
        assert created.is_ok, created

        # 20:00 on the 27th in Vancouver: 03:00Z on the 28th, stored on the host's
        # (UTC) clock.
        moment = datetime(2026, 9, 28, 3, 0, tzinfo=UTC)
        with zone_scope(zone):
            recorded = await completions.record_completion(
                habit_uid, uid, completed_at=as_stored_clock(moment)
            )
        assert recorded.is_ok, recorded
        stored = await _raw(
            neo4j_driver,
            "MATCH (c:HabitCompletion {habit_uid: $habit_uid}) RETURN c.completed_at AS at",
            habit_uid=habit_uid,
        )
        assert [row["at"] for row in stored] == ["2026-09-28T03:00:00"]

        with zone_scope(zone):
            on_the_27th = await completions.get_completions_for_habit(
                habit_uid, start_date=date(2026, 9, 27), end_date=date(2026, 9, 27)
            )
            on_the_28th = await completions.get_completions_for_habit(
                habit_uid, start_date=date(2026, 9, 28), end_date=date(2026, 9, 28)
            )
        assert on_the_27th.is_ok and on_the_28th.is_ok
        assert len(on_the_27th.value) == 1
        assert on_the_28th.value == []

    async def test_a_bangkok_deadline_is_on_the_bangkok_day(self, neo4j_driver, users) -> None:
        uid = await _register(users, "choice_deadline", zone="Asia/Bangkok")
        zone = await _zone_of(users, uid)
        assert zone == BANGKOK
        backend = ChoicesBackend(neo4j_driver, NeoLabel.CHOICE, Choice, base_label=NeoLabel.ENTITY)
        service = ChoicesCoreService(backend=backend, event_bus=InMemoryEventBus())

        # The user types 05:00 on the 28th into a datetime-local field: on their
        # clock. It is 22:00Z on the 27th — the stored clock is the host's (UTC).
        with zone_scope(zone):
            created = await service.create_choice(
                ChoiceCreateRequest(
                    title="Which offer",
                    description="Decide by dawn",
                    decision_deadline=datetime(2026, 9, 28, 5, 0),
                ),
                uid,
            )
        assert created.is_ok, created
        stored = await _raw(
            neo4j_driver,
            "MATCH (c:Choice {uid: $uid}) RETURN c.decision_deadline AS deadline",
            uid=created.value.uid,
        )
        assert [row["deadline"] for row in stored] == ["2026-09-27T22:00:00"]

        with zone_scope(zone):
            by_the_27th = await backend.get_choices_needing_decision(uid, "2026-09-27")
            by_the_28th = await backend.get_choices_needing_decision(uid, "2026-09-28")
        assert by_the_27th.is_ok and by_the_28th.is_ok
        assert by_the_27th.value == []
        assert [row["uid"] for row in by_the_28th.value] == [created.value.uid]
