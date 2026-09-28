"""The UTC instants migration, end to end on a real Neo4j (a testcontainer of its own).

A pre-cutover corpus is seeded through the real writers in a process moved back
onto the laptop's old clocks (``forced_zone`` — America/Vancouver, and UTC+7 for a
stamp dated February), so every stamp is stored as the old writers stored it: the
mapper's offset-less strings, ``datetime($now)`` natives from a naive clock, the
server's ``datetime()``, an aware handler's natives, a backfill's
``toString(localdatetime())``, a JSON property the reports read and one no code
reads. The census must settle every value; ``--confirm`` moves exactly the
laptop-clock digits, keeping each value's shape; ``--verify`` finds them moved and
the paired stamps together; a second ``--confirm`` and a census are refused;
``--revert`` puts every value back and the graph guard then refuses the graph.

The census reads the whole graph, so the module runs on its own container
(``scratch_neo4j_container``), emptied before each test.

See: /docs/roadmap/utc-instants-arc.md § Migration contract (PR 4)
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import time_machine

from adapters.persistence.neo4j.backends.activity_backends import GoalsBackend, TasksBackend
from adapters.persistence.neo4j.backends.collab_backends import GroupBackend, NotificationBackend
from adapters.persistence.neo4j.backends.curriculum_backends import KuBackend
from adapters.persistence.neo4j.backends.misc_backends import ActivityReportBackend
from adapters.persistence.neo4j.backends.sharing_backend import SharingBackend
from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from adapters.persistence.neo4j.embeddings_backend import EmbeddingsBackend
from adapters.persistence.neo4j.graph_driver import (
    UTC_INSTANTS_MIGRATION,
    GraphNotMigratedError,
    open_async_driver,
)
from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.events import PathStepEnrolled
from core.events.handlers.path_step_enrollment_handler import handle_path_step_enrolled
from core.models.entity import Entity
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.migration_enums import MigrationState
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.notification_enums import NotificationType
from core.models.goal.goal import Goal
from core.models.group.group import Group
from core.models.ku.ku import Ku
from core.models.report.activity_report import ActivityReport
from core.models.task.task import Task
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.services.goals.progress_history import progress_entry
from core.services.notifications.notification_service import NotificationService
from core.services.report.activity_report_service import ActivityReportService
from core.services.sharing.unified_sharing_service import UnifiedSharingService
from core.services.user_entry.user_entry_service import UserEntryService
from core.utils import timestamp_helpers
from core.utils.result_simplified import Result
from tests.helpers.forced_zone import forced_zone

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "migrations" / "utc_instants_2026_10.py"
_spec = importlib.util.spec_from_file_location("utc_instants_2026_10", SCRIPT)
assert _spec is not None and _spec.loader is not None
migration = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = migration
_spec.loader.exec_module(migration)

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.integration,
    pytest.mark.usefixtures("connection_settings"),
]

TEACHER = "user_utcmig_teacher"
STUDENT = "user_utcmig_student"
ADMIN = "user_utcmig_admin"
CLASS = "group.utcmig_class"


def _at(stamp: str) -> float:
    """A UTC ISO moment as the timestamp time_machine travels to (TZ is left alone)."""
    return datetime.fromisoformat(stamp).replace(tzinfo=UTC).timestamp()


@pytest_asyncio.fixture(loop_scope="session")
async def graph(scratch_neo4j_container: Any) -> AsyncIterator[Any]:
    """An unguarded driver onto the scratch container, emptied before and after each test."""
    driver = open_async_driver(
        scratch_neo4j_container.get_connection_url(), auth=("neo4j", "unused")
    )
    await driver.execute_query("MATCH (n) DETACH DELETE n")
    yield driver
    await driver.execute_query("MATCH (n) DETACH DELETE n")
    await driver.close()


async def _raw(driver: Any, query: str, **params: Any) -> list[dict[str, Any]]:
    result = await driver.execute_query(query, **params)
    return [dict(record) for record in result.records]


async def _value(driver: Any, query: str, **params: Any) -> tuple[str, str]:
    """``(valueType, text)`` of the one value a query returns as ``v``."""
    rows = await _raw(
        driver,
        query
        + " RETURN valueType(v) AS type, CASE WHEN v IS :: STRING THEN v ELSE toString(v) END AS text",
        **params,
    )
    assert len(rows) == 1, rows
    return str(rows[0]["type"]), str(rows[0]["text"])


class _NoAdmin:
    """The enrollment handler's admin lookup, answered with this module's admin."""

    async def get_admin_uid(
        self,
    ) -> Result[list[dict[str, str]]]:
        return Result.ok([{"admin_uid": ADMIN}])


@dataclass
class Corpus:
    task_uid: str
    feb_task_uid: str
    pair_task_uid: str
    inferred_task_uid: str
    goal_uid: str
    ku_uid: str
    entry_uid: str
    notification_uid: str
    report_uid: str


async def _seed(driver: Any) -> Corpus:
    """A pre-cutover corpus, written by the real writers on the laptop's old clocks."""
    await driver.execute_query(
        """
        MERGE (t:User {uid: $teacher}) SET t.display_name = 'Ms Rivera'
        MERGE (s:User {uid: $student}) SET s.display_name = 'Sam Student'
        MERGE (a:User {uid: $admin}) SET a.display_name = 'Admin', a.role = 'admin'
        MERGE (g:Group {uid: $group}) SET g.name = 'Essay class', g.is_active = true
        MERGE (t)-[:OWNS]->(g)
        """,
        teacher=TEACHER,
        student=STUDENT,
        admin=ADMIN,
        group=CLASS,
    )
    tasks = TasksBackend(driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)
    goals = GoalsBackend(driver, NeoLabel.GOAL, Goal, base_label=NeoLabel.ENTITY)
    kus = KuBackend(driver, NeoLabel.KU, Ku, base_label=NeoLabel.ENTITY)
    executor = Neo4jQueryExecutor(driver)
    groups = GroupBackend(driver, NeoLabel.GROUP, Group)
    sharing = UnifiedSharingService(backend=SharingBackend(driver, NeoLabel.ENTITY, Entity))
    entries = UserEntryService(backend=UserEntryBackend(driver), sharing_service=sharing)  # type: ignore[arg-type]
    notifications = NotificationService(backend=NotificationBackend(executor=executor))
    reports = ActivityReportService(
        backend=ActivityReportBackend(
            driver, NeoLabel.ACTIVITY_REPORT, ActivityReport, base_label=NeoLabel.ENTITY
        ),
        context_builder=None,  # type: ignore[arg-type]
        event_bus=None,
        sharing_service=sharing,
    )

    with _the_old_code():
        await _seed_on_the_old_clocks(
            driver, tasks, goals, kus, groups, sharing, entries, notifications, reports
        )
    touched = await EmbeddingsBackend(executor).touch_embedding_updated_at(["task.utcmig-pair"])
    assert touched.is_ok

    # The enrollment handler's default group and membership: aware, one moment.
    with time_machine.travel(_at("2026-09-22T10:00:00.654321"), tick=False):
        await handle_path_step_enrolled(
            PathStepEnrolled(user_uid=UserUID(STUDENT), ps_uid="ps.utcmig.step"),
            user_entry_backend=_NoAdmin(),
            group_backend=groups,
        )
    # The 2026-07 OWNS backfill's shape — ``toString(localdatetime())``, a server
    # clock read as UTC digits in milliseconds — over an edge its writer left bare.
    await driver.execute_query(
        """
        CREATE (:Entity:Exercise {uid: 'exercise.utcmig', user_uid: $student, title: 'Bare'})
        WITH 1 AS one
        MATCH (e:Entity {uid: 'exercise.utcmig'}), (owner:User {uid: e.user_uid})
        MERGE (owner)-[o:OWNS]->(e)
          ON CREATE SET o.created_at = toString(localdatetime('2026-07-05T19:15:00.372')),
                        o.last_accessed = toString(localdatetime('2026-07-05T19:15:00.372'))
        """,
        student=STUDENT,
    )
    rows = await _raw(driver, "MATCH (n:Notification) RETURN n.uid AS uid")
    report = await _raw(driver, "MATCH (n:ActivityReport) RETURN n.uid AS uid")
    return Corpus(
        task_uid="task.utcmig",
        feb_task_uid="task.utcmig-feb",
        pair_task_uid="task.utcmig-pair",
        inferred_task_uid="task.utcmig-inferred",
        goal_uid="goal.utcmig",
        ku_uid="ku.utcmig.concept",
        entry_uid="ue_utcmig",
        notification_uid=str(rows[0]["uid"]),
        report_uid=str(report[0]["uid"]),
    )


