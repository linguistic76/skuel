"""Copy-revision collapse for the teacher review queue.

The vault exercise channel files a frozen COPY of the living entry on every
turn-in (edit-while-submitted → rev 2 with rev 1 still frozen and pending).
The review queue listed every copy as its own item — the #511 walk residue:
a teacher saw rev 1 AND rev 2 of the same student's work as two pieces of
work to do, though reviewing a superseded copy is never useful.

These tests pin the queue (and its dashboard ``pending_count`` twin — the
badge must agree with the queue's length — and the students summary) to
*lineage-newest*: a pending copy is superseded by ANY newer copy in the same
(student, root exercise) lineage — newer by the edge revision, the same
root-lineage lens ``_next_revision`` uses — or, for frozen copies of a vault
note, in the same (student, note) lineage, regardless of the newer copy's
status (a reviewed rev 2 still retires the pending rev 1). Collapse is
per-lineage: another student's copy of the same exercise, and entries in no
lineage at all, must never be swallowed.

The queue query is also THE needs-review rule for the per-student page
(feedback-loop UX arc C2): scoped by ``student_uid`` it feeds the student
page's Needs Review bucket, so the two surfaces read one collapse rule and
can never drift apart — the drift WAS the bug (the per-student query had no
collapse and listed superseded copies the queue correctly dropped).

Run against a real Neo4j: the collapse resolves against persisted
``FULFILLS_EXERCISE {revision}`` edges, which a mocked backend would only
assert were queried, not that they gate.
"""

from __future__ import annotations

import pytest

from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from core.models.type_hints import UserUID
from core.orchestrator.teacher_orchestrator import TeacherOrchestrator
from core.ports.query_types import ReviewQueueItem
from core.services.report.teacher_review_service import TeacherReviewService

TEACHER = "user_qcc_teacher"
OTHER_TEACHER = "user_qcc_other_teacher"
STUDENT_1 = "user_qcc_student_1"
STUDENT_2 = "user_qcc_student_2"
GROUP_UID = "group_qcc"
OTHER_GROUP_UID = "group_qcc_other"
INACTIVE_GROUP_UID = "group_qcc_inactive"  # owned by TEACHER, deactivated

EX_1 = "ex_qcc_one"
EX_2 = "ex_qcc_two"
EX_3 = "ex_qcc_three"

S1_REV1 = "ue_qcc_s1_rev1"  # superseded by S1_REV2 — must NOT queue
S1_REV2 = "ue_qcc_s1_rev2"  # newest TEACHER-REVIEW copy, pending — must queue
S1_AI = "ue_qcc_s1_ai"  # newer PRIVATE llm_summary entry — must not retire S1_REV2
S1_LONE = "ue_qcc_s1_lone"  # no exercise anchor — no lineage, must queue
S2_EX1 = "ue_qcc_s2_ex1"  # other student, same exercise — own lineage, must queue
S2_EX1_OTHER = "ue_qcc_s2_ex1_other"  # rev 2 shared ONLY with the other classroom
S2_EX2_REV1 = "ue_qcc_s2_ex2_rev1"  # superseded by a REVIEWED rev 2 — must NOT queue
S2_EX2_REV2 = "ue_qcc_s2_ex2_rev2"  # completed — not pending, not queued
S1_EX2_REV1 = "ue_qcc_s1_ex2_rev1"  # active-group share, pending — must queue
S1_EX2_REV2 = "ue_qcc_s1_ex2_rev2"  # shared ONLY with the deactivated group
S1_EX3_WAIT = "ue_qcc_s1_ex3_wait"  # revision requested, no resubmit — waiting
S2_EX3_REV1 = "ue_qcc_s2_ex3_rev1"  # revision requested, then resubmitted — history
S2_EX3_REV2 = "ue_qcc_s2_ex3_rev2"  # the resubmit — back in Needs review


@pytest.fixture
def review_service(neo4j_driver) -> TeacherReviewService:
    """Real service over a real user_entry backend.

    Only ``user_entry_backend`` is exercised by the reads under test
    (``get_review_queue``, ``get_dashboard_stats``, ``get_student_submissions``,
    ``verify_teacher_authority``); the other collaborators are never touched,
    so ``None`` is honest here.
    """
    user_entry_backend = UserEntryBackend(driver=neo4j_driver)
    return TeacherReviewService(
        user_entry_backend=user_entry_backend,
        report_backend=None,  # type: ignore[arg-type]
        exercise_backend=None,  # type: ignore[arg-type]
        group_backend=None,  # type: ignore[arg-type]
        ku_interaction_service=None,  # type: ignore[arg-type]
        report_mastery_service=None,  # type: ignore[arg-type]
        event_bus=None,  # type: ignore[arg-type]
    )


