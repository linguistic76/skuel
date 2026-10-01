"""
Revision-on-edge Integration Test — ADR-054 Commit 3
=====================================================

A turn-in's revision lives on its ``FULFILLS_EXERCISE`` edge (ADR-054). A
second attempt against the same exercise produces a brand-new ``:UserEntry``
node with a brand-new edge carrying ``revision = 2``; the first entry keeps its
node and its edge's ``revision = 1``.

The same statement stamps the turn-in snapshot — the root exercise's uid and
title — on the node and on the returned model (Submit & Share arc R12); the
second test pins that it survives the exercise's deletion. The third pins the
numbering across a delete: the next revision is one past the highest living
one, so a deleted entry's number is never minted onto a second living entry.
"""

from __future__ import annotations

import pytest

from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry import UserEntry
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
    first_uid = first.value[0].uid

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
    second_uid = second.value[0].uid
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


@pytest.mark.asyncio
async def test_turn_in_carries_the_exercise_snapshot(
    clean_neo4j,
    user_entry_service,
    neo4j_driver,
    seed_classroom,
) -> None:
    """The writer stamps ``turn_in_exercise_uid`` / ``turn_in_exercise_title``
    on the node and returns them on the model; a living-channel entry (a
    caller-supplied uid, no edge) carries neither."""
    ctx = await seed_classroom()

    created = await user_entry_service.create_entry(
        request=UserEntryCreateRequest(
            title="Attempt #1",
            content="initial answer",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid=ctx["exercise_uid"],
        ),
        user_uid=ctx["student_uid"],
    )
    assert created.is_ok, created.expect_error()
    entry = created.value[0]
    assert entry.turn_in_exercise_uid == ctx["exercise_uid"]
    assert entry.turn_in_exercise_title == "Test Exercise"

    async with neo4j_driver.session() as session:
        stored = await (
            await session.run(
                """
                MATCH (e:UserEntry {uid: $uid})
                RETURN e.turn_in_exercise_uid AS uid, e.turn_in_exercise_title AS title
                """,
                uid=entry.uid,
            )
        ).single()
        assert stored is not None
        assert stored["uid"] == ctx["exercise_uid"]
        assert stored["title"] == "Test Exercise"

        # The exercise goes; the snapshot stays — the exchange key outlives it.
        await session.run(
            "MATCH (ex:Entity:Exercise {uid: $ex}) DETACH DELETE ex", ex=ctx["exercise_uid"]
        )
        after = await (
            await session.run(
                """
                MATCH (e:UserEntry {uid: $uid})
                RETURN e.turn_in_exercise_uid AS uid,
                       EXISTS((e)-[:FULFILLS_EXERCISE]->()) AS has_edge
                """,
                uid=entry.uid,
            )
        ).single()
        assert after is not None
        assert after["uid"] == ctx["exercise_uid"]
        assert after["has_edge"] is False


@pytest.mark.asyncio
async def test_a_deleted_turn_in_leaves_a_gap_the_next_one_does_not_fill(
    clean_neo4j,
    user_entry_service,
    neo4j_driver,
    seed_classroom,
) -> None:
    """v1, v2, the student deletes v1: the next turn-in is v3, not a second v2.

    The number reaches three places — the edge, the snapshot and the default
    title — and all three read 3.
    """
    ctx = await seed_classroom()

    async def turn_in() -> UserEntry:
        created = await user_entry_service.create_entry(
            request=UserEntryCreateRequest(
                content="an answer",
                pipeline=Pipeline.TEACHER_REVIEW,
                fulfills_exercise_uid=ctx["exercise_uid"],
            ),
            user_uid=ctx["student_uid"],
        )
        assert created.is_ok, created.expect_error()
        return created.value[0]

    first = await turn_in()
    second = await turn_in()
    assert (first.turn_in_revision, second.turn_in_revision) == (1, 2)

    deleted = await user_entry_service.delete_entry(first.uid, ctx["student_uid"])
    assert deleted.is_ok, deleted.expect_error()

    third = await turn_in()

    assert third.turn_in_revision == 3
    assert third.title == "Test Exercise v3"
    async with neo4j_driver.session() as session:
        rows = await session.run(
            """
            MATCH (u:UserEntry {user_uid: $sid})-[r:FULFILLS_EXERCISE]->(:Exercise {uid: $ex})
            RETURN u.uid AS uid, u.title AS title, r.revision AS edge, u.turn_in_revision AS snapshot
            """,
            sid=ctx["student_uid"],
            ex=ctx["exercise_uid"],
        )
        living = {row["uid"]: (row["title"], row["edge"], row["snapshot"]) async for row in rows}
    assert living == {
        second.uid: ("Test Exercise v2", 2, 2),
        third.uid: ("Test Exercise v3", 3, 3),
    }
