"""
Teacher Review Authorization Integration Tests
==============================================

End-to-end: verify that `UserEntryBackend.verify_teacher_has_group_access`
only returns a match when the teacher and the submission's owner share an
active Group. Commit E of the deferred-security follow-up — closes the
Finding 8 hole where any teacher with a submission UID could submit
reports, request revisions, or approve other teachers' students' work.

Seed layout:
    Teacher A  --OWNS--> Group X  <--MEMBER_OF-- Student 1 (submission_1)
    Teacher B  --OWNS--> Group Y  <--MEMBER_OF-- Student 2 (submission_2)
    Teacher B  --OWNS--> Group Z  (is_active=false)  <--MEMBER_OF-- Student 1

Expectations:
- Teacher A over submission_1 → match (same active group).
- Teacher B over submission_1 → no match (different group; the
  inactive Group Z must not satisfy the `g.is_active = true` predicate).
- Teacher B over submission_2 → match.
- Teacher over their own submission UID → no match (``student.uid <> teacher.uid``).
"""

import pytest

from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend


@pytest.fixture
async def teacher_review_fixture(neo4j_driver):
    """Seed two teachers, two groups, two students, two submissions + one inactive group."""
    teacher_a = "test_trreview_teacher_a"
    teacher_b = "test_trreview_teacher_b"
    student_1 = "test_trreview_student_1"
    student_2 = "test_trreview_student_2"
    group_x = "test_trreview_group_x"
    group_y = "test_trreview_group_y"
    group_z_inactive = "test_trreview_group_z"
    submission_1 = "ue_trreview_s1_submission"
    submission_2 = "ue_trreview_s2_submission"

    await neo4j_driver.execute_query(
        """
        MERGE (ta:User {uid: $teacher_a}) SET ta.name = 'Teacher A', ta.status = 'active'
        MERGE (tb:User {uid: $teacher_b}) SET tb.name = 'Teacher B', tb.status = 'active'
        MERGE (s1:User {uid: $student_1}) SET s1.name = 'Student 1', s1.status = 'active'
        MERGE (s2:User {uid: $student_2}) SET s2.name = 'Student 2', s2.status = 'active'

        MERGE (gx:Group {uid: $group_x})
          SET gx.name = 'Group X', gx.owner_uid = $teacher_a, gx.is_active = true
        MERGE (gy:Group {uid: $group_y})
          SET gy.name = 'Group Y', gy.owner_uid = $teacher_b, gy.is_active = true
        MERGE (gz:Group {uid: $group_z_inactive})
          SET gz.name = 'Group Z (inactive)', gz.owner_uid = $teacher_b, gz.is_active = false

        MERGE (ta)-[:OWNS]->(gx)
        MERGE (tb)-[:OWNS]->(gy)
        MERGE (tb)-[:OWNS]->(gz)
        MERGE (s1)-[:MEMBER_OF {role: 'student'}]->(gx)
        MERGE (s2)-[:MEMBER_OF {role: 'student'}]->(gy)
        MERGE (s1)-[:MEMBER_OF {role: 'student'}]->(gz)

        MERGE (sub1:Entity:UserEntry {uid: $submission_1})
          SET sub1.entity_type = 'user_entry',
              sub1.title = 'S1 submission',
              sub1.status = 'submitted',
              sub1.pipeline = 'teacher_review',
              sub1.user_uid = $student_1
        MERGE (sub2:Entity:UserEntry {uid: $submission_2})
          SET sub2.entity_type = 'user_entry',
              sub2.title = 'S2 submission',
              sub2.status = 'submitted',
              sub2.pipeline = 'teacher_review',
              sub2.user_uid = $student_2

        MERGE (s1)-[:OWNS]->(sub1)
        MERGE (s2)-[:OWNS]->(sub2)
        """,
        teacher_a=teacher_a,
        teacher_b=teacher_b,
        student_1=student_1,
        student_2=student_2,
        group_x=group_x,
        group_y=group_y,
        group_z_inactive=group_z_inactive,
        submission_1=submission_1,
        submission_2=submission_2,
    )

    yield {
        "teacher_a": teacher_a,
        "teacher_b": teacher_b,
        "student_1": student_1,
        "student_2": student_2,
        "group_x": group_x,
        "group_y": group_y,
        "group_z_inactive": group_z_inactive,
        "submission_1": submission_1,
        "submission_2": submission_2,
    }

    await neo4j_driver.execute_query(
        """
        UNWIND $user_uids AS uid MATCH (u:User {uid: uid}) DETACH DELETE u
        """,
        user_uids=[teacher_a, teacher_b, student_1, student_2],
    )
    await neo4j_driver.execute_query(
        """
        UNWIND $group_uids AS uid MATCH (g:Group {uid: uid}) DETACH DELETE g
        """,
        group_uids=[group_x, group_y, group_z_inactive],
    )
    await neo4j_driver.execute_query(
        """
        UNWIND $entity_uids AS uid MATCH (e:Entity {uid: uid}) DETACH DELETE e
        """,
        entity_uids=[submission_1, submission_2],
    )


