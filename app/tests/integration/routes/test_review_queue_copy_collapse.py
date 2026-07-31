"""Copy-revision collapse for the teacher review queue.

The vault exercise channel files a frozen COPY of the living entry on every
turn-in (edit-while-submitted → rev 2 with rev 1 still frozen and pending).
The review queue listed every copy as its own item — the #511 walk residue:
a teacher saw rev 1 AND rev 2 of the same student's work as two pieces of
work to do, though reviewing a superseded copy is never useful.

These tests pin the queue (and its dashboard ``pending_count`` twin — the
badge must agree with the queue's length) to *lineage-newest*: a pending
copy is superseded by ANY newer copy in the same (student, root exercise)
lineage — newer by the edge revision, the same root-lineage lens
``get_latest_entry_for_exercise`` / ``_next_revision`` use — regardless of
the newer copy's status (a reviewed rev 2 still retires the pending rev 1).
Collapse is per-lineage: another student's copy of the same exercise, and
entries with no exercise anchor at all, must never be swallowed.

Run against a real Neo4j: the collapse resolves against persisted
``FULFILLS_EXERCISE {revision}`` edges, which a mocked backend would only
assert were queried, not that they gate.
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from core.services.report.teacher_review_service import TeacherReviewService

TEACHER = "user_qcc_teacher"
STUDENT_1 = "user_qcc_student_1"
STUDENT_2 = "user_qcc_student_2"
GROUP_UID = "group_qcc"

EX_1 = "ex_qcc_one"
EX_2 = "ex_qcc_two"

S1_REV1 = "ue_qcc_s1_rev1"  # superseded by S1_REV2 — must NOT queue
S1_REV2 = "ue_qcc_s1_rev2"  # lineage-newest, pending — must queue
S1_LONE = "ue_qcc_s1_lone"  # no exercise anchor — no lineage, must queue
S2_EX1 = "ue_qcc_s2_ex1"  # other student, same exercise — own lineage, must queue
S2_EX2_REV1 = "ue_qcc_s2_ex2_rev1"  # superseded by a REVIEWED rev 2 — must NOT queue
S2_EX2_REV2 = "ue_qcc_s2_ex2_rev2"  # completed — not pending, not queued


@pytest.fixture
def review_service(neo4j_driver) -> TeacherReviewService:
    """Real service over a real user_entry backend.

    Only ``user_entry_backend`` is exercised by the reads under test
    (``get_review_queue``, ``get_dashboard_stats``); the other collaborators
    are never touched, so ``None`` is honest here.
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
    - STUDENT_1, no exercise anchor: standalone entry → queues untouched.
    - STUDENT_2 x EX_1: rev 1 pending → queues (S1's rev 2 on the same
      exercise is a different lineage and must not swallow it).
    - STUDENT_2 x EX_2: rev 1 pending, rev 2 already completed → rev 1 is
      superseded by the reviewed copy and must not queue.
    """
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (t:User {uid: $teacher})
            MERGE (s1:User {uid: $student_1})
            MERGE (s2:User {uid: $student_2})
            MERGE (g:Group {uid: $group}) SET g.is_active = true
            MERGE (t)-[:OWNS]->(g)
            MERGE (s1)-[:MEMBER_OF]->(g)
            MERGE (s2)-[:MEMBER_OF]->(g)
            CREATE (ex1:Entity:Exercise {
                uid: $ex_1, entity_type: 'exercise', title: 'Exercise one',
                status: 'active', created_at: datetime(), updated_at: datetime()
            })
            CREATE (ex2:Entity:Exercise {
                uid: $ex_2, entity_type: 'exercise', title: 'Exercise two',
                status: 'active', created_at: datetime(), updated_at: datetime()
            })
            CREATE (a1:Entity:UserEntry {
                uid: $s1_rev1, entity_type: 'user_entry', title: 'S1 turn-in',
                status: 'submitted', pipeline: 'teacher_review',
                created_at: datetime() - duration('PT2H'), updated_at: datetime()
            })
            CREATE (a2:Entity:UserEntry {
                uid: $s1_rev2, entity_type: 'user_entry', title: 'S1 turn-in',
                status: 'submitted', pipeline: 'teacher_review',
                created_at: datetime() - duration('PT1H'), updated_at: datetime()
            })
            CREATE (lone:Entity:UserEntry {
                uid: $s1_lone, entity_type: 'user_entry', title: 'S1 standalone',
                status: 'submitted', pipeline: 'teacher_review',
                created_at: datetime(), updated_at: datetime()
            })
            CREATE (b1:Entity:UserEntry {
                uid: $s2_ex1, entity_type: 'user_entry', title: 'S2 turn-in',
                status: 'submitted', pipeline: 'teacher_review',
                created_at: datetime(), updated_at: datetime()
            })
            CREATE (c1:Entity:UserEntry {
                uid: $s2_ex2_rev1, entity_type: 'user_entry', title: 'S2 second exercise',
                status: 'submitted', pipeline: 'teacher_review',
                created_at: datetime() - duration('PT2H'), updated_at: datetime()
            })
            CREATE (c2:Entity:UserEntry {
                uid: $s2_ex2_rev2, entity_type: 'user_entry', title: 'S2 second exercise',
                status: 'completed', pipeline: 'teacher_review',
                created_at: datetime() - duration('PT1H'), updated_at: datetime()
            })
            MERGE (s1)-[:OWNS]->(a1)
            MERGE (s1)-[:OWNS]->(a2)
            MERGE (s1)-[:OWNS]->(lone)
            MERGE (s2)-[:OWNS]->(b1)
            MERGE (s2)-[:OWNS]->(c1)
            MERGE (s2)-[:OWNS]->(c2)
            MERGE (a1)-[:FULFILLS_EXERCISE {revision: 1}]->(ex1)
            MERGE (a2)-[:FULFILLS_EXERCISE {revision: 2}]->(ex1)
            MERGE (b1)-[:FULFILLS_EXERCISE {revision: 1}]->(ex1)
            MERGE (c1)-[:FULFILLS_EXERCISE {revision: 1}]->(ex2)
            MERGE (c2)-[:FULFILLS_EXERCISE {revision: 2}]->(ex2)
            MERGE (a1)-[:SHARED_WITH_GROUP]->(g)
            MERGE (a2)-[:SHARED_WITH_GROUP]->(g)
            MERGE (lone)-[:SHARED_WITH_GROUP]->(g)
            MERGE (b1)-[:SHARED_WITH_GROUP]->(g)
            MERGE (c1)-[:SHARED_WITH_GROUP]->(g)
            MERGE (c2)-[:SHARED_WITH_GROUP]->(g)
            """,
            teacher=TEACHER,
            student_1=STUDENT_1,
            student_2=STUDENT_2,
            group=GROUP_UID,
            ex_1=EX_1,
            ex_2=EX_2,
            s1_rev1=S1_REV1,
            s1_rev2=S1_REV2,
            s1_lone=S1_LONE,
            s2_ex1=S2_EX1,
            s2_ex2_rev1=S2_EX2_REV1,
            s2_ex2_rev2=S2_EX2_REV2,
        )


async def _queue_uids(review_service: TeacherReviewService) -> set[str]:
    result = await review_service.get_review_queue(TEACHER)
    assert result.is_ok, f"queue read failed: {result}"
    items: list[dict[str, Any]] = list(result.value)
    return {item["submission_uid"] for item in items}


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

    async def test_other_lineages_are_untouched(self, review_service, seeded) -> None:
        """Collapse is per-(student, exercise): neighbors must not be swallowed."""
        uids = await _queue_uids(review_service)
        assert S2_EX1 in uids, "another student's copy of the same exercise is its own lineage"
        assert S1_LONE in uids, "an entry with no exercise anchor has no lineage to collapse"

    async def test_queue_is_exactly_the_lineage_newest_set(self, review_service, seeded) -> None:
        assert await _queue_uids(review_service) == {S1_REV2, S1_LONE, S2_EX1}


class TestDashboardPendingCountAgrees:
    """The dashboard badge counts what the queue shows — not superseded copies."""

    async def test_pending_count_matches_collapsed_queue(self, review_service, seeded) -> None:
        stats = await review_service.get_dashboard_stats(TEACHER)
        assert stats.is_ok, f"dashboard read failed: {stats}"
        assert stats.value["pending_count"] == 3