@pytest.fixture
async def seeded(clean_neo4j, neo4j_driver) -> None:
    """One classroom, two students, three lineages of frozen copies.

    - STUDENT_1 x EX_1: rev 1 + rev 2 both pending → only rev 2 queues.
      A rev 3 exists too, but it is a PRIVATE llm_summary entry (the upload
      form keeps ``fulfills_exercise_uid`` on every destination, so AI
      entries join the same lineage) — it must not retire the teacher's
      still-unreviewed rev 2.
    - STUDENT_1, no exercise anchor: standalone entry → queues untouched.
    - STUDENT_2 x EX_1: rev 1 pending, shared with TEACHER's group → queues
      (S1's rev 2 on the same exercise is a different lineage and must not
      swallow it). A rev 2 exists but the multi-class student directed it
      ONLY to OTHER_TEACHER's group (``teacher:<group_uid>`` names it) — a
      copy this teacher cannot see must not retire their pending work.
    - STUDENT_2 x EX_2: rev 1 pending, rev 2 already completed → rev 1 is
      superseded by the reviewed copy and must not queue.
    - STUDENT_1 x EX_2: rev 1 pending in the active group; rev 2 shared ONLY
      with a group TEACHER owns but has DEACTIVATED. The queue's visibility
      is active-owned-groups (matching the detail view and review writes),
      so rev 2 neither queues nor supersedes the reviewable rev 1.
    - STUDENT_1 x EX_3: rev 1 revision_requested with no resubmit → the
      waiting-for-resubmit view's sole member; never in Needs review.
    - STUDENT_2 x EX_3: rev 1 revision_requested, rev 2 resubmitted
      (submitted) — the same collapse moves the lineage from Waiting back to
      Needs review: rev 2 queues, rev 1 is history in BOTH views.

    Every exercise-anchored copy carries the turn-in snapshot the writer
    stamps — the lineage key (Submit & Share arc R12); the edges carry the
    revision the rank reads while the exercise exists.
    """
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (t:User {uid: $teacher})
            MERGE (ot:User {uid: $other_teacher})
            MERGE (s1:User {uid: $student_1})
            MERGE (s2:User {uid: $student_2})
            MERGE (g:Group {uid: $group}) SET g.is_active = true
            MERGE (g2:Group {uid: $other_group}) SET g2.is_active = true
            MERGE (g3:Group {uid: $inactive_group}) SET g3.is_active = false
            MERGE (t)-[:OWNS]->(g)
            MERGE (ot)-[:OWNS]->(g2)
            MERGE (t)-[:OWNS]->(g3)
            MERGE (s1)-[:MEMBER_OF]->(g)
            MERGE (s2)-[:MEMBER_OF]->(g)
            MERGE (s2)-[:MEMBER_OF]->(g2)
            CREATE (ex1:Entity:Exercise {
                uid: $ex_1, entity_type: 'exercise', title: 'Exercise one',
                status: 'active', created_at: datetime(), updated_at: datetime()
            })
            CREATE (ex2:Entity:Exercise {
                uid: $ex_2, entity_type: 'exercise', title: 'Exercise two',
                status: 'active', created_at: datetime(), updated_at: datetime()
            })
            CREATE (ex3:Entity:Exercise {
                uid: $ex_3, entity_type: 'exercise', title: 'Exercise three',
                status: 'active', created_at: datetime(), updated_at: datetime()
            })
            CREATE (a1:Entity:UserEntry {
                uid: $s1_rev1, entity_type: 'user_entry', title: 'S1 turn-in',
                status: 'submitted', pipeline: 'teacher_review',
                turn_in_exercise_uid: $ex_1, turn_in_exercise_title: 'Exercise one',
                created_at: datetime() - duration('PT2H'), updated_at: datetime()
            })
            CREATE (a2:Entity:UserEntry {
                uid: $s1_rev2, entity_type: 'user_entry', title: 'S1 turn-in',
                status: 'submitted', pipeline: 'teacher_review',
                turn_in_exercise_uid: $ex_1, turn_in_exercise_title: 'Exercise one',
                created_at: datetime() - duration('PT1H'), updated_at: datetime()
            })
            CREATE (ai:Entity:UserEntry {
                uid: $s1_ai, entity_type: 'user_entry', title: 'S1 AI feedback run',
                status: 'active', pipeline: 'llm_summary',
                turn_in_exercise_uid: $ex_1, turn_in_exercise_title: 'Exercise one',
                created_at: datetime(), updated_at: datetime()
            })
            CREATE (lone:Entity:UserEntry {
                uid: $s1_lone, entity_type: 'user_entry', title: 'S1 standalone',
                status: 'submitted', pipeline: 'teacher_review',
                created_at: datetime(), updated_at: datetime()
            })
            CREATE (b1:Entity:UserEntry {
                uid: $s2_ex1, entity_type: 'user_entry', title: 'S2 turn-in',
                status: 'submitted', pipeline: 'teacher_review',
                turn_in_exercise_uid: $ex_1, turn_in_exercise_title: 'Exercise one',
                created_at: datetime() - duration('PT2H'), updated_at: datetime()
            })
            CREATE (b2:Entity:UserEntry {
                uid: $s2_ex1_other, entity_type: 'user_entry', title: 'S2 turn-in',
                status: 'submitted', pipeline: 'teacher_review',
                turn_in_exercise_uid: $ex_1, turn_in_exercise_title: 'Exercise one',
                created_at: datetime() - duration('PT1H'), updated_at: datetime()
            })
            CREATE (c1:Entity:UserEntry {
                uid: $s2_ex2_rev1, entity_type: 'user_entry', title: 'S2 second exercise',
                status: 'submitted', pipeline: 'teacher_review',
                turn_in_exercise_uid: $ex_2, turn_in_exercise_title: 'Exercise two',
                created_at: datetime() - duration('PT2H'), updated_at: datetime()
            })
            CREATE (c2:Entity:UserEntry {
                uid: $s2_ex2_rev2, entity_type: 'user_entry', title: 'S2 second exercise',
                status: 'completed', pipeline: 'teacher_review',
                turn_in_exercise_uid: $ex_2, turn_in_exercise_title: 'Exercise two',
                created_at: datetime() - duration('PT1H'), updated_at: datetime()
            })
            CREATE (d1:Entity:UserEntry {
                uid: $s1_ex2_rev1, entity_type: 'user_entry', title: 'S1 second exercise',
                status: 'submitted', pipeline: 'teacher_review',
                turn_in_exercise_uid: $ex_2, turn_in_exercise_title: 'Exercise two',
                created_at: datetime() - duration('PT2H'), updated_at: datetime()
            })
            CREATE (d2:Entity:UserEntry {
                uid: $s1_ex2_rev2, entity_type: 'user_entry', title: 'S1 second exercise',
                status: 'submitted', pipeline: 'teacher_review',
                turn_in_exercise_uid: $ex_2, turn_in_exercise_title: 'Exercise two',
                created_at: datetime() - duration('PT1H'), updated_at: datetime()
            })
            CREATE (w1:Entity:UserEntry {
                uid: $s1_ex3_wait, entity_type: 'user_entry', title: 'S1 third exercise',
                status: 'revision_requested', pipeline: 'teacher_review',
                turn_in_exercise_uid: $ex_3, turn_in_exercise_title: 'Exercise three',
                created_at: datetime() - duration('PT2H'), updated_at: datetime()
            })
            CREATE (w2:Entity:UserEntry {
                uid: $s2_ex3_rev1, entity_type: 'user_entry', title: 'S2 third exercise',
                status: 'revision_requested', pipeline: 'teacher_review',
                turn_in_exercise_uid: $ex_3, turn_in_exercise_title: 'Exercise three',
                created_at: datetime() - duration('PT2H'), updated_at: datetime()
            })
            CREATE (w3:Entity:UserEntry {
                uid: $s2_ex3_rev2, entity_type: 'user_entry', title: 'S2 third exercise',
                status: 'submitted', pipeline: 'teacher_review',
                turn_in_exercise_uid: $ex_3, turn_in_exercise_title: 'Exercise three',
                created_at: datetime() - duration('PT1H'), updated_at: datetime()
            })
            MERGE (s1)-[:OWNS]->(a1)
            MERGE (s1)-[:OWNS]->(a2)
            MERGE (s1)-[:OWNS]->(ai)
            MERGE (s1)-[:OWNS]->(lone)
            MERGE (s2)-[:OWNS]->(b1)
            MERGE (s2)-[:OWNS]->(b2)
            MERGE (s2)-[:OWNS]->(c1)
            MERGE (s2)-[:OWNS]->(c2)
            MERGE (s1)-[:OWNS]->(d1)
            MERGE (s1)-[:OWNS]->(d2)
            MERGE (s1)-[:OWNS]->(w1)
            MERGE (s2)-[:OWNS]->(w2)
            MERGE (s2)-[:OWNS]->(w3)
            MERGE (a1)-[:FULFILLS_EXERCISE {revision: 1}]->(ex1)
            MERGE (a2)-[:FULFILLS_EXERCISE {revision: 2}]->(ex1)
            MERGE (ai)-[:FULFILLS_EXERCISE {revision: 3}]->(ex1)
            MERGE (b1)-[:FULFILLS_EXERCISE {revision: 1}]->(ex1)
            MERGE (b2)-[:FULFILLS_EXERCISE {revision: 2}]->(ex1)
            MERGE (c1)-[:FULFILLS_EXERCISE {revision: 1}]->(ex2)
            MERGE (c2)-[:FULFILLS_EXERCISE {revision: 2}]->(ex2)
            MERGE (d1)-[:FULFILLS_EXERCISE {revision: 1}]->(ex2)
            MERGE (d2)-[:FULFILLS_EXERCISE {revision: 2}]->(ex2)
            MERGE (w1)-[:FULFILLS_EXERCISE {revision: 1}]->(ex3)
            MERGE (w2)-[:FULFILLS_EXERCISE {revision: 1}]->(ex3)
            MERGE (w3)-[:FULFILLS_EXERCISE {revision: 2}]->(ex3)
            MERGE (a1)-[:SUBMITTED_TO_GROUP]->(g)
            MERGE (a2)-[:SUBMITTED_TO_GROUP]->(g)
            MERGE (lone)-[:SUBMITTED_TO_GROUP]->(g)
            MERGE (b1)-[:SUBMITTED_TO_GROUP]->(g)
            MERGE (b2)-[:SUBMITTED_TO_GROUP]->(g2)
            MERGE (c1)-[:SUBMITTED_TO_GROUP]->(g)
            MERGE (c2)-[:SUBMITTED_TO_GROUP]->(g)
            MERGE (d1)-[:SUBMITTED_TO_GROUP]->(g)
            MERGE (d2)-[:SUBMITTED_TO_GROUP]->(g3)
            MERGE (w1)-[:SUBMITTED_TO_GROUP]->(g)
            MERGE (w2)-[:SUBMITTED_TO_GROUP]->(g)
            MERGE (w3)-[:SUBMITTED_TO_GROUP]->(g)
            """,
            teacher=TEACHER,
            other_teacher=OTHER_TEACHER,
            student_1=STUDENT_1,
            student_2=STUDENT_2,
            group=GROUP_UID,
            other_group=OTHER_GROUP_UID,
            inactive_group=INACTIVE_GROUP_UID,
            ex_1=EX_1,
            ex_2=EX_2,
            s1_rev1=S1_REV1,
            s1_rev2=S1_REV2,
            s1_ai=S1_AI,
            s1_lone=S1_LONE,
            s2_ex1=S2_EX1,
            s2_ex1_other=S2_EX1_OTHER,
            s2_ex2_rev1=S2_EX2_REV1,
            s2_ex2_rev2=S2_EX2_REV2,
            s1_ex2_rev1=S1_EX2_REV1,
            s1_ex2_rev2=S1_EX2_REV2,
            ex_3=EX_3,
            s1_ex3_wait=S1_EX3_WAIT,
            s2_ex3_rev1=S2_EX3_REV1,
            s2_ex3_rev2=S2_EX3_REV2,
        )


async def _queue_uids(
    review_service: TeacherReviewService,
    student_uid: str | None = None,
    status_filter: str | None = None,
) -> set[str]:
    result = await review_service.get_review_queue(
        TEACHER, status_filter=status_filter, student_uid=student_uid
    )
    assert result.is_ok, f"queue read failed: {result}"
    items: list[ReviewQueueItem] = list(result.value)
    return {item["submission_uid"] for item in items}


async def _waiting_uids(
    review_service: TeacherReviewService, student_uid: str | None = None
) -> set[str]:
    return await _queue_uids(
        review_service, student_uid=student_uid, status_filter="revision_requested"
    )


class TestQueueCopyCollapse:
    """The queue shows each lineage's newest copy, and only that one."""

    async def test_superseded_pending_copy_is_hidden(self, review_service, seeded) -> None:
        uids = await _queue_uids(review_service)
        assert S1_REV2 in uids, "the lineage-newest pending copy must still queue"
        assert S1_REV1 not in uids, (
            "a pending copy with a newer sibling in its lineage is superseded work"
        )

    async def test_copy_superseded_by_reviewed_revision_is_hidden(
        self, review_service, seeded
    ) -> None:
        """Supersession ignores the newer copy's status — reviewed retires pending."""
        uids = await _queue_uids(review_service)
        assert S2_EX2_REV1 not in uids
        assert S2_EX2_REV2 not in uids, "a completed copy is not pending work either"

    async def test_private_ai_entry_never_retires_teacher_work(
        self, review_service, seeded
    ) -> None:
        """Only a teacher-review copy supersedes: a newer PRIVATE llm_summary
        entry in the same lineage is invisible to the teacher, so collapsing
        behind it would remove work with no teacher-visible successor."""
        uids = await _queue_uids(review_service)
        assert S1_REV2 in uids, (
            "the newest teacher-review copy must survive a newer private AI entry"
        )
        assert S1_AI not in uids, "the private AI entry itself is never teacher work"

    async def test_other_classrooms_copy_never_retires_this_teachers_work(
        self, review_service, seeded
    ) -> None:
        """A multi-class student can direct a revision to another teacher's
        group only (``group:<uid>``); a copy this teacher cannot see must
        not supersede the pending copy they can."""
        uids = await _queue_uids(review_service)
        assert S2_EX1 in uids, (
            "the newest copy VISIBLE TO THIS TEACHER must survive a newer copy "
            "shared only with another classroom"
        )
        assert S2_EX1_OTHER not in uids, "the other classroom's copy is not this teacher's work"

    async def test_other_lineages_are_untouched(self, review_service, seeded) -> None:
        """Collapse is per-(student, exercise): neighbors must not be swallowed."""
        uids = await _queue_uids(review_service)
        assert S2_EX1 in uids, "another student's copy of the same exercise is its own lineage"
        assert S1_LONE in uids, "an entry with no exercise anchor has no lineage to collapse"

    async def test_deactivated_classroom_copy_neither_queues_nor_supersedes(
        self, review_service, seeded
    ) -> None:
        """Queue visibility is 'shared with an ACTIVE owned group' — matching
        the detail view and the review writes, which both refuse deactivated
        groups. A copy reachable only through a deactivated group is not
        reviewable work, and it cannot retire the reviewable older copy."""
        uids = await _queue_uids(review_service)
        assert S1_EX2_REV1 in uids, (
            "the pending copy in the ACTIVE classroom must survive a newer copy "
            "locked in a deactivated one"
        )
        assert S1_EX2_REV2 not in uids, (
            "a copy the teacher can neither open nor review is not work to do"
        )

    async def test_queue_is_exactly_the_lineage_newest_set(self, review_service, seeded) -> None:
        assert await _queue_uids(review_service) == {
            S1_REV2,
            S1_LONE,
            S2_EX1,
            S1_EX2_REV1,
            S2_EX3_REV2,
        }