@pytest.fixture
def user_entry_backend(neo4j_driver):
    return UserEntryBackend(neo4j_driver)


@pytest.mark.asyncio
@pytest.mark.integration
class TestVerifyTeacherHasGroupAccess:
    async def test_teacher_with_shared_active_group_passes(
        self, user_entry_backend, teacher_review_fixture
    ):
        """Teacher A and Student 1 share active Group X → access granted."""
        result = await user_entry_backend.verify_teacher_has_group_access(
            teacher_review_fixture["submission_1"], teacher_review_fixture["teacher_a"]
        )
        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["has_access"] is True

    async def test_teacher_without_shared_group_blocked(
        self, user_entry_backend, teacher_review_fixture
    ):
        """Teacher B has no active shared group with Student 1 → empty result
        (inactive Group Z must not satisfy the is_active predicate)."""
        result = await user_entry_backend.verify_teacher_has_group_access(
            teacher_review_fixture["submission_1"], teacher_review_fixture["teacher_b"]
        )
        assert not result.is_error
        assert result.value == []

    async def test_teacher_blocked_from_own_submission_uid(
        self, user_entry_backend, teacher_review_fixture, neo4j_driver
    ):
        """Even if the teacher's own UID is somehow the submission owner, the
        ``student.uid <> teacher.uid`` predicate must reject — belt-and-braces
        against teachers reviewing their own uploads."""
        teacher_a = teacher_review_fixture["teacher_a"]
        self_owned = "ue_trreview_self_owned"
        await neo4j_driver.execute_query(
            """
            MERGE (ta:User {uid: $teacher_a})
            MERGE (self:Entity:UserEntry {uid: $self_owned})
              SET self.entity_type = 'user_entry',
                  self.pipeline = 'teacher_review',
                  self.status = 'submitted'
            MERGE (ta)-[:OWNS]->(self)
            """,
            teacher_a=teacher_a,
            self_owned=self_owned,
        )
        try:
            result = await user_entry_backend.verify_teacher_has_group_access(self_owned, teacher_a)
            assert not result.is_error
            assert result.value == []
        finally:
            await neo4j_driver.execute_query(
                "MATCH (e:Entity {uid: $uid}) DETACH DELETE e", uid=self_owned
            )

    async def test_each_teacher_only_sees_own_group_members(
        self, user_entry_backend, teacher_review_fixture
    ):
        """Teacher B over Student 2 passes; Teacher A over Student 2 does not."""
        b_over_s2 = await user_entry_backend.verify_teacher_has_group_access(
            teacher_review_fixture["submission_2"], teacher_review_fixture["teacher_b"]
        )
        a_over_s2 = await user_entry_backend.verify_teacher_has_group_access(
            teacher_review_fixture["submission_2"], teacher_review_fixture["teacher_a"]
        )
        assert not b_over_s2.is_error
        assert len(b_over_s2.value) == 1
        assert not a_over_s2.is_error
        assert a_over_s2.value == []
