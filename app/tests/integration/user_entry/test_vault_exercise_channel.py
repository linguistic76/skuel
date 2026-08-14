"""
Vault Exercise Channel Integration Tests — PR 1 (channel mechanics)
====================================================================

The living/submit channel end-to-end against a real Neo4j container:

    living file (deterministic uid + fulfills_exercise_uid + status: in process)
        → ONE UserEntry node, upserted in place across edited syncs,
          intent stored as a node property, NEVER a FULFILLS_EXERCISE edge
    flip to status: submitted + sync
        → exactly one frozen copy through the existing turn-in machinery
          (fresh node, FULFILLS_EXERCISE {revision}, Interaction,
          SHARED_WITH_GROUP routing to the teacher's group)
    idle re-sync while submitted → no second copy (content unchanged)
    edit while submitted + sync  → revision-2 copy; prior copy intact

Everything drives through ``ingest_user_entry`` — the same door the vault
sync uses — so the request-building, coercion, and copy-filing behavior
under test is the shipped path, not a test-local reconstruction.

See: docs/roadmap/done/moc-knowledge-channel-design-notes.md § Phase 0 rulings (R2, R3).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.exercise_backends import ExerciseBackend
from adapters.persistence.neo4j.backends.misc_backends import InteractionBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.exercises.exercise import Exercise
from core.models.interaction.interaction import Interaction
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
    real sharing (auto-share fan-out), real InteractionService (audit record)."""
    interaction_backend = InteractionBackend(
        driver=neo4j_driver,
        label=NeoLabel.INTERACTION,
        entity_class=Interaction,
        base_label=NeoLabel.ENTITY,
    )
    yield UserEntryService(
        backend=user_entry_backend,  # type: ignore[arg-type]
        sharing_service=sharing_service,
        interaction_service=InteractionService(backend=interaction_backend),
    )


def _living_file_data(
    exercise_uid: str,
    status: str = "in process",
    content: str = "- task one",
) -> dict[str, Any]:
    return {
        "pipeline": "knowledge",
        "title": "My task list",
        "uid": "ue.vault.tasks-list",  # authored = stored, verbatim (colon alias deleted 2026-08-14)
        "fulfills_exercise_uid": exercise_uid,
        "status": status,
        "content": content,
        "audience": "private",
    }


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
                      -[:SHARED_WITH_GROUP]->(g:Group {uid: $group_uid})
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
        # Owner passes the use-guard; no SHARED_WITH_GROUP → no reviewer
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
