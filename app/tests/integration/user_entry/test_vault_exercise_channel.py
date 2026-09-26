"""
Vault Notes Are Drafts — Integration Tests (Submit & Share arc R9)
===================================================================

The living/submit channel end-to-end against a real Neo4j container:

    vault note (with or without fulfills_exercise_uid, status: in process)
        → ONE UserEntry node, upserted in place across edited syncs, from
          its FIRST sync (the door mints a uid), intent stored as a node
          property, NEVER a FULFILLS_EXERCISE edge, never a link
    flip to status: submitted + sync
        → exactly one frozen copy to the note's audience (teachers by
          default): with an exercise, through the turn-in machinery (fresh
          node, FULFILLS_EXERCISE {revision}, Interaction); a feedback
          request routes SUBMITTED_TO_GROUP to the teacher's group; the copy
          records its note (submitted_from_uid) and a fingerprint
    idle re-sync while submitted → no second copy (the fingerprint matches)
    edit while submitted + sync  → a new copy; prior copy intact
    Stop sharing a copy + idle re-sync → nothing re-filed, nothing re-shared

Everything drives through ``ingest_user_entry`` — the same door the vault
sync uses — so the request-building, coercion, and copy-filing behavior
under test is the shipped path, not a test-local reconstruction.

See: docs/roadmap/submission-sharing-arc.md § PR 8; ADR-088.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.collab_backends import GroupBackend
from adapters.persistence.neo4j.backends.exercise_backends import ExerciseBackend
from adapters.persistence.neo4j.backends.misc_backends import InteractionBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.exercises.exercise import Exercise
from core.models.group.group import Group
from core.models.interaction.interaction import Interaction
from core.services.groups.group_service import GroupService
from core.services.ingestion.user_entry_ingestion import ingest_user_entry
from core.services.interaction import InteractionService
from core.services.user_entry.user_entry_service import UserEntryService

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

LIVING_UID = "ue.vault.tasks-list"


@pytest_asyncio.fixture
async def channel_service(
    user_entry_backend, sharing_service, neo4j_driver
) -> AsyncIterator[UserEntryService]:
    """UserEntryService wired like production for the channel: real backend,
    real sharing (the audience writes), real groups (``teachers`` without an
    exercise), real InteractionService (audit record)."""
    interaction_backend = InteractionBackend(
        driver=neo4j_driver,
        label=NeoLabel.INTERACTION,
        entity_class=Interaction,
        base_label=NeoLabel.ENTITY,
    )
    group_backend = GroupBackend(driver=neo4j_driver, label=NeoLabel.GROUP, entity_class=Group)
    yield UserEntryService(
        backend=user_entry_backend,  # type: ignore[arg-type]
        sharing_service=sharing_service,
        interaction_service=InteractionService(backend=interaction_backend),
        group_service=GroupService(backend=group_backend),
    )


def _living_file_data(
    exercise_uid: str | None,
    status: str = "in process",
    content: str = "- task one",
    audience: object = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "pipeline": "knowledge",
        "title": "My task list",
        "uid": "ue.vault.tasks-list",  # authored = stored, verbatim (colon alias deleted 2026-08-14)
        "fulfills_exercise_uid": exercise_uid,
        "status": status,
        "content": content,
        "audience": audience,
    }
    return {k: v for k, v in data.items() if v is not None}


async def _sync(service: UserEntryService, user_uid: str, data: dict[str, Any]):
    return await ingest_user_entry(
        data=data,
        file_path=Path("/vault/knowledge/tasks-list.md"),
        user_uid=user_uid,
        user_entry_service=service,
    )


async def _graph_counts(neo4j_driver, student_uid: str, exercise_uid: str) -> dict[str, Any]:
    """One snapshot of every channel invariant we assert on."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (living:Entity:UserEntry {uid: $living_uid})
            OPTIONAL MATCH (living)-[lf:FULFILLS_EXERCISE]->()
            OPTIONAL MATCH (u:User {uid: $student_uid})-[:OWNS]->(copy:Entity:UserEntry)
                            -[cf:FULFILLS_EXERCISE]->(:Entity {uid: $exercise_uid})
            OPTIONAL MATCH (ia:Entity:Interaction {user_uid: $student_uid})
            RETURN living.status AS living_status,
                   living.content AS living_content,
                   living.fulfills_exercise_uid AS living_intent,
                   count(DISTINCT lf) AS living_edges,
                   count(DISTINCT copy) AS copies,
                   collect(DISTINCT {uid: copy.uid, revision: cf.revision,
                                     status: copy.status, pipeline: copy.pipeline,
                                     content: copy.content}) AS copy_rows,
                   count(DISTINCT ia) AS interactions
            """,
            living_uid=LIVING_UID,
            student_uid=student_uid,
            exercise_uid=exercise_uid,
        )
        record = await result.single()
        assert record is not None
        rows = [r for r in record["copy_rows"] if r["uid"] is not None]
        return {
            "living_status": record["living_status"],
            "living_content": record["living_content"],
            "living_intent": record["living_intent"],
            "living_edges": record["living_edges"],
            "copies": record["copies"],
            "copy_rows": sorted(rows, key=lambda r: r["revision"] or 0),
            "interactions": record["interactions"],
        }


@pytest.mark.asyncio
async def test_living_file_syncs_in_place(
    clean_neo4j, channel_service, neo4j_driver, seed_classroom
) -> None:
    """N edited syncs → ONE node, zero copies, zero edges, intent stored."""
    ctx = await seed_classroom()

    for i in range(3):
        result = await _sync(
            channel_service,
            ctx["student_uid"],
            _living_file_data(ctx["exercise_uid"], content=f"- task edit {i}"),
        )
        assert result.is_ok, result.expect_error()
        assert result.value["uid"] == LIVING_UID
        assert result.value["submitted_copy_uid"] is None

    async with neo4j_driver.session() as session:
        row = await (
            await session.run(
                "MATCH (n:Entity:UserEntry {user_uid: $u}) RETURN count(n) AS n",
                u=ctx["student_uid"],
            )
        ).single()
        assert row["n"] == 1  # ONE living node, no duplicates across syncs

    snap = await _graph_counts(neo4j_driver, ctx["student_uid"], ctx["exercise_uid"])
    assert snap["living_content"] == "- task edit 2"
    assert snap["living_status"] == "active"
    assert snap["living_intent"] == ctx["exercise_uid"]
    assert snap["living_edges"] == 0
    assert snap["copies"] == 0
    assert snap["interactions"] == 0


@pytest.mark.asyncio
async def test_organizes_edges_survive_edited_resync(
    clean_neo4j, channel_service, neo4j_driver, seed_classroom
) -> None:
    """The MOC edge pass keys on the living entry's uid — the uid must stay
    stable across edited re-syncs so ORGANIZES re-draws keep landing on the
    same node (and edges drawn between syncs are not orphaned)."""
    ctx = await seed_classroom()

    result = await _sync(
        channel_service, ctx["student_uid"], _living_file_data(ctx["exercise_uid"])
    )
    assert result.is_ok, result.expect_error()

    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (living:Entity:UserEntry {uid: $living_uid})
            MATCH (ex:Entity {uid: $exercise_uid})
            MERGE (living)-[:ORGANIZES {order: 1}]->(ex)
            """,
            living_uid=LIVING_UID,
            exercise_uid=ctx["exercise_uid"],
        )

    result = await _sync(
        channel_service,
        ctx["student_uid"],
        _living_file_data(ctx["exercise_uid"], content="- edited"),
    )
    assert result.is_ok, result.expect_error()

    async with neo4j_driver.session() as session:
        row = await (
            await session.run(
                """
                MATCH (living:Entity:UserEntry {uid: $living_uid})-[o:ORGANIZES]->()
                RETURN count(o) AS n
                """,
                living_uid=LIVING_UID,
            )
        ).single()
        assert row["n"] == 1  # edge intact on the same, stable uid