@contextmanager
def _the_old_code() -> Iterator[None]:
    """The code before the cutover: the stored clock is the host's (``None``)."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(timestamp_helpers, "STORED_INSTANT_CLOCK", None)
        yield


async def _seed_on_the_old_clocks(
    driver: Any,
    tasks: TasksBackend,
    goals: GoalsBackend,
    kus: KuBackend,
    groups: GroupBackend,
    sharing: UnifiedSharingService,
    entries: UserEntryService,
    notifications: NotificationService,
    reports: ActivityReportService,
) -> None:
    # UTC+7, before the zone change: the "+07" cohort.
    with (
        forced_zone("Asia/Bangkok"),
        time_machine.travel(_at("2026-02-01T11:12:42.404457"), tick=False),
    ):
        assert (
            await tasks.create(Task(uid="task.utcmig-feb", title="Feb", user_uid=STUDENT))
        ).is_ok

    with forced_zone("America/Vancouver"):
        with time_machine.travel(_at("2026-09-20T16:00:00.123456"), tick=False):
            assert (
                await tasks.create(Task(uid="task.utcmig", title="Sep", user_uid=STUDENT))
            ).is_ok
            assert (
                await tasks.create(
                    Task(
                        uid="task.utcmig-inferred",
                        title="Inferred",
                        user_uid=STUDENT,
                        knowledge_inference_metadata={
                            "inference_version": "2.4",
                            "inference_timestamp": datetime.now().isoformat(),
                        },
                    )
                )
            ).is_ok
            assert (
                await goals.create(
                    Goal(
                        uid="goal.utcmig",
                        title="Progressed",
                        user_uid=STUDENT,
                        status=EntityStatus.ACTIVE,
                        progress_history=(dict(progress_entry(10.0, datetime.now())),),
                    )
                )
            ).is_ok
            assert (await kus.create(Ku(uid="ku.utcmig.concept", title="A concept"))).is_ok
            substance = await kus.increment_substance(
                "ku.utcmig.concept",
                "times_reflected_in_entries",
                "last_reflected_date",
                datetime.now().isoformat(),
            )
            assert substance.is_ok, substance.expect_error()
            # A teacher adds the student to an owned, non-default group (add_member's clock).
            added = await groups.add_member(
                CLASS, UserUID(STUDENT), joined_at=datetime.now().isoformat()
            )
            assert added.is_ok, added.expect_error()

        with time_machine.travel(_at("2026-09-21T01:30:00.000321"), tick=False):
            created = await entries.create_entry(
                UserEntryCreateRequest(
                    uid="ue_utcmig",
                    title="Where I grew up",
                    content="A river town, and the bridge we crossed every day.",
                ),
                UserUID(STUDENT),
            )
            assert created.is_ok, created.expect_error()
        with time_machine.travel(_at("2026-09-21T01:45:00.250123"), tick=False):
            shared = await sharing.share_with_group("ue_utcmig", STUDENT, CLASS)
            assert shared.is_ok, shared.expect_error()
        with time_machine.travel(_at("2026-09-28T00:40:00.500123"), tick=False):
            personal = await sharing.share("ue_utcmig", STUDENT, TEACHER)
            assert personal.is_ok, personal.expect_error()
        with time_machine.travel(_at("2026-09-28T00:41:00.750123"), tick=False):
            notified = await notifications.create_notification(
                user_uid=UserUID(TEACHER),
                notification_type=NotificationType.SHARED_WITH_YOU,
                title="Sam Student shared an entry with you",
                message="Where I grew up",
                source_uid="ue_utcmig",
                source_type=EntityType.USER_ENTRY,
            )
            assert notified.is_ok, notified.expect_error()
        with time_machine.travel(_at("2026-09-28T03:10:00.100123"), tick=False):
            written = await reports.submit_report(
                admin_uid=TEACHER,
                subject_uid=STUDENT,
                feedback_text="A steady month.",
                time_period="2026-09",
            )
            assert written.is_ok, written.expect_error()

        # Created on the laptop's real clock, then embedded by the server in the same
        # moment: the classification check's pair (7.00 h apart before the move).
        assert (
            await tasks.create(Task(uid="task.utcmig-pair", title="Pair", user_uid=STUDENT))
        ).is_ok


async def _census(driver: Any, uri: str) -> Any:
    async with driver.session(default_access_mode="READ") as session:
        tx = await session.begin_transaction()
        try:
            return await migration.run_census(tx, uri)
        finally:
            await tx.rollback()


def _verdicts(census: Any) -> dict[tuple[str, str], set[str]]:
    out: dict[tuple[str, str], set[str]] = {}
    for stamp in census.stamps:
        out.setdefault(
            (f"{stamp.owner}.{stamp.prop}{stamp.json_path or ''}", stamp.value.cls.name), set()
        ).add(stamp.verdict.value)
    return out


async def test_census_confirm_verify_then_revert_move_only_the_laptop_clock_digits(
    graph: Any, scratch_neo4j_container: Any, tmp_path: Path
) -> None:
    corpus = await _seed(graph)
    uri = scratch_neo4j_container.get_connection_url()
    census = await _census(graph, uri)
    assert not census.stops and not census.key_stops, [
        (s.owner, s.prop, s.value.text, s.reason) for s in census.stops
    ] + census.key_stops

    verdicts = _verdicts(census)
    for owner_prop, verdict in [
        ("(:Task).created_at", "shift"),
        ("[:OWNS].created_at", "shift"),
        ("(:UserEntry).created_at", "shift"),
        ("(:Notification).created_at", "shift"),
        ("[:SHARED_WITH_GROUP].shared_at", "shift"),
        ("[:SHARES_WITH].shared_at", "shift"),
        ("(:Ku).last_reflected_date", "shift"),
        ("[:MEMBER_OF].joined_at", "shift"),
        ("(:ActivityReport).period_start", "shift"),
        ("(:ActivityReport).data_cutoff", "shift"),
        ("(:Goal).progress_history$[].date", "shift"),
        ("(:Task).knowledge_inference_metadata$.inference_timestamp", "leave"),
        ("(:ActivityReport).metadata$.data_cutoff", "leave"),
        ("(:Task).embedding_updated_at", "leave"),
        ("(:Group).created_at", "leave"),
    ]:
        assert any(key[0] == owner_prop and verdict in found for key, found in verdicts.items()), (
            owner_prop,
            verdict,
            {k: v for k, v in verdicts.items() if k[0] == owner_prop},
        )
    # The enrollment handler's membership is paired with its group's created_at;
    # add_member's on the class group moves; the backfill's OWNS strings stay.
    member_verdicts = {s.end_uid: s.verdict.value for s in census.stamps if s.prop == "joined_at"}
    assert member_verdicts == {CLASS: "shift", f"group_default_{ADMIN}": "leave"}
    owns_ms = [
        s for s in census.stamps if s.owner == "[:OWNS]" and s.value.cls.name == "STR_NAIVE_MS"
    ]
    assert owns_ms and all(s.verdict.value == "leave" for s in owns_ms)
    assert len(census.pairs) == 1 and census.pairs[0]["key"]["key"] == corpus.pair_task_uid

    before = {
        "task": await _value(
            graph, "MATCH (n:Task {uid: $uid}) WITH n.created_at AS v", uid=corpus.task_uid
        ),
        "feb": await _value(
            graph, "MATCH (n:Task {uid: $uid}) WITH n.created_at AS v", uid=corpus.feb_task_uid
        ),
        "notification": await _value(
            graph,
            "MATCH (n:Notification {uid: $uid}) WITH n.created_at AS v",
            uid=corpus.notification_uid,
        ),
        "embedding": await _value(
            graph,
            "MATCH (n:Task {uid: $uid}) WITH n.embedding_updated_at AS v",
            uid=corpus.pair_task_uid,
        ),
        "inferred": await _value(
            graph,
            "MATCH (n:Task {uid: $uid}) WITH n.knowledge_inference_metadata AS v",
            uid=corpus.inferred_task_uid,
        ),
        "progress": await _value(
            graph, "MATCH (n:Goal {uid: $uid}) WITH n.progress_history AS v", uid=corpus.goal_uid
        ),
    }
    assert before["task"] == ("STRING NOT NULL", "2026-09-20T09:00:00.123456")
    assert before["feb"] == ("STRING NOT NULL", "2026-02-01T18:12:42.404457")
    assert before["notification"] == ("ZONED DATETIME NOT NULL", "2026-09-27T17:41:00.750123Z")

    path, digest = migration.write_manifest(migration.build_manifest(census), tmp_path)
    manifest = migration.load_manifest(tmp_path, digest)
    assert path.name == f"manifest-{digest}.json"
    await migration.confirm(graph, manifest, digest, uri)

    # Each value keeps its shape (R5): an offset-less string, a native.
    assert await _value(
        graph, "MATCH (n:Task {uid: $uid}) WITH n.created_at AS v", uid=corpus.task_uid
    ) == (
        "STRING NOT NULL",
        "2026-09-20T16:00:00.123456",
    )
    assert await _value(
        graph, "MATCH (n:Task {uid: $uid}) WITH n.created_at AS v", uid=corpus.feb_task_uid
    ) == (
        "STRING NOT NULL",
        "2026-02-01T11:12:42.404457",
    )
    assert await _value(
        graph,
        "MATCH (n:Notification {uid: $uid}) WITH n.created_at AS v",
        uid=corpus.notification_uid,
    ) == ("ZONED DATETIME NOT NULL", "2026-09-28T00:41:00.750123Z")
    # What was already UTC, and what no code reads, is untouched.
    assert (
        await _value(
            graph,
            "MATCH (n:Task {uid: $uid}) WITH n.embedding_updated_at AS v",
            uid=corpus.pair_task_uid,
        )
        == before["embedding"]
    )
    assert (
        await _value(
            graph,
            "MATCH (n:Task {uid: $uid}) WITH n.knowledge_inference_metadata AS v",
            uid=corpus.inferred_task_uid,
        )
        == before["inferred"]
    )
    progress_type, progress_text = await _value(
        graph, "MATCH (n:Goal {uid: $uid}) WITH n.progress_history AS v", uid=corpus.goal_uid
    )
    assert progress_type == "STRING NOT NULL"
    assert "2026-09-20T16:00:00.123456" in progress_text
    assert progress_text == before["progress"][1].replace(
        "2026-09-20T09:00:00.123456", "2026-09-20T16:00:00.123456"
    )

    records = await _raw(
        graph,
        "MATCH (r:MigrationRecord {name: $name}) RETURN r.state AS state, r.manifest_hash AS hash",
        name=UTC_INSTANTS_MIGRATION,
    )
    assert records == [{"state": MigrationState.APPLIED, "hash": digest}]

    verification = await migration.verify(graph, tmp_path)
    assert verification.ok, verification
    assert (
        verification.pairs,
        verification.pairs_apart_before,
        verification.pairs_together_after,
    ) == (1, 1, 1)
    # The check reads both of the pair's values from the graph: a changed embedding
    # stamp fails it, though the manifest still holds the census's value.
    await graph.execute_query(
        "MATCH (n:Task {uid: $uid}) SET n.embedding_updated_at = n.embedding_updated_at + duration('PT3H')",
        uid=corpus.pair_task_uid,
    )
    assert not (await migration.verify(graph, tmp_path)).ok
    await graph.execute_query(
        "MATCH (n:Task {uid: $uid}) SET n.embedding_updated_at = n.embedding_updated_at - duration('PT3H')",
        uid=corpus.pair_task_uid,
    )

    # Applied: a second confirm and a census are refused, and nothing moves.
    with pytest.raises(migration.RefusedError, match="'applied'"):
        await migration.confirm(graph, manifest, digest, uri)
    async with graph.session(default_access_mode="READ") as session:
        tx = await session.begin_transaction()
        try:
            refusal = migration._state_refusal(
                await migration.read_record_states(tx), allowed={None, MigrationState.REVERTED}
            )
        finally:
            await tx.rollback()
    assert refusal is not None and "'applied'" in refusal

    # The app's guard opens the migrated graph.
    opened = Neo4jConnection(uri=uri, username="neo4j", password="unused")
    await opened.connect()
    await opened.close()

    await migration.revert(graph, tmp_path)
    assert (
        await _value(
            graph, "MATCH (n:Task {uid: $uid}) WITH n.created_at AS v", uid=corpus.task_uid
        )
        == before["task"]
    )
    assert (
        await _value(
            graph, "MATCH (n:Task {uid: $uid}) WITH n.created_at AS v", uid=corpus.feb_task_uid
        )
        == before["feb"]
    )
    assert (
        await _value(
            graph,
            "MATCH (n:Notification {uid: $uid}) WITH n.created_at AS v",
            uid=corpus.notification_uid,
        )
        == before["notification"]
    )
    assert (
        await _value(
            graph, "MATCH (n:Goal {uid: $uid}) WITH n.progress_history AS v", uid=corpus.goal_uid
        )
        == before["progress"]
    )
    records = await _raw(
        graph,
        "MATCH (r:MigrationRecord {name: $name}) RETURN r.state AS state",
        name=UTC_INSTANTS_MIGRATION,
    )
    assert records == [{"state": MigrationState.REVERTED}]
    refused = Neo4jConnection(uri=uri, username="neo4j", password="unused")
    with pytest.raises(GraphNotMigratedError, match="'reverted'"):
        await refused.connect()


async def test_a_value_changed_since_the_census_rolls_the_whole_confirm_back(
    graph: Any, scratch_neo4j_container: Any, tmp_path: Path
) -> None:
    corpus = await _seed(graph)
    uri = scratch_neo4j_container.get_connection_url()
    census = await _census(graph, uri)
    manifest_data = migration.build_manifest(census)
    _, digest = migration.write_manifest(manifest_data, tmp_path)
    manifest = migration.load_manifest(tmp_path, digest)

    # The app wrote after the census: one Task's created_at is no longer the census's.
    await graph.execute_query(
        "MATCH (n:Task {uid: $uid}) SET n.created_at = '2026-09-29T08:00:00.000001'",
        uid=corpus.feb_task_uid,
    )
    with pytest.raises(migration.ConflictError) as conflict:
        await migration.confirm(graph, manifest, digest, uri)
    changed = [
        row["id"]
        for row in manifest["rows"]
        if row["key"].get("key") == corpus.feb_task_uid and row["property"] == "created_at"
    ]
    assert conflict.value.ids == sorted(changed)

    # Nothing was written: every other row still holds its old value, and no record.
    async with graph.session(default_access_mode="READ") as session:
        tx = await session.begin_transaction()
        try:
            still_old = await migration.rows_not_at(tx, list(manifest["rows"]), "old")
        finally:
            await tx.rollback()
    assert still_old == sorted(changed)
    assert await _raw(graph, "MATCH (r:MigrationRecord) RETURN r") == []


async def test_compare_and_set_on_a_native_is_typed(
    graph: Any, scratch_neo4j_container: Any, tmp_path: Path
) -> None:
    """A string holding a native's exact text is not that native: the confirm conflicts."""
    corpus = await _seed(graph)
    uri = scratch_neo4j_container.get_connection_url()
    census = await _census(graph, uri)
    _, digest = migration.write_manifest(migration.build_manifest(census), tmp_path)
    manifest = migration.load_manifest(tmp_path, digest)
    await graph.execute_query(
        "MATCH (n:Notification {uid: $uid}) SET n.created_at = toString(n.created_at)",
        uid=corpus.notification_uid,
    )
    with pytest.raises(migration.ConflictError) as conflict:
        await migration.confirm(graph, manifest, digest, uri)
    assert [manifest["rows"][i]["owner"] for i in conflict.value.ids] == ["(:Notification)"]


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("zone_change_day", "zone change day"),
        ("utc_clock_process", "a UTC-clock process wrote it"),
        ("unknown_property", "no rule for this label and property"),
        ("unpaired_default_group", "no paired stamp settles"),
        ("duplicate_relationship_key", "resolves to 2 element(s)"),
        ("unreadable_stamp_form", "is not a shape this property's writers produce"),
        ("list_of_stamps", "is not a shape this property's writers produce"),
    ],
)
async def test_the_census_stops_on_what_no_rule_settles(
    graph: Any, scratch_neo4j_container: Any, case: str, reason: str
) -> None:
    await graph.execute_query(
        "MERGE (:User {uid: $student}) MERGE (:User {uid: $teacher}) "
        "MERGE (:User {uid: $admin})-[:OWNS]->(:Group {uid: $default, name: 'Default'})",
        student=STUDENT,
        teacher=TEACHER,
        admin=ADMIN,
        default=f"group_default_{ADMIN}",
    )
    tasks = TasksBackend(graph, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)
    if case == "zone_change_day":
        with (
            _the_old_code(),
            forced_zone("America/Vancouver"),
            time_machine.travel(_at("2026-03-27T20:00:00"), tick=False),
        ):
            assert (
                await tasks.create(Task(uid="task.change-day", title="x", user_uid=STUDENT))
            ).is_ok
    elif case == "utc_clock_process":
        # A process on UTC (the pin, or a UTC host) writing now: digits ahead of the laptop's.
        assert (await tasks.create(Task(uid="task.utc-process", title="x", user_uid=STUDENT))).is_ok
    elif case == "unknown_property":
        await graph.execute_query(
            "CREATE (:Entity:Task {uid: 'task.odd', odd_at: '2026-09-01T10:00:00.000001'})"
        )
    elif case == "unpaired_default_group":
        groups = GroupBackend(graph, NeoLabel.GROUP, Group)
        with _the_old_code(), forced_zone("America/Vancouver"):
            added = await groups.add_member(
                f"group_default_{ADMIN}", UserUID(STUDENT), joined_at=datetime.now().isoformat()
            )
        assert added.is_ok
    elif case == "duplicate_relationship_key":
        await graph.execute_query(
            "MATCH (s:User {uid: $student}), (t:User {uid: $teacher}) "
            "CREATE (e:Entity:UserEntry {uid: 'ue_dup'}) "
            "CREATE (t)-[:SHARES_WITH {shared_at: datetime('2026-09-20T09:00:00.123456Z')}]->(e) "
            "CREATE (t)-[:SHARES_WITH {shared_at: datetime('2026-09-20T09:00:01.123456Z')}]->(e)",
            student=STUDENT,
            teacher=TEACHER,
        )
    elif case == "unreadable_stamp_form":
        # A form datetime.fromisoformat reads (a comma for the decimal point) and the
        # classifier does not: a stamp all the same, so it stops.
        await graph.execute_query(
            "CREATE (:Entity:Task {uid: 'task.comma', created_at: '2026-09-20T09:00:00,123456'})"
        )
    elif case == "list_of_stamps":
        await graph.execute_query(
            "CREATE (:Entity:Task {uid: 'task.listed', "
            "created_at: [datetime('2026-09-20T09:00:00.123456Z')]})"
        )
    census = await _census(graph, scratch_neo4j_container.get_connection_url())
    reasons = [s.reason for s in census.stops] + census.key_stops
    assert any(reason in r for r in reasons), reasons