class TestWaitingForResubmitFilter:
    """``status_filter='revision_requested'`` on the SAME query is the waiting set.

    Pins arc-2 C3: no dedicated waiting query exists — the needs-review query
    with the revision_requested status carries the same visibility and the
    same copy-revision collapse, so a resubmit atomically moves the lineage
    from Waiting for resubmit back to Needs review with no state to sync.
    """

    async def test_waiting_is_exactly_the_unresubmitted_revision_requests(
        self, review_service, seeded
    ) -> None:
        assert await _waiting_uids(review_service) == {S1_EX3_WAIT}

    async def test_resubmit_moves_lineage_from_waiting_to_needs_review(
        self, review_service, seeded
    ) -> None:
        """The collapse retires the revision-requested copy the moment a
        teacher-visible resubmit exists — one query, both directions."""
        waiting = await _waiting_uids(review_service)
        needs_review = await _queue_uids(review_service)
        assert S2_EX3_REV1 not in waiting, (
            "a revision-requested copy with a teacher-visible resubmit is no longer waiting"
        )
        assert S2_EX3_REV2 in needs_review, "the resubmit itself is work to review"

    async def test_views_are_disjoint(self, review_service, seeded) -> None:
        assert await _waiting_uids(review_service) & await _queue_uids(review_service) == set(), (
            "no entry may show as both Needs review and Waiting for resubmit"
        )

    async def test_scoped_waiting_partitions_the_unscoped_waiting(
        self, review_service, seeded
    ) -> None:
        s1 = await _waiting_uids(review_service, student_uid=STUDENT_1)
        s2 = await _waiting_uids(review_service, student_uid=STUDENT_2)
        assert s1 == {S1_EX3_WAIT}
        assert s2 == set(), "S2's revision request was resubmitted — nothing waiting"
        assert s1 | s2 == await _waiting_uids(review_service)


