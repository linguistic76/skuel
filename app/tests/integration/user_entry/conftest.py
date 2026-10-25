"""
UserEntry Integration Test Fixtures — ADR-054
==============================================

Provides a fully-wired ``UserEntryService`` + ``UnifiedSharingService``
stack over a real Neo4j container, plus seed helpers for the nodes each
flow test needs (users, groups, exercises).

These fixtures stay local to the ``user_entry`` integration suite; the
session-scoped ``neo4j_driver`` / ``clean_neo4j`` fixtures come from
``tests/integration/conftest.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import pytest_asyncio

from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from core.services.sharing.unified_sharing_service import UnifiedSharingService
from core.services.user_entry.user_entry_service import UserEntryService


@pytest_asyncio.fixture
async def user_entry_backend(neo4j_driver) -> AsyncIterator[UserEntryBackend]:
    """Real ``UserEntryBackend`` bound to the test Neo4j driver."""
    yield build_production_backends(neo4j_driver)["user_entry_backend"]


@pytest_asyncio.fixture
async def sharing_service(neo4j_driver) -> AsyncIterator[UnifiedSharingService]:
    """Real ``UnifiedSharingService`` over a real ``SharingBackend``."""
    backend = build_production_backends(neo4j_driver)["sharing_backend"]
    yield UnifiedSharingService(backend=backend)


@pytest_asyncio.fixture
async def user_entry_service(
    user_entry_backend: UserEntryBackend,
    sharing_service: UnifiedSharingService,
) -> AsyncIterator[UserEntryService]:
    """``UserEntryService`` wired with real backend + sharing service.

    ``interaction_service`` / ``event_bus`` are left unset — the flow
    tests assert on graph state, not audit/event side effects.
    """
    yield UserEntryService(
        backend=user_entry_backend,  # type: ignore[arg-type]
        sharing_service=sharing_service,
    )


@pytest_asyncio.fixture
async def seed_user(neo4j_driver) -> Callable[..., Awaitable[str]]:
    """Return an async helper that MERGEs a ``:User`` node and returns its UID."""

    async def _seed(uid: str, name: str | None = None) -> str:
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (u:User {uid: $uid})
                ON CREATE SET u.name = $name,
                              u.created_at = datetime()
                SET u.name = coalesce(u.name, $name)
                """,
                uid=uid,
                name=name or uid,
            )
        return uid

    return _seed


@pytest_asyncio.fixture
async def seed_group(neo4j_driver) -> Callable[..., Awaitable[str]]:
    """MERGE a ``:Group`` node owned by a teacher (User-[:OWNS]->Group).

    ``is_active = true`` mirrors the real creation path (``Group.is_active``
    defaults to ``True`` and is always serialized to the node) — every
    teacher-review surface (queue, detail, writes) gates on it, so a seed
    without it models a group that cannot exist in production.
    """

    async def _seed(group_uid: str, teacher_uid: str, name: str | None = None) -> str:
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (g:Group {uid: $group_uid})
                ON CREATE SET g.name = $name,
                              g.created_at = datetime()
                SET g.is_active = true
                WITH g
                MATCH (t:User {uid: $teacher_uid})
                MERGE (t)-[:OWNS]->(g)
                """,
                group_uid=group_uid,
                name=name or group_uid,
                teacher_uid=teacher_uid,
            )
        return group_uid

    return _seed


@pytest_asyncio.fixture
async def seed_membership(neo4j_driver) -> Callable[..., Awaitable[None]]:
    """MERGE a ``(:User)-[:MEMBER_OF]->(:Group)`` edge.

    A ``teacher:<group_uid>`` feedback target and a ``group:`` share each
    require the submitter to be a member of the group.
    """

    async def _seed(user_uid: str, group_uid: str) -> None:
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (u:User {uid: $user_uid})
                MATCH (g:Group {uid: $group_uid})
                MERGE (u)-[:MEMBER_OF]->(g)
                """,
                user_uid=user_uid,
                group_uid=group_uid,
            )

    return _seed


