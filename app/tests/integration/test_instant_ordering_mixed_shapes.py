"""Orderings over instant columns whose writers store both shapes (UTC arc, PR 6b).

An instant is a string when the mapper writes it (``isoformat()``) and a native
when a Cypher ``datetime()`` writer does. Neo4j orders values of different
types by type before value — every string after every temporal, so first under
``DESC`` — and ``max()`` of a string and a native is the string. Each test here
seeds two rows through the real writers, one stamp of each shape, in BOTH
arrangements (the newer one a native, then the newer one a string): a raw
ordering is right in one arrangement and wrong in the other, so only the
coerced ordering passes both. Each test reads the stored stamps' types back, so
it pins its own premise.

The last three read a column of one shape whose raw order is still wrong: a
string with an offset sorts by its digits, and a ``toString`` of natives ranks
a whole second after its own fractions.

See: /docs/roadmap/utc-instants-arc.md § PR 6
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast

import pytest
import time_machine
from neo4j import AsyncDriver

from adapters.persistence.neo4j.backends.activity_backends import ChoicesBackend, TasksBackend
from adapters.persistence.neo4j.backends.collab_backends import GroupBackend
from adapters.persistence.neo4j.backends.curriculum_backends import KuBackend
from adapters.persistence.neo4j.backends.sharing_backend import SharingBackend
from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from adapters.persistence.neo4j.bulk_upsert_backend import BulkUpsertBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.search_event_backend import SearchEventBackend
from core.events.search_events import SearchExecuted
from core.models.choice.choice import Choice
from core.models.entity import Entity
from core.models.enums import SearchVisibility
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.group.group import Group
from core.models.ku.ku import Ku
from core.models.task.task import Task
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.services.groups.group_service import GroupService
from core.services.search_event_recorder import SearchEventRecorder
from core.services.sharing.unified_sharing_service import UnifiedSharingService
from core.services.user_entry.user_entry_service import UserEntryService

TEACHER = "user_6b_teacher"
STUDENT = "user_6b_student"
GROUP = "group_6b_class"
EXERCISE_A = "ex_6b_first"
EXERCISE_B = "ex_6b_second"
STEP = "ps.6b.step"

NATIVE = "ZONED DATETIME NOT NULL"
STRING = "STRING NOT NULL"


def _instants(newer_is_native: bool) -> tuple[datetime, datetime]:
    """``(native_at, string_at)``: one an hour ago, the other two days ago."""
    now = datetime.now(UTC).replace(microsecond=0)
    newer, older = now - timedelta(hours=1), now - timedelta(days=2)
    return (newer, older) if newer_is_native else (older, newer)


def _at(moment: datetime) -> time_machine.travel:
    """Freeze the process clock at ``moment`` (a timestamp — see the arc's time-machine note)."""
    return time_machine.travel(moment.timestamp(), tick=False)


async def _stamp_types(driver: AsyncDriver, prop: str, uids: list[str]) -> dict[str, str]:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (n) WHERE n.uid IN $uids RETURN n.uid AS uid, valueType(n[$prop]) AS type",
            uids=uids,
            prop=prop,
        )
        return {str(row["uid"]): str(row["type"]) for row in await result.data()}


class _HasUid(Protocol):
    uid: str


def _uids(rows: Sequence[Mapping[str, object] | _HasUid]) -> list[str]:
    """The uids of rows that are models or ``uid``-keyed maps."""
    return [str(row["uid"] if isinstance(row, Mapping) else row.uid) for row in rows]


def _entity_uids(rows: Sequence[Mapping[str, object]]) -> list[str]:
    """The uids of the ``entity`` column's nodes."""
    return _uids(
        [cast("Mapping[str, object]", row["entity"]) for row in rows]
    )  # boundary: neo4j Node