@pytest.mark.asyncio
async def test_submit_flip_files_one_frozen_copy(
    clean_neo4j, channel_service, neo4j_driver, seed_classroom
) -> None:
    ctx = await seed_classroom()

    # Work in progress first
    result = await _sync(
        channel_service, ctx["student_uid"], _living_file_data(ctx["exercise_uid"])
    )
    assert result.is_ok, result.expect_error()

    # Flip to submitted
    result = await _sync(
        channel_service,
        ctx["student_uid"],
        _living_file_data(ctx["exercise_uid"], status="submitted"),
    )
    assert result.is_ok, result.expect_error()
    copy_uid = result.value["submitted_copy_uid"]
    assert copy_uid and copy_uid != LIVING_UID

    snap = await _graph_counts(neo4j_driver, ctx["student_uid"], ctx["exercise_uid"])
    # Living entry: untouched channel state — active, no edge, intent kept
    assert snap["living_status"] == "active"
    assert snap["living_edges"] == 0
    assert snap["living_intent"] == ctx["exercise_uid"]
    # Exactly one frozen copy, truthful status, revision 1, edge to exercise
    assert snap["copies"] == 1
    copy = snap["copy_rows"][0]
    assert copy["uid"] == copy_uid
    assert copy["revision"] == 1
    assert copy["status"] == "submitted"
    assert copy["pipeline"] == "teacher_review"
    assert copy["content"] == "- task one"
    # Interaction audit record minted for the turn-in (and only the turn-in)
    assert snap["interactions"] == 1

    # Routed to the teacher's group
    async with neo4j_driver.session() as session:
        row = await (
            await session.run(
                """
                MATCH (copy:Entity:UserEntry {uid: $copy_uid})
                      -[:SUBMITTED_TO_GROUP]->(g:Group {uid: $group_uid})
                RETURN count(g) AS n
                """,
                copy_uid=copy_uid,
                group_uid=ctx["group_uid"],
            )
        ).single()
        assert row["n"] == 1


