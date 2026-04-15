"""
Submit → Review Cycle Integration Test — ADR-054 Commit 3
==========================================================

Exercises the full teacher-review submission path on ``UserEntry``:

    student → UserEntryService.create_entry(TEACHER_REVIEW, fulfills_exercise_uid)
              → (:UserEntry) node
              → [:FULFILLS_EXERCISE {revision: 1}] → (:Exercise)
              → [:SHARED_WITH_GROUP] → (:Group)   (auto-share path)
              → entry visible via get_review_queue_by_groups(teacher_uid)

No HTTP layer — the route just forwards into this same service call.
We assert on graph state because that IS the contract ADR-054 locks in.
"""

from __future__ import annotations

import pytest

from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry_request import UserEntryCreateRequest


@pytest.mark.asyncio
async def test_teacher_review_submission_lands_in_review_queue(
    clean_neo4j,
    user_entry_service,
    neo4j_driver,
    seed_classroom,
) -> None:
    ctx = await seed_classroom()

    request = UserEntryCreateRequest(
        title="My first attempt",
        content="Here is my worked solution.",
        pipeline=Pipeline.TEACHER_REVIEW,
        fulfills_exercise_uid=ctx["exercise_uid"],
    )

    create_result = await user_entry_service.create_entry(
        request=request,
        user_uid=ctx["student_uid"],
    )
    assert create_result.is_ok, create_result.expect_error()
    entry = create_result.value
    assert entry.uid.startswith("ue_")

    # Node exists with :Entity:UserEntry labels + user_entry type + pipeline set
    async with neo4j_driver.session() as session:
        row = await (
            await session.run(
                """
                MATCH (u:Entity:UserEntry {uid: $uid})
                RETURN u.entity_type AS entity_type,
                       u.pipeline    AS pipeline,
                       u.status      AS status,
                       u.user_uid    AS user_uid
                """,
                uid=entry.uid,
            )
        ).single()
        assert row is not None, "UserEntry node not persisted"
        assert row["entity_type"] == "user_entry"
        assert row["pipeline"] == Pipeline.TEACHER_REVIEW.value
        assert row["status"] == "submitted"
        assert row["user_uid"] == ctx["student_uid"]

        # FULFILLS_EXERCISE edge carries revision=1 on its first attempt
        fe = await (
            await session.run(
                """
                MATCH (u:UserEntry {uid: $uid})-[r:FULFILLS_EXERCISE]->(ex:Exercise {uid: $ex})
                RETURN r.revision AS revision, count(r) AS cnt
                """,
                uid=entry.uid,
                ex=ctx["exercise_uid"],
            )
        ).single()
        assert fe is not None and fe["cnt"] == 1
        assert fe["revision"] == 1

        # Auto-share fired: SHARED_WITH_GROUP to the exercise's assigned group
        sg = await (
            await session.run(
                """
                MATCH (u:UserEntry {uid: $uid})-[:SHARED_WITH_GROUP]->(g:Group {uid: $g})
                RETURN count(*) AS cnt
                """,
                uid=entry.uid,
                g=ctx["group_uid"],
            )
        ).single()
        assert sg is not None and sg["cnt"] == 1, "auto-share to group did not fire"

    # Teacher review queue picks the entry up
    queue_result = await user_entry_service.get_review_queue(
        teacher_uid=ctx["teacher_uid"],
    )
    assert queue_result.is_ok, queue_result.expect_error()
    queue = queue_result.value or []
    assert any(row["entry_uid"] == entry.uid for row in queue), (
        f"entry {entry.uid} missing from review queue for teacher {ctx['teacher_uid']}: {queue}"
    )
    match = next(row for row in queue if row["entry_uid"] == entry.uid)
    assert match["revision"] == 1
    assert match["exercise_uid"] == ctx["exercise_uid"]
    assert match["group_uid"] == ctx["group_uid"]