async def _seed_classroom(driver: AsyncDriver) -> None:
    """The structure the writers need, none of it a stamp under test: two users,
    the teacher's group with the student in it, and two exercises as the content-vault
    sync writes them — curriculum, naming the teacher (``REVIEWED_BY``), hanging from a
    published step the student is in progress on."""
    async with driver.session() as session:
        await session.run(
            """
            MERGE (t:User {uid: $teacher})
            SET t.display_name = 'Teacher', t.title = 'teacher', t.role = 'teacher'
            MERGE (s:User {uid: $student}) SET s.display_name = 'Student', s.title = 'student'
            MERGE (g:Group {uid: $group}) SET g.name = 'Class', g.is_active = true
            MERGE (t)-[:OWNS]->(g)
            MERGE (s)-[:MEMBER_OF]->(g)
            MERGE (ps:Entity:PathStep {uid: $step})
            SET ps.title = $step, ps.entity_type = 'path_step', ps.status = 'active',
                ps.publication_state = 'published'
            MERGE (s)-[ip:IN_PROGRESS]->(ps)
            SET ip.started_at = datetime(), ip.last_activity_at = datetime(),
                ip.progress_score = 0.0
            WITH t, ps
            UNWIND $exercises AS exercise_uid
            MERGE (ex:Entity:Exercise {uid: exercise_uid})
            SET ex.title = exercise_uid, ex.entity_type = 'exercise',
                ex.status = 'active', ex.visibility = 'private', ex.scope = 'curriculum'
            MERGE (ex)-[:REVIEWED_BY]->(t)
            MERGE (ps)-[:HAS_EXERCISE]->(ex)
            """,
            teacher=TEACHER,
            student=STUDENT,
            group=GROUP,
            step=STEP,
            exercises=[EXERCISE_A, EXERCISE_B],
        )


# ============================================================================
# Group.created_at — the service's create (string), the default group (native)
# ============================================================================


@pytest.mark.parametrize("newer_is_native", [True, False])
async def test_groups_list_newest_first(clean_neo4j, neo4j_driver, newer_is_native) -> None:
    await _seed_classroom(neo4j_driver)
    groups = GroupBackend(driver=neo4j_driver, label=NeoLabel.GROUP, entity_class=Group)
    native_at, string_at = _instants(newer_is_native)

    default = await groups.get_or_create_default_group(TEACHER, native_at.isoformat())
    assert default.is_ok, default.expect_error()
    default_uid = str(default.value[0]["group_uid"])
    with _at(string_at):
        created = await GroupService(backend=groups).create(
            Group(uid="group_6b_string", name="String-stamped", owner_uid=TEACHER)
        )
    assert created.is_ok, created.expect_error()
    assert await _stamp_types(neo4j_driver, "created_at", [default_uid, "group_6b_string"]) == {
        default_uid: NATIVE,
        "group_6b_string": STRING,
    }
    newest_first = [default_uid, "group_6b_string"]
    if not newer_is_native:
        newest_first.reverse()

    owned = await groups.get_user_groups(UserUID(TEACHER), include_owned=True)
    stats = await groups.get_teacher_groups_with_stats(TEACHER)

    assert owned.is_ok and stats.is_ok
    # The seeded classroom carries no created_at; the order read is the two stamped groups'.
    assert [uid for uid in _uids(owned.value) if uid in newest_first] == newest_first
    assert [uid for uid in _uids(stats.value) if uid in newest_first] == newest_first


# ============================================================================
# Task.updated_at — the picker's recent list (an edit: string; a re-sync: native)
# ============================================================================


