"""
Revision-on-edge Integration Test — ADR-054 Commit 3
=====================================================

ADR-054 moves ``revision_number`` off the node and onto the
``FULFILLS_EXERCISE`` edge. A second attempt against the same exercise
produces a brand-new ``:UserEntry`` node with a brand-new edge carrying
``revision = 2`` — the first entry's edge still carries ``revision = 1``
and its node is unchanged.
"""

from __future__ import annotations

import pytest

from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry_request import UserEntryCreateRequest


@pytest.mark.asyncio
async def test_second_attempt_creates_new_entry_with_revision_two(
    clean_neo4j,
    user_entry_service,
    neo4j_driver,
    seed_classroom,
) -> None:
    ctx = await seed_classroom()

    first = await user_entry_service.create_entry(
        request=UserEntryCreateRequest(
            title="Attempt #1",
            content="initial answer",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid=ctx["exercise_uid"],
        ),
        user_uid=ctx["student_uid"],
    )
    assert first.is_ok, first.expect_error()
    first_uid = first.value.uid

    second = await user_entry_service.create_entry(
        request=UserEntryCreateRequest(
            title="Attempt #2",
            content="revised answer",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid=ctx["exercise_uid"],
        ),
        user_uid=ctx["student_uid"],
    )
    assert second.is_ok, second.expect_error()
    second_uid = second.value.uid
    assert second_uid != first_uid, "second attempt must create a distinct node"

    async with neo4j_driver.session() as session:
        # Exactly two UserEntry nodes for this (student, exercise)
        node_count = await (
            await session.run(
                """
                MATCH (u:UserEntry {user_uid: $sid})-[:FULFILLS_EXERCISE]->(:Exercise {uid: $ex})
                RETURN count(DISTINCT u) AS cnt
                """,
                sid=ctx["student_uid"],
                ex=ctx["exercise_uid"],
            )
        ).single()
        assert node_count is not None and node_count["cnt"] == 2

        # No node carries a stale revision_number field
        stale = await (
            await session.run(
                """
                MATCH (u:UserEntry {user_uid: $sid})
                WHERE u.revision_number IS NOT NULL
                RETURN count(u) AS cnt
                """,
                sid=ctx["student_uid"],
            )
        ).single()
        assert stale is not None and stale["cnt"] == 0, (
            "revision_number should not live on the node"
        )

        # Revisions on the edges: first=1, second=2
        rev_result = await session.run(
            """
            MATCH (u:UserEntry)-[r:FULFILLS_EXERCISE]->(:Exercise {uid: $ex})
            WHERE u.uid IN [$u1, $u2]
            RETURN u.uid AS uid, r.revision AS revision
            """,
            ex=ctx["exercise_uid"],
            u1=first_uid,
            u2=second_uid,
        )
        by_uid = {r["uid"]: r["revision"] async for r in rev_result}
        assert by_uid == {first_uid: 1, second_uid: 2}, by_uid