class TestDashboardPendingCountAgrees:
    """The dashboard badge counts what the queue shows — not superseded copies."""

    async def test_pending_count_matches_collapsed_queue(self, review_service, seeded) -> None:
        stats = await review_service.get_dashboard_stats(TEACHER)
        assert stats.is_ok, f"dashboard read failed: {stats}"
        assert stats.value["pending_count"] == 5


@pytest.fixture
async def exercise_one_deleted(seeded, neo4j_driver) -> None:
    """EX_1 is gone the way the CRUD delete removes it — with every edge."""
    async with neo4j_driver.session() as session:
        await session.run("MATCH (ex:Entity:Exercise {uid: $ex}) DETACH DELETE ex", ex=EX_1)


class TestCollapseSurvivesExerciseDeletion:
    """The lineage is the snapshot, not the edge (Submit & Share arc R12):
    deleting the exercise removes every FULFILLS_EXERCISE edge and the
    revision numbers on them, and the collapse must not change."""

    async def test_queue_is_unchanged_by_the_deletion(
        self, review_service, exercise_one_deleted
    ) -> None:
        assert await _queue_uids(review_service) == {
            S1_REV2,
            S1_LONE,
            S2_EX1,
            S1_EX2_REV1,
            S2_EX3_REV2,
        }, "rev 1 stays superseded by rev 2 on created_at once the edge revisions are gone"

    async def test_queue_rows_read_the_snapshot(self, review_service, exercise_one_deleted) -> None:
        result = await review_service.get_review_queue(TEACHER)
        assert result.is_ok, f"queue read failed: {result}"
        by_uid = {item["submission_uid"]: item for item in result.value}
        assert by_uid[S1_REV2]["exercise_uid"] == EX_1
        assert by_uid[S1_REV2]["exercise_name"] == "Exercise one"
        assert by_uid[S1_EX2_REV1]["exercise_name"] == "Exercise two", "a live exercise reads live"

    async def test_pending_count_still_agrees(self, review_service, exercise_one_deleted) -> None:
        stats = await review_service.get_dashboard_stats(TEACHER)
        assert stats.is_ok, f"dashboard read failed: {stats}"
        assert stats.value["pending_count"] == 5