@pytest.mark.parametrize("newer_is_native", [True, False])
async def test_recent_tasks_list_by_last_update(clean_neo4j, neo4j_driver, newer_is_native) -> None:
    tasks = TasksBackend(neo4j_driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)
    user = UserUID("user_test")
    for uid in ("task_6b_edited", "task_6b_resynced"):
        created = await tasks.create(
            Task(uid=uid, title=uid, entity_type=EntityType.TASK, user_uid=user)
        )
        assert created.is_ok, created.expect_error()

    # The re-sync stamps the database's own clock (now); the edit is placed a
    # day either side of it.
    edit_at = datetime.now(UTC) + timedelta(days=-1 if newer_is_native else 1)
    if newer_is_native:
        with _at(edit_at):
            assert (await tasks.update("task_6b_edited", {"title": "edited"})).is_ok
    # A vault re-sync carries the task's owner — the upsert writes nothing to a
    # node someone else owns, and a row naming no owner is not the owner's.
    resynced = await BulkUpsertBackend(neo4j_driver).upsert_nodes(
        "Task",
        "Entity",
        [{"uid": "task_6b_resynced", "title": "resynced", "user_uid": str(user)}],
        {},
    )
    assert resynced.is_ok, resynced.expect_error()
    if not newer_is_native:
        with _at(edit_at):
            assert (await tasks.update("task_6b_edited", {"title": "edited"})).is_ok

    assert await _stamp_types(
        neo4j_driver, "updated_at", ["task_6b_edited", "task_6b_resynced"]
    ) == {"task_6b_edited": STRING, "task_6b_resynced": NATIVE}
    newest_first = ["task_6b_resynced", "task_6b_edited"]
    if not newer_is_native:
        newest_first.reverse()

    recent = await tasks.get_user_entities(user, sort_by="updated_at", sort_order="desc")

    assert recent.is_ok, recent.expect_error()
    listed = [uid for uid in _uids(recent.value[0]) if uid.startswith("task_6b_")]
    assert listed == newest_first


# ============================================================================
# Ku.updated_at — the search builders, ordered by Ku's search_order_by
# ============================================================================


@pytest.mark.parametrize("newer_is_native", [True, False])
async def test_curriculum_searches_list_by_last_update(
    clean_neo4j, neo4j_driver, newer_is_native
) -> None:
    kus = KuBackend(neo4j_driver, NeoLabel.KU, Ku, base_label=NeoLabel.ENTITY)
    for uid in ("ku.6b.edited", "ku.6b.resynced"):
        created = await kus.create(Ku(uid=uid, title=f"Breath {uid}", tags=["breath"]))
        assert created.is_ok, created.expect_error()

    edit_at = datetime.now(UTC) + timedelta(days=-1 if newer_is_native else 1)
    if newer_is_native:
        with _at(edit_at):
            assert (await kus.update("ku.6b.edited", {"description": "edited"})).is_ok
    resynced = await BulkUpsertBackend(neo4j_driver).upsert_nodes(
        "Ku", "Entity", [{"uid": "ku.6b.resynced", "description": "resynced"}], {}
    )
    assert resynced.is_ok, resynced.expect_error()
    if not newer_is_native:
        with _at(edit_at):
            assert (await kus.update("ku.6b.edited", {"description": "edited"})).is_ok

    assert await _stamp_types(neo4j_driver, "updated_at", ["ku.6b.edited", "ku.6b.resynced"]) == {
        "ku.6b.edited": STRING,
        "ku.6b.resynced": NATIVE,
    }
    newest_first = ["ku.6b.resynced", "ku.6b.edited"]
    if not newer_is_native:
        newest_first.reverse()

    # Ku's DomainConfig: search_order_by="updated_at", search_visibility=PUBLIC.
    public = SearchVisibility.PUBLIC
    text = await kus.text_search_raw("breath", ("title",), order_by="updated_at", visibility=public)
    tags = await kus.array_any_match_raw(
        "tags", ["breath"], order_by="updated_at", visibility=public
    )
    faceted = await kus.faceted_search_raw(
        user_uid=None,
        search_fields=("title",),
        search_order_by="updated_at",
        graph_enrichment_patterns=(),
        property_filters={},
        query_text="breath",
        visibility=public,
    )

    assert text.is_ok and tags.is_ok and faceted.is_ok
    assert _uids(text.value) == newest_first
    assert _uids(tags.value) == newest_first
    assert _entity_uids(faceted.value) == newest_first


# ============================================================================
# Choice.decision_deadline — client deadlines keep their offsets (one shape,
# strings that do not sort as their instants)
# ============================================================================