@pytest.mark.asyncio
async def test_idle_resync_while_submitted_is_noop(
    clean_neo4j, channel_service, neo4j_driver, seed_classroom
) -> None:
    ctx = await seed_classroom()

    submitted = _living_file_data(ctx["exercise_uid"], status="submitted")
    result = await _sync(channel_service, ctx["student_uid"], submitted)
    assert result.is_ok, result.expect_error()
    first_copy_uid = result.value["submitted_copy_uid"]
    assert first_copy_uid

    # Same content, still submitted → no new copy
    for _ in range(2):
        result = await _sync(channel_service, ctx["student_uid"], submitted)
        assert result.is_ok, result.expect_error()
        assert result.value["submitted_copy_uid"] is None

    snap = await _graph_counts(neo4j_driver, ctx["student_uid"], ctx["exercise_uid"])
    assert snap["copies"] == 1
    assert snap["interactions"] == 1


@pytest.mark.asyncio
async def test_edit_while_submitted_is_a_resubmission(
    clean_neo4j, channel_service, neo4j_driver, seed_classroom
) -> None:
    ctx = await seed_classroom()

    result = await _sync(
        channel_service,
        ctx["student_uid"],
        _living_file_data(ctx["exercise_uid"], status="submitted", content="- v1"),
    )
    assert result.is_ok, result.expect_error()
    first_copy_uid = result.value["submitted_copy_uid"]

    result = await _sync(
        channel_service,
        ctx["student_uid"],
        _living_file_data(ctx["exercise_uid"], status="submitted", content="- v2 improved"),
    )
    assert result.is_ok, result.expect_error()
    second_copy_uid = result.value["submitted_copy_uid"]
    assert second_copy_uid and second_copy_uid != first_copy_uid

    snap = await _graph_counts(neo4j_driver, ctx["student_uid"], ctx["exercise_uid"])
    assert snap["copies"] == 2
    assert [r["revision"] for r in snap["copy_rows"]] == [1, 2]
    # The prior copy is never orphaned or mutated — frozen means frozen
    assert snap["copy_rows"][0]["uid"] == first_copy_uid
    assert snap["copy_rows"][0]["content"] == "- v1"
    assert snap["copy_rows"][1]["content"] == "- v2 improved"
    assert snap["interactions"] == 2


@pytest.mark.asyncio
async def test_unreachable_teacher_surfaces_error_and_compensates(
    clean_neo4j, channel_service, neo4j_driver, seed_user, seed_exercise
) -> None:
    """A submitted copy that reaches no teacher/group is deleted and the file
    fails — the living entry stays. (Owner-passes-guard shape: a PERSONAL
    exercise with no group share.)"""
    student = await seed_user("user_ue_loner", name="Loner")
    exercise_uid = await seed_exercise("exercise.ue_personal", group_uid=None)
    async with neo4j_driver.session() as session:
        # Owner passes the use-guard; no group to submit to → no reviewer
        await session.run(
            "MATCH (ex:Entity {uid: $uid}) SET ex.user_uid = $owner",
            uid=exercise_uid,
            owner=student,
        )

    result = await _sync(
        channel_service,
        student,
        _living_file_data(exercise_uid, status="submitted"),
    )
    assert result.is_error
    assert "no teacher" in str(result.expect_error()).lower()

    snap = await _graph_counts(neo4j_driver, student, exercise_uid)
    assert snap["living_status"] == "active"  # living entry persisted
    assert snap["copies"] == 0  # compensated — no unreviewable orphan