class TestStudentScopedQueue:
    """``student_uid`` narrows the queue to one student without changing the rule."""

    async def test_scope_partitions_the_unscoped_queue(self, review_service, seeded) -> None:
        s1_uids = await _queue_uids(review_service, student_uid=STUDENT_1)
        s2_uids = await _queue_uids(review_service, student_uid=STUDENT_2)
        assert s1_uids == {S1_REV2, S1_LONE, S1_EX2_REV1}
        assert s2_uids == {S2_EX1, S2_EX3_REV2}
        assert s1_uids | s2_uids == await _queue_uids(review_service), (
            "the per-student scopes must partition the unscoped queue — "
            "same rule, narrowed, nothing added or lost"
        )

    async def test_superseded_copy_stays_hidden_under_scope(self, review_service, seeded) -> None:
        assert S1_REV1 not in await _queue_uids(review_service, student_uid=STUDENT_1)


class TestStudentPageAgreesWithQueue:
    """The per-student page's buckets ARE the student-scoped queues.

    Pins both directions of the arc's acceptance case: Needs Review is the
    scoped needs-review queue (the superseded rev-1 copy the queue drops
    lands in Completed, never limbo), and Revision Requested is the scoped
    waiting queue (a revision-requested copy whose student resubmitted is
    history too, not still-waiting).
    """

    async def test_needs_review_bucket_equals_scoped_queue(self, review_service, seeded) -> None:
        orchestrator = TeacherOrchestrator(teacher_review_service=review_service)
        result = await orchestrator.get_bucketed_student_submissions(
            teacher_uid=UserUID(TEACHER), student_uid=STUDENT_1
        )
        assert result.is_ok, f"bucketing failed: {result}"
        pending, revision, completed, _name = result.value

        pending_uids = {item["uid"] for item in pending}
        assert pending_uids == await _queue_uids(review_service, student_uid=STUDENT_1)
        assert S1_REV1 not in pending_uids, (
            "the superseded pending copy must never show as Needs Review"
        )
        assert S1_REV1 in {item["uid"] for item in completed}, (
            "a superseded copy is history — it belongs to Completed, not limbo"
        )
        assert {item["uid"] for item in revision} == await _waiting_uids(
            review_service, student_uid=STUDENT_1
        ), "the Revision Requested bucket is the scoped waiting queue — same rule, same collapse"

    async def test_reviewed_lineage_buckets_to_history(self, review_service, seeded) -> None:
        orchestrator = TeacherOrchestrator(teacher_review_service=review_service)
        result = await orchestrator.get_bucketed_student_submissions(
            teacher_uid=UserUID(TEACHER), student_uid=STUDENT_2
        )
        assert result.is_ok, f"bucketing failed: {result}"
        pending, revision, completed, _name = result.value

        assert {item["uid"] for item in pending} == {S2_EX1, S2_EX3_REV2}
        assert revision == [], (
            "S2's revision request was resubmitted — the old copy is not still waiting"
        )
        assert {item["uid"] for item in completed} == {S2_EX2_REV1, S2_EX2_REV2, S2_EX3_REV1}, (
            "retired copies are history: the reviewed rev 1, its reviewer, AND the "
            "resubmitted revision-requested copy"
        )