async def test_pending_choices_order_by_the_deadline_instant(clean_neo4j, neo4j_driver) -> None:
    choices = ChoicesBackend(neo4j_driver, NeoLabel.CHOICE, Choice, base_label=NeoLabel.ENTITY)
    user = UserUID("user_test")
    # 10:00 at -07:00 is 17:00Z, after the offset-less 12:00 (UTC) — though its
    # digits sort first.
    deadlines = {
        "choice_6b_offset": datetime.fromisoformat("2026-10-01T10:00:00-07:00"),
        "choice_6b_utc": datetime.fromisoformat("2026-10-01T12:00:00"),
    }
    for uid, deadline in deadlines.items():
        created = await choices.create(
            Choice(
                uid=uid,
                title=uid,
                entity_type=EntityType.CHOICE,
                user_uid=user,
                decision_deadline=deadline,
            )
        )
        assert created.is_ok, created.expect_error()
    assert await _stamp_types(neo4j_driver, "decision_deadline", list(deadlines)) == {
        uid: STRING for uid in deadlines
    }

    pending = await choices.get_pending_choices(user)

    assert pending.is_ok, pending.expect_error()
    listed = _uids(pending.value)
    assert listed == ["choice_6b_utc", "choice_6b_offset"]


# ============================================================================
# SHARES_WITH.shared_at — the Shared lists order by the share's instant, not
# its text (natives; a whole second's text sorts after its own fractions)
# ============================================================================


async def test_shared_lists_order_by_the_share_instant(clean_neo4j, neo4j_driver) -> None:
    await _seed_classroom(neo4j_driver)
    sharing = UnifiedSharingService(backend=SharingBackend(neo4j_driver, NeoLabel.ENTITY, Entity))
    entries = UserEntryService(backend=UserEntryBackend(neo4j_driver), sharing_service=sharing)  # type: ignore[arg-type]
    second = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    # The earlier share lands on a whole second; the later one half a second on.
    shares = {"first": second, "later": second + timedelta(milliseconds=500)}

    entry_uids: dict[str, str] = {}
    for name, moment in shares.items():
        created = await entries.create_entry(
            UserEntryCreateRequest(title=f"Entry {name}", content="Text."), UserUID(STUDENT)
        )
        assert created.is_ok, created.expect_error()
        entry_uids[name] = created.value[0].uid
        with _at(moment):
            shared = await sharing.share(entry_uids[name], STUDENT, TEACHER)
        assert shared.is_ok, shared.expect_error()

    with_me = await sharing.backend.query_shared_with_me(UserUID(TEACHER), limit=10)
    by_me = await sharing.backend.query_shared_by_me(UserUID(STUDENT), limit=10)

    newest_first = [entry_uids["later"], entry_uids["first"]]
    assert with_me.is_ok and by_me.is_ok
    assert _entity_uids(with_me.value) == newest_first
    assert _entity_uids(by_me.value) == newest_first


# ============================================================================
# SearchEvent.created_at — the gap report's tie-break orders by the instant
# ============================================================================


async def test_search_gaps_break_ties_by_the_last_search_instant(neo4j_driver) -> None:
    backend = SearchEventBackend(Neo4jQueryExecutor(neo4j_driver))
    async with neo4j_driver.session() as session:
        await session.run("MATCH (e:SearchEvent) DETACH DELETE e")
    recorder = SearchEventRecorder(backend=backend)
    second = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    for query, moment in (
        ("zz whole second", second),
        ("zz half second on", second + timedelta(milliseconds=500)),
    ):
        await recorder.handle_search_executed(
            SearchExecuted(
                query_text=query,
                user_uid=UserUID("user_test"),
                entry_point="faceted",
                result_count=0,
                zero_results=True,
                domains=("ku",),
                filters_json="{}",
                occurred_at=moment,
            )
        )

    gaps = await backend.get_search_gaps(max_result_count=2, days=90)

    async with neo4j_driver.session() as session:
        await session.run("MATCH (e:SearchEvent) DETACH DELETE e")
    assert gaps.is_ok, gaps.expect_error()
    assert [row["query"] for row in gaps.value] == ["zz half second on", "zz whole second"]