async def _copies_of(neo4j_driver, note_uid: str) -> list[dict[str, Any]]:
    """Every frozen copy filed from a note, oldest first, with its links."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (copy:Entity:UserEntry {submitted_from_uid: $note_uid})
            OPTIONAL MATCH (copy)-[:SUBMITTED_TO_GROUP]->(sg:Group)
            OPTIONAL MATCH (reader:User)-[:SHARES_WITH]->(copy)
            RETURN copy.uid AS uid, copy.pipeline AS pipeline, copy.status AS status,
                   copy.submission_fingerprint AS fingerprint,
                   copy.metadata AS metadata, copy.created_at AS created_at,
                   collect(DISTINCT sg.uid) AS submitted_to,
                   collect(DISTINCT reader.uid) AS shared_with
            ORDER BY created_at
            """,
            note_uid=note_uid,
        )
        return [dict(record) async for record in result]


async def _study_in(neo4j_driver, student_uid: str, group_uid: str) -> None:
    """Mark the membership a student one — ``teachers`` without an exercise
    expands to the groups the owner studies in (``MEMBER_OF {role: student}``)."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (:User {uid: $student})-[m:MEMBER_OF]->(:Group {uid: $group})
            SET m.role = 'student'
            """,
            student=student_uid,
            group=group_uid,
        )


async def _links_on(neo4j_driver, entry_uid: str) -> int:
    async with neo4j_driver.session() as session:
        row = await (
            await session.run(
                """
                MATCH (e:Entity:UserEntry {uid: $uid})
                RETURN COUNT { (e)-[:SUBMITTED_TO_GROUP|SHARED_WITH_GROUP]->() }
                     + COUNT { ()-[:SHARES_WITH]->(e) } AS n
                """,
                uid=entry_uid,
            )
        ).single()
        assert row is not None
        return int(row["n"])


@pytest.mark.asyncio
async def test_an_exercise_note_without_a_uid_is_living_from_its_first_sync(
    clean_neo4j, channel_service, neo4j_driver, seed_classroom
) -> None:
    """The first sync is the case the tracker's prior uid never covered: the
    door mints the uid, so the note is a draft — never filed as a turn-in."""
    ctx = await seed_classroom()
    data = _living_file_data(ctx["exercise_uid"])
    del data["uid"]

    result = await _sync(channel_service, ctx["student_uid"], data)
    assert result.is_ok, result.expect_error()
    note_uid = result.value["uid"]

    async with neo4j_driver.session() as session:
        row = await (
            await session.run(
                """
                MATCH (n:Entity:UserEntry {uid: $uid})
                RETURN n.status AS status, n.fulfills_exercise_uid AS intent,
                       n.turn_in_exercise_uid AS snapshot,
                       COUNT { (n)-[:FULFILLS_EXERCISE]->() } AS edges,
                       COUNT { (:Entity:Interaction {user_uid: $student}) } AS interactions
                """,
                uid=note_uid,
                student=ctx["student_uid"],
            )
        ).single()
    assert row is not None
    assert row["status"] == "active"
    assert row["intent"] == ctx["exercise_uid"]
    assert row["snapshot"] is None
    assert row["edges"] == 0
    assert row["interactions"] == 0
    assert await _links_on(neo4j_driver, note_uid) == 0