# =============================================================================
# The note lineage (Submit & Share arc R9): frozen copies of one vault note
# =============================================================================

NOTE_A = "ue.vault.qcc-note-a"
NOTE_B = "ue.vault.qcc-note-b"
S1_NOTE_A_V1 = "ue_qcc_s1_note_a_v1"  # superseded by S1_NOTE_A_V2 — must NOT queue
S1_NOTE_A_V2 = "ue_qcc_s1_note_a_v2"  # the note's newest request — must queue
S1_NOTE_A_SHARE = "ue_qcc_s1_note_a_share"  # a newer share-only copy — supersedes nothing
S1_NOTE_B = "ue_qcc_s1_note_b"  # another note — its own lineage, must queue
S2_NOTE_A = "ue_qcc_s2_note_a"  # another student, same provenance string — must queue


@pytest.fixture
async def seeded_notes(seeded, neo4j_driver) -> None:
    """Exercise-less frozen copies filed from vault notes, beside the lineages above."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (s1:User {uid: $student_1}), (s2:User {uid: $student_2})
            MATCH (g:Group {uid: $group})
            CREATE (a1:Entity:UserEntry {
                uid: $s1_a_v1, entity_type: 'user_entry', title: 'Note A',
                status: 'submitted', pipeline: 'teacher_review', submitted_from_uid: $note_a,
                created_at: datetime() - duration('PT3H'), updated_at: datetime()
            })
            CREATE (a2:Entity:UserEntry {
                uid: $s1_a_v2, entity_type: 'user_entry', title: 'Note A',
                status: 'submitted', pipeline: 'teacher_review', submitted_from_uid: $note_a,
                created_at: datetime() - duration('PT2H'), updated_at: datetime()
            })
            CREATE (a3:Entity:UserEntry {
                uid: $s1_a_share, entity_type: 'user_entry', title: 'Note A',
                status: 'submitted', pipeline: 'none', submitted_from_uid: $note_a,
                created_at: datetime() - duration('PT1H'), updated_at: datetime()
            })
            CREATE (b1:Entity:UserEntry {
                uid: $s1_b, entity_type: 'user_entry', title: 'Note B',
                status: 'submitted', pipeline: 'teacher_review', submitted_from_uid: $note_b,
                created_at: datetime() - duration('PT4H'), updated_at: datetime()
            })
            CREATE (c1:Entity:UserEntry {
                uid: $s2_a, entity_type: 'user_entry', title: 'Note A',
                status: 'submitted', pipeline: 'teacher_review', submitted_from_uid: $note_a,
                created_at: datetime() - duration('PT5H'), updated_at: datetime()
            })
            MERGE (s1)-[:OWNS]->(a1)
            MERGE (s1)-[:OWNS]->(a2)
            MERGE (s1)-[:OWNS]->(a3)
            MERGE (s1)-[:OWNS]->(b1)
            MERGE (s2)-[:OWNS]->(c1)
            MERGE (a1)-[:SUBMITTED_TO_GROUP]->(g)
            MERGE (a2)-[:SUBMITTED_TO_GROUP]->(g)
            MERGE (a3)-[:SHARED_WITH_GROUP]->(g)
            MERGE (b1)-[:SUBMITTED_TO_GROUP]->(g)
            MERGE (c1)-[:SUBMITTED_TO_GROUP]->(g)
            """,
            student_1=STUDENT_1,
            student_2=STUDENT_2,
            group=GROUP_UID,
            note_a=NOTE_A,
            note_b=NOTE_B,
            s1_a_v1=S1_NOTE_A_V1,
            s1_a_v2=S1_NOTE_A_V2,
            s1_a_share=S1_NOTE_A_SHARE,
            s1_b=S1_NOTE_B,
            s2_a=S2_NOTE_A,
        )


