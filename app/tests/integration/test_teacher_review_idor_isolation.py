"""
Teacher Review IDOR Isolation Integration Tests
================================================

End-to-end: verify that the four teacher-review backend reads are scoped
to the teacher's classroom and do not leak across teachers.

This closes the IDOR class where backend methods accepted ``teacher_uid``
but never filtered on it — observation #3 from the PR #98 review.

Seed layout (two unrelated classrooms):
    Teacher A --OWNS--> Group X (active) <--MEMBER_OF-- Student 1
                          ^
                          |--SHARED_WITH_GROUP-- submission_1 (Student 1)
    Teacher B --OWNS--> Group Y (active) <--MEMBER_OF-- Student 2
                          ^
                          |--SHARED_WITH_GROUP-- submission_2 (Student 2)

Each method asserted against:
- Teacher A reading their own classroom → sees data.
- Teacher B reading Teacher A's submission/student/queue → sees nothing.
- ``get_dashboard_stats`` for Teacher B → zero ``pending_count`` /
  ``total_students`` even when classroom A has both.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend


@pytest.fixture
async def two_classroom_fixture(neo4j_driver):
    """Seed two unrelated teacher classrooms, each with one shared submission."""
    teacher_a = "test_idor_teacher_a"
    teacher_b = "test_idor_teacher_b"
    student_1 = "test_idor_student_1"
    student_2 = "test_idor_student_2"
    group_x = "test_idor_group_x"
    group_y = "test_idor_group_y"
    submission_1 = "ue_idor_s1"
    submission_2 = "ue_idor_s2"
    now = datetime.now().isoformat()

    await neo4j_driver.execute_query(
        """
        MERGE (ta:User {uid: $teacher_a}) SET ta.name = 'Teacher A', ta.status = 'active'
        MERGE (tb:User {uid: $teacher_b}) SET tb.name = 'Teacher B', tb.status = 'active'
        MERGE (s1:User {uid: $student_1}) SET s1.name = 'Student 1', s1.status = 'active'
        MERGE (s2:User {uid: $student_2}) SET s2.name = 'Student 2', s2.status = 'active'

        MERGE (gx:Group {uid: $group_x})
          SET gx.name = 'Group X', gx.is_active = true
        MERGE (gy:Group {uid: $group_y})
          SET gy.name = 'Group Y', gy.is_active = true

        MERGE (ta)-[:OWNS]->(gx)
        MERGE (tb)-[:OWNS]->(gy)
        MERGE (s1)-[:MEMBER_OF {role: 'student'}]->(gx)
        MERGE (s2)-[:MEMBER_OF {role: 'student'}]->(gy)

        MERGE (sub1:Entity:UserEntry {uid: $submission_1})
          SET sub1.entity_type = 'user_entry',
              sub1.title = 'S1 submission',
              sub1.status = 'submitted',
              sub1.pipeline = 'teacher_review',
              sub1.created_at = datetime($now),
              sub1.user_uid = $student_1
        MERGE (sub2:Entity:UserEntry {uid: $submission_2})
          SET sub2.entity_type = 'user_entry',
              sub2.title = 'S2 submission',
              sub2.status = 'submitted',
              sub2.pipeline = 'teacher_review',
              sub2.created_at = datetime($now),
              sub2.user_uid = $student_2

        MERGE (s1)-[:OWNS]->(sub1)
        MERGE (s2)-[:OWNS]->(sub2)

        MERGE (sub1)-[:SHARED_WITH_GROUP]->(gx)
        MERGE (sub2)-[:SHARED_WITH_GROUP]->(gy)
        """,
        teacher_a=teacher_a,
        teacher_b=teacher_b,
        student_1=student_1,
        student_2=student_2,
        group_x=group_x,
        group_y=group_y,
        submission_1=submission_1,
        submission_2=submission_2,
        now=now,
    )

    yield {
        "teacher_a": teacher_a,
        "teacher_b": teacher_b,
        "student_1": student_1,
        "student_2": student_2,
        "group_x": group_x,
        "group_y": group_y,
        "submission_1": submission_1,
        "submission_2": submission_2,
    }

    await neo4j_driver.execute_query(
        "UNWIND $uids AS uid MATCH (u:User {uid: uid}) DETACH DELETE u",
        uids=[teacher_a, teacher_b, student_1, student_2],
    )
    await neo4j_driver.execute_query(
        "UNWIND $uids AS uid MATCH (g:Group {uid: uid}) DETACH DELETE g",
        uids=[group_x, group_y],
    )
    await neo4j_driver.execute_query(
        "UNWIND $uids AS uid MATCH (e:Entity {uid: uid}) DETACH DELETE e",
        uids=[submission_1, submission_2],
    )


@pytest.fixture
def backend(neo4j_driver):
    return UserEntryBackend(neo4j_driver)


@pytest.mark.asyncio
@pytest.mark.integration
class TestStudentEntriesIsolation:
    """``get_student_entries_for_teacher`` — Model A (shared active group)."""

    async def test_own_classroom_returns_entries(self, backend, two_classroom_fixture):
        result = await backend.get_student_entries_for_teacher(
            two_classroom_fixture["teacher_a"], two_classroom_fixture["student_1"]
        )
        assert not result.is_error
        uids = {row["uid"] for row in result.value}
        assert two_classroom_fixture["submission_1"] in uids

    async def test_cross_classroom_returns_empty(self, backend, two_classroom_fixture):
        """Teacher B has no shared active group with Student 1 → empty."""
        result = await backend.get_student_entries_for_teacher(
            two_classroom_fixture["teacher_b"], two_classroom_fixture["student_1"]
        )
        assert not result.is_error
        assert result.value == []


@pytest.mark.asyncio
@pytest.mark.integration
class TestEntryDetailIsolation:
    """``get_entry_detail_for_teacher`` — Model B (SHARED_WITH_GROUP)."""

    async def test_own_classroom_returns_detail(self, backend, two_classroom_fixture):
        result = await backend.get_entry_detail_for_teacher(
            two_classroom_fixture["submission_1"], two_classroom_fixture["teacher_a"]
        )
        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["uid"] == two_classroom_fixture["submission_1"]

    async def test_cross_classroom_returns_empty(self, backend, two_classroom_fixture):
        """Teacher B owns no group that submission_1 is SHARED_WITH_GROUP → empty.

        Service layer maps empty → 404 (Errors.not_found), so probing across
        classrooms cannot confirm the entry's existence.
        """
        result = await backend.get_entry_detail_for_teacher(
            two_classroom_fixture["submission_1"], two_classroom_fixture["teacher_b"]
        )
        assert not result.is_error
        assert result.value == []

    async def test_inactive_group_does_not_unlock_detail(
        self, backend, two_classroom_fixture, neo4j_driver
    ):
        """An inactive group cannot satisfy the gate, even if Teacher B owns it
        and submission_1 is SHARED_WITH_GROUP to it."""
        teacher_b = two_classroom_fixture["teacher_b"]
        inactive_group = "test_idor_group_z_inactive"
        try:
            await neo4j_driver.execute_query(
                """
                MERGE (gz:Group {uid: $g}) SET gz.is_active = false, gz.name = 'Z'
                WITH gz
                MATCH (tb:User {uid: $tb}) MERGE (tb)-[:OWNS]->(gz)
                WITH gz
                MATCH (sub:Entity {uid: $sub}) MERGE (sub)-[:SHARED_WITH_GROUP]->(gz)
                """,
                g=inactive_group,
                tb=teacher_b,
                sub=two_classroom_fixture["submission_1"],
            )
            result = await backend.get_entry_detail_for_teacher(
                two_classroom_fixture["submission_1"], teacher_b
            )
            assert not result.is_error
            assert result.value == []
        finally:
            await neo4j_driver.execute_query(
                "MATCH (g:Group {uid: $g}) DETACH DELETE g", g=inactive_group
            )


@pytest.mark.asyncio
@pytest.mark.integration
class TestDashboardStatsIsolation:
    """``get_dashboard_stats`` — Model B on pending_count + total_students."""

    async def test_own_classroom_sees_pending_and_students(self, backend, two_classroom_fixture):
        result = await backend.get_dashboard_stats(two_classroom_fixture["teacher_a"])
        assert not result.is_error
        record = result.value[0]
        assert record["pending_count"] >= 1
        assert record["total_students"] >= 1
        assert record["total_groups"] >= 1

    async def test_cross_classroom_sees_zero_pending_and_students(
        self, backend, two_classroom_fixture, neo4j_driver
    ):
        """Teacher B owns Group Y but submission_2 is shared with Y; we need a
        teacher with NO shared submissions to assert the zero case cleanly.

        We use a fresh teacher with their own empty group — total_groups=1,
        total_exercises=0, pending_count=0, total_students=0.
        """
        empty_teacher = "test_idor_teacher_empty"
        empty_group = "test_idor_group_empty"
        try:
            await neo4j_driver.execute_query(
                """
                MERGE (t:User {uid: $t}) SET t.status = 'active', t.name = 'Empty'
                MERGE (g:Group {uid: $g}) SET g.is_active = true, g.name = 'Empty'
                MERGE (t)-[:OWNS]->(g)
                """,
                t=empty_teacher,
                g=empty_group,
            )
            result = await backend.get_dashboard_stats(empty_teacher)
            assert not result.is_error
            record = result.value[0]
            assert record["pending_count"] == 0
            assert record["total_students"] == 0
        finally:
            await neo4j_driver.execute_query(
                "MATCH (u:User {uid: $t}) DETACH DELETE u", t=empty_teacher
            )
            await neo4j_driver.execute_query(
                "MATCH (g:Group {uid: $g}) DETACH DELETE g", g=empty_group
            )


@pytest.mark.asyncio
@pytest.mark.integration
class TestReviewQueueIsolation:
    """``get_review_queue_by_groups`` — already gated; regression for the
    rewire from the deleted ``get_review_queue`` that wasn't gated."""

    async def test_own_classroom_sees_only_own_entries(self, backend, two_classroom_fixture):
        queue_a = await backend.get_review_queue_by_groups(two_classroom_fixture["teacher_a"])
        assert not queue_a.is_error
        uids = {row["entry_uid"] for row in queue_a.value}
        assert two_classroom_fixture["submission_1"] in uids
        assert two_classroom_fixture["submission_2"] not in uids

    async def test_cross_classroom_disjoint(self, backend, two_classroom_fixture):
        queue_b = await backend.get_review_queue_by_groups(two_classroom_fixture["teacher_b"])
        assert not queue_b.is_error
        uids = {row["entry_uid"] for row in queue_b.value}
        assert two_classroom_fixture["submission_2"] in uids
        assert two_classroom_fixture["submission_1"] not in uids