@pytest.mark.asyncio
async def test_a_note_without_an_exercise_files_one_copy_to_its_teachers(
    clean_neo4j, channel_service, neo4j_driver, seed_classroom
) -> None:
    """R9 with no exercise: ``status: submitted`` files one frozen copy to
    ``teachers`` (every group the student studies in); an idle re-sync files
    nothing; the note itself carries no link."""
    ctx = await seed_classroom()
    await _study_in(neo4j_driver, ctx["student_uid"], ctx["group_uid"])
    submitted = _living_file_data(None, status="submitted")

    result = await _sync(channel_service, ctx["student_uid"], submitted)
    assert result.is_ok, result.expect_error()
    copy_uid = result.value["submitted_copy_uid"]
    assert copy_uid

    for _ in range(2):
        result = await _sync(channel_service, ctx["student_uid"], submitted)
        assert result.is_ok, result.expect_error()
        assert result.value["submitted_copy_uid"] is None

    copies = await _copies_of(neo4j_driver, LIVING_UID)
    assert [c["uid"] for c in copies] == [copy_uid]
    copy = copies[0]
    assert copy["pipeline"] == "teacher_review"
    assert copy["status"] == "submitted"
    assert copy["submitted_to"] == [ctx["group_uid"]]
    assert copy["fingerprint"]
    assert "vault_file_path" not in (copy["metadata"] or "")
    assert await _links_on(neo4j_driver, LIVING_UID) == 0


@pytest.mark.asyncio
async def test_stop_sharing_a_copy_stays_durable_until_the_note_changes(
    clean_neo4j, channel_service, neo4j_driver, seed_classroom, seed_user, seed_membership
) -> None:
    """A share-only copy (``user:`` — pipeline none) reaches its reader; a
    Stop sharing is not read as an audience edit, so an idle re-sync neither
    re-files nor re-shares. A real edit of the audience files a new copy."""
    ctx = await seed_classroom()
    await _study_in(neo4j_driver, ctx["student_uid"], ctx["group_uid"])
    reader = await seed_user("user_ue_reader", name="Reader")
    await seed_membership(reader, ctx["group_uid"])
    async with neo4j_driver.session() as session:
        await session.run("MATCH (u:User {uid: $uid}) SET u.title = 'ue_reader'", uid=reader)
    shared = _living_file_data(None, status="submitted", audience=["user:ue_reader"])

    result = await _sync(channel_service, ctx["student_uid"], shared)
    assert result.is_ok, result.expect_error()
    first = result.value["submitted_copy_uid"]
    copies = await _copies_of(neo4j_driver, LIVING_UID)
    assert copies[0]["pipeline"] == "none"
    assert copies[0]["status"] == "submitted"
    assert copies[0]["shared_with"] == [reader]
    assert copies[0]["submitted_to"] == []

    # Stop sharing (the owner's door deletes the person link)
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (:User {uid: $reader})-[s:SHARES_WITH]->(:Entity {uid: $copy}) DELETE s",
            reader=reader,
            copy=first,
        )

    result = await _sync(channel_service, ctx["student_uid"], shared)
    assert result.is_ok, result.expect_error()
    assert result.value["submitted_copy_uid"] is None
    copies = await _copies_of(neo4j_driver, LIVING_UID)
    assert [c["uid"] for c in copies] == [first]
    assert copies[0]["shared_with"] == []  # the revocation held

    result = await _sync(
        channel_service,
        ctx["student_uid"],
        _living_file_data(None, status="submitted", audience=["teachers", "user:ue_reader"]),
    )
    assert result.is_ok, result.expect_error()
    second = result.value["submitted_copy_uid"]
    assert second and second != first
    copies = await _copies_of(neo4j_driver, LIVING_UID)
    assert copies[1]["pipeline"] == "teacher_review"
    assert copies[1]["submitted_to"] == [ctx["group_uid"]]
    assert copies[1]["shared_with"] == [reader]


# ============================================================================
# PR 2 surfaces — In Progress status rows + emergent-MOC child reads
# ============================================================================


async def _student_status_rows(neo4j_driver, student_uid: str) -> list[dict[str, Any]]:
    """Rows from the chip-feeding backend query (assigned-exercise variant)."""
    backend = ExerciseBackend(
        driver=neo4j_driver,
        label=NeoLabel.EXERCISE,
        entity_class=Exercise,
        base_label=NeoLabel.ENTITY,
    )
    result = await backend.get_student_exercises_with_status(student_uid)
    assert result.is_ok, result.expect_error()
    return [dict(r) for r in (result.value or [])]


async def _mark_assigned(neo4j_driver, exercise_uid: str) -> None:
    """The status query filters on scope='assigned' (seed helper leaves it unset)."""
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (ex:Entity {uid: $uid}) SET ex.scope = 'assigned'",
            uid=exercise_uid,
        )