class TestNoteLineageCollapse:
    """A newer copy of the same vault note supersedes an older pending one —
    in the queue, its dashboard badge and the students summary alike."""

    async def test_queue_holds_each_notes_newest_request(
        self, review_service, seeded_notes
    ) -> None:
        uids = await _queue_uids(review_service)
        assert S1_NOTE_A_V2 in uids, "the note's newest feedback request must queue"
        assert S1_NOTE_A_V1 not in uids, "an older copy of the same note is superseded"
        assert S1_NOTE_A_SHARE not in uids, "a share-only copy is no feedback request"
        assert S1_NOTE_B in uids, "another note is its own lineage"
        assert S2_NOTE_A in uids, "the lineage is per student — provenance never crosses owners"
        assert uids == {
            S1_REV2,
            S1_LONE,
            S2_EX1,
            S1_EX2_REV1,
            S2_EX3_REV2,
            S1_NOTE_A_V2,
            S1_NOTE_B,
            S2_NOTE_A,
        }

    async def test_pending_count_agrees(self, review_service, seeded_notes) -> None:
        stats = await review_service.get_dashboard_stats(TEACHER)
        assert stats.is_ok, f"dashboard read failed: {stats}"
        assert stats.value["pending_count"] == 8

    async def test_students_summary_reads_the_same_rule(self, review_service, seeded_notes) -> None:
        """Pending there is every not-completed submission the rule leaves
        current: a superseded copy — by exercise or by note — is history."""
        result = await review_service.get_students_summary(TEACHER)
        assert result.is_ok, f"students summary failed: {result}"
        by_student = {row["student_uid"]: row for row in result.value}
        s1 = by_student[STUDENT_1]
        # S1: rev1+rev2, lone, ex2 rev1, ex3 wait, note A v1+v2, note B (ex2 rev2
        # is locked in a deactivated group and never counted).
        assert s1["submission_count"] == 8
        assert s1["reviewed_count"] == 0
        assert s1["pending_count"] == 6  # minus rev1 and note A v1, both superseded
        s2 = by_student[STUDENT_2]
        # S2: ex1, ex2 rev1+rev2, ex3 rev1+rev2, note A (the other-class copy is
        # another teacher's).
        assert s2["submission_count"] == 6
        assert s2["reviewed_count"] == 1
        assert s2["pending_count"] == 3  # ex1, ex3 rev2, note A