async def test_the_command_line_runs_the_whole_sitting(
    graph: Any,
    scratch_neo4j_container: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """census → --confirm HASH → --verify → a refused --confirm and census → --revert → census."""
    await _seed(graph)
    uri = scratch_neo4j_container.get_connection_url()
    import adapters.persistence.neo4j.neo4j_connection as connection

    def to_the_scratch_graph(*, utc_instants_guard: bool = True) -> Neo4jConnection:
        return Neo4jConnection(
            uri=uri, username="neo4j", password="unused", utc_instants_guard=utc_instants_guard
        )

    monkeypatch.setattr(connection, "Neo4jConnection", to_the_scratch_graph)

    async def run(*args: str) -> tuple[int, str]:
        code = await migration.main([*args, "--manifest-dir", str(tmp_path)])
        return code, capsys.readouterr().out

    code, out = await run()
    assert code == 0, out
    digest = out.split("Hash:", 1)[1].split()[0]
    assert (await run("--confirm", digest))[0] == 0
    code, out = await run("--verify")
    assert code == 0 and "\nOK" in out, out
    code, out = await run("--confirm", digest)
    assert code == 1 and "REFUSED" in out, out
    code, out = await run()
    assert code == 1 and "REFUSED" in out, out
    assert (await run("--revert"))[0] == 0
    code, out = await run("--verify")
    assert code == 1 and "REFUSED" in out, out
    code, out = await run()
    assert code == 0, out  # a reverted graph may be censused and confirmed again