@pytest_asyncio.fixture
async def seed_exercise(neo4j_driver) -> Callable[..., Awaitable[str]]:
    """MERGE an exercise as the content-vault sync writes it (ADR-091 S2-S4).

    Ownerless curriculum (``scope: curriculum``, no ``:OWNS``), hanging from a
    published PathStep (``HAS_EXERCISE``). ``teacher_uid`` is the teacher its file
    names (``REVIEWED_BY``; the sync admits only a TEACHER, so the role is set);
    each of ``learner_uids`` is in progress on the step, the tie that admits a
    turn-in.
    """

    async def _seed(
        exercise_uid: str,
        title: str = "Test Exercise",
        teacher_uid: str | None = None,
        learner_uids: tuple[str, ...] = (),
    ) -> str:
        now_iso = datetime.now().isoformat()
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (ex:Entity:Exercise {uid: $exercise_uid})
                ON CREATE SET ex.title = $title,
                              ex.entity_type = 'exercise',
                              ex.scope = 'curriculum',
                              ex.status = 'active',
                              ex.visibility = 'private',
                              ex.created_at = datetime($now),
                              ex.updated_at = datetime($now)
                MERGE (ps:Entity:PathStep {uid: $step_uid})
                ON CREATE SET ps.title = $step_uid,
                              ps.entity_type = 'path_step',
                              ps.status = 'active',
                              ps.publication_state = 'published'
                MERGE (ps)-[:HAS_EXERCISE]->(ex)
                WITH ex, ps
                UNWIND $learners AS learner_uid
                MATCH (learner:User {uid: learner_uid})
                MERGE (learner)-[ip:IN_PROGRESS]->(ps)
                ON CREATE SET ip.started_at = datetime($now),
                              ip.last_activity_at = datetime($now),
                              ip.progress_score = 0.0
                """,
                exercise_uid=exercise_uid,
                step_uid=f"ps.{exercise_uid}",
                title=title,
                learners=list(learner_uids),
                now=now_iso,
            )
            if teacher_uid is not None:
                await session.run(
                    """
                    MATCH (ex:Entity:Exercise {uid: $exercise_uid})
                    MATCH (t:User {uid: $teacher_uid})
                    SET t.role = 'teacher'
                    MERGE (ex)-[:REVIEWED_BY]->(t)
                    """,
                    exercise_uid=exercise_uid,
                    teacher_uid=teacher_uid,
                )
        return exercise_uid

    return _seed


@pytest_asyncio.fixture
async def seed_classroom(
    seed_user: Callable[..., Awaitable[str]],
    seed_group: Callable[..., Awaitable[str]],
    seed_membership: Callable[..., Awaitable[None]],
    seed_exercise: Callable[..., Awaitable[str]],
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Compose one teacher + one group + one exercise + one student.

    The exercise names the teacher, and the student is in progress on its step
    and a member of the teacher's group. Returns a dict with ``teacher_uid``,
    ``student_uid``, ``group_uid``, ``exercise_uid`` suitable for the flow tests
    to submit against.
    """

    async def _seed(
        *,
        teacher_uid: str = seed_user_uid("ue_teacher"),
        student_uid: str = seed_user_uid("ue_student"),
        group_uid: str = "group.ue-class",
        exercise_uid: str = "exercise.ue-demo",
    ) -> dict[str, Any]:
        await seed_user(teacher_uid, name="Teacher")
        await seed_user(student_uid, name="Student")
        await seed_group(group_uid, teacher_uid)
        await seed_membership(student_uid, group_uid)
        await seed_exercise(exercise_uid, teacher_uid=teacher_uid, learner_uids=(student_uid,))
        return {
            "teacher_uid": teacher_uid,
            "student_uid": student_uid,
            "group_uid": group_uid,
            "exercise_uid": exercise_uid,
        }

    return _seed