@pytest.mark.asyncio
async def test_living_intent_surfaces_as_in_progress_row(
    clean_neo4j, channel_service, neo4j_driver, seed_classroom
) -> None:
    """Declared intent (property, no edge) → has_in_progress on the status row
    the exercise chips render from; a turn-in copy then sets has_submission
    while has_in_progress stays truthful (the living entry keeps its intent)."""
    ctx = await seed_classroom()
    await _mark_assigned(neo4j_driver, ctx["exercise_uid"])

    # No entry at all → neither flag
    rows = await _student_status_rows(neo4j_driver, ctx["student_uid"])
    assert len(rows) == 1
    assert rows[0]["has_in_progress"] is False
    assert rows[0]["in_progress_uid"] is None
    assert rows[0]["has_submission"] is False

    # Living sync → In Progress, still no submission
    result = await _sync(
        channel_service, ctx["student_uid"], _living_file_data(ctx["exercise_uid"])
    )
    assert result.is_ok, result.expect_error()

    rows = await _student_status_rows(neo4j_driver, ctx["student_uid"])
    assert rows[0]["has_in_progress"] is True
    assert rows[0]["in_progress_uid"] == LIVING_UID
    assert rows[0]["has_submission"] is False

    # Submit flip → the frozen copy is the submission; the living entry's
    # intent remains and must NOT be counted as a submission (edge-only)
    result = await _sync(
        channel_service,
        ctx["student_uid"],
        _living_file_data(ctx["exercise_uid"], status="submitted"),
    )
    assert result.is_ok, result.expect_error()
    copy_uid = result.value["submitted_copy_uid"]

    rows = await _student_status_rows(neo4j_driver, ctx["student_uid"])
    assert rows[0]["has_submission"] is True
    assert rows[0]["submission_uid"] == copy_uid
    assert rows[0]["has_in_progress"] is True
    assert rows[0]["in_progress_uid"] == LIVING_UID


@pytest.mark.asyncio
async def test_another_users_living_entry_is_invisible(
    clean_neo4j, channel_service, neo4j_driver, seed_classroom, seed_user, seed_membership
) -> None:
    """Ownership scope: student B's status rows never reflect student A's
    living entry against the same assigned exercise."""
    ctx = await seed_classroom()
    await _mark_assigned(neo4j_driver, ctx["exercise_uid"])
    other = await seed_user("user_ue_other", name="Other")
    await seed_membership(other, ctx["group_uid"])

    result = await _sync(
        channel_service, ctx["student_uid"], _living_file_data(ctx["exercise_uid"])
    )
    assert result.is_ok, result.expect_error()

    rows = await _student_status_rows(neo4j_driver, other)
    assert len(rows) == 1
    assert rows[0]["has_in_progress"] is False
    assert rows[0]["in_progress_uid"] is None


@pytest.mark.asyncio
async def test_user_entry_backend_reads_organized_children(
    clean_neo4j, channel_service, user_entry_backend, neo4j_driver, seed_classroom
) -> None:
    """The emergent-MOC read behind /gradebook/{uid}: ORGANIZES children come
    back ordered and typed (entity_type drives per-type detail hrefs)."""
    ctx = await seed_classroom()

    result = await _sync(
        channel_service, ctx["student_uid"], _living_file_data(ctx["exercise_uid"])
    )
    assert result.is_ok, result.expect_error()

    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (living:Entity:UserEntry {uid: $living_uid})
            MERGE (t:Entity:Task {uid: 'tk_moc_child', entity_type: 'task',
                                  title: 'Child task'})
            MERGE (ex:Entity {uid: $exercise_uid})
            MERGE (living)-[:ORGANIZES {order: 1}]->(t)
            MERGE (living)-[:ORGANIZES {order: 0}]->(ex)
            """,
            living_uid=LIVING_UID,
            exercise_uid=ctx["exercise_uid"],
        )

    children_result = await user_entry_backend.get_organized_children(LIVING_UID)
    assert children_result.is_ok, children_result.expect_error()
    children = children_result.value
    assert [c["uid"] for c in children] == [ctx["exercise_uid"], "tk_moc_child"]
    assert children[0]["entity_type"] == "exercise"
    assert children[1]["entity_type"] == "task"
    assert [c["order"] for c in children] == [0, 1]

    # Negative control: a non-MOC entry has no children section to render
    empty_result = await user_entry_backend.get_organized_children("ue_no_such_moc")
    assert empty_result.is_ok
    assert empty_result.value == []
