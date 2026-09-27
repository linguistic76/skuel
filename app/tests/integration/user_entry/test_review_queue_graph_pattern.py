"""
Review-queue isolation by group — ADR-054 Commit 3
===================================================

The review queue pattern uses ``SUBMITTED_TO_GROUP`` — the feedback request,
ADR-088 §2 — as the single source of truth for teacher access (no role-gated
Cypher). This test wires up two unrelated classrooms and asserts that each
teacher's queue sees only the entries submitted to groups *they* own, and
that non-``teacher_review`` pipelines never surface regardless of audience.
"""

from __future__ import annotations

import pytest

from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry_request import UserEntryCreateRequest


@pytest.mark.asyncio
async def test_review_queue_isolates_by_group_ownership(
    clean_neo4j,
    user_entry_service,
    user_entry_backend,
    seed_classroom,
    seed_user,
    seed_group,
    seed_membership,
    seed_exercise,
) -> None:
    # Classroom A — full seeded classroom helper
    ctx_a = await seed_classroom(
        teacher_uid="user_teacher_a",
        student_uid="user_student_a",
        group_uid="group.a",
        exercise_uid="exercise.a",
    )

    # Classroom B — disjoint teacher + group + exercise, shared student identity
    teacher_b = await seed_user("user_teacher_b", name="Teacher B")
    student_b = await seed_user("user_student_b", name="Student B")
    group_b = await seed_group("group.b", teacher_b)
    await seed_membership(student_b, group_b)
    exercise_b = await seed_exercise("exercise.b", group_uid=group_b)

    # --- Submissions ---
    # 1. Student A → classroom A (teacher_review) — should land in A's queue only
    r1 = await user_entry_service.create_entry(
        request=UserEntryCreateRequest(
            title="A1",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid=ctx_a["exercise_uid"],
        ),
        user_uid=ctx_a["student_uid"],
    )
    assert r1.is_ok, r1.expect_error()

    # 2. Student B → classroom B (teacher_review) — should land in B's queue only
    r2 = await user_entry_service.create_entry(
        request=UserEntryCreateRequest(
            title="B1",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid=exercise_b,
        ),
        user_uid=student_b,
    )
    assert r2.is_ok, r2.expect_error()

    # 3. Student A → classroom A (Pipeline.NONE) — never in either queue
    r3 = await user_entry_service.create_entry(
        request=UserEntryCreateRequest(
            title="Private note (no pipeline)",
            pipeline=Pipeline.NONE,
        ),
        user_uid=ctx_a["student_uid"],
    )
    assert r3.is_ok, r3.expect_error()

    # --- Queue assertions ---
    queue_a = (
        await user_entry_backend.get_review_queue_by_groups(ctx_a["teacher_uid"])
    ).value or []
    queue_b = (await user_entry_backend.get_review_queue_by_groups(teacher_b)).value or []

    uids_a = {row["entry_uid"] for row in queue_a}
    uids_b = {row["entry_uid"] for row in queue_b}

    r1_uid = r1.value[0].uid
    r2_uid = r2.value[0].uid
    r3_uid = r3.value[0].uid

    assert r1_uid in uids_a
    assert r2_uid not in uids_a
    assert r3_uid not in uids_a

    assert r2_uid in uids_b
    assert r1_uid not in uids_b
    assert r3_uid not in uids_b


@pytest.mark.asyncio
async def test_a_request_to_two_classes_of_one_teacher_lists_once(
    clean_neo4j,
    user_entry_service,
    user_entry_backend,
    neo4j_driver,
    seed_user,
    seed_group,
    seed_membership,
    seed_exercise,
) -> None:
    """An exercise assigned to two of a teacher's classes, answered by a
    student in both: ``teachers`` files one ``SUBMITTED_TO_GROUP`` per class,
    and the teacher's queue and detail read still see one feedback request."""
    teacher = await seed_user("user_teacher_two_classes", name="Teacher")
    student = await seed_user("user_student_two_classes", name="Student")
    class_1 = await seed_group("group.two-classes-1", teacher)
    class_2 = await seed_group("group.two-classes-2", teacher)
    await seed_membership(student, class_1)
    await seed_membership(student, class_2)
    exercise = await seed_exercise("exercise.two-classes", group_uid=class_1)
    await seed_exercise("exercise.two-classes", group_uid=class_2)

    created = await user_entry_service.create_entry(
        request=UserEntryCreateRequest(
            title="Two classes",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid=exercise,
        ),
        user_uid=student,
    )
    assert created.is_ok, created.expect_error()
    entry_uid = created.value[0].uid

    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (:UserEntry {uid: $uid})-[r:SUBMITTED_TO_GROUP]->(g:Group) "
            "RETURN collect(g.uid) AS groups",
            uid=entry_uid,
        )
        record = await result.single()
    # Precondition: the request really asks both classes.
    assert record is not None and sorted(record["groups"]) == sorted([class_1, class_2])

    queue = (await user_entry_backend.get_review_queue_by_groups(teacher)).value or []
    assert [row["entry_uid"] for row in queue] == [entry_uid]

    detail = (await user_entry_backend.get_entry_detail_for_teacher(entry_uid, teacher)).value
    assert detail is not None and len(detail) == 1
