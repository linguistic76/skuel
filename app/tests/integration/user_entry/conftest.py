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

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

from adapters.persistence.neo4j.backends.sharing_backend import SharingBackend
from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from core.models.entity import Entity
from core.models.enums.neo_labels import NeoLabel
from core.services.sharing.unified_sharing_service import UnifiedSharingService
from core.services.user_entry.user_entry_service import UserEntryService


@pytest_asyncio.fixture
async def user_entry_backend(neo4j_driver) -> AsyncIterator[UserEntryBackend]:
    """Real ``UserEntryBackend`` bound to the test Neo4j driver."""
    yield UserEntryBackend(neo4j_driver)


@pytest_asyncio.fixture
async def sharing_service(neo4j_driver) -> AsyncIterator[UnifiedSharingService]:
    """Real ``UnifiedSharingService`` over a real ``SharingBackend``."""
    backend = SharingBackend(neo4j_driver, NeoLabel.ENTITY, Entity)
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

    Required for auto-share fan-out: ``query_exercise_groups_for_member``
    only returns groups the submitter is an active member of (commit 7dc89f3f,
    "security(upload): close UserEntry authorization holes").
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
    """MERGE an ``(:Entity:Exercise)`` node and SHARED_WITH_GROUP to a group."""

    async def _seed(
        exercise_uid: str,
        title: str = "Test Exercise",
        group_uid: str | None = None,
    ) -> str:
        now_iso = datetime.now().isoformat()
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (ex:Entity:Exercise {uid: $exercise_uid})
                ON CREATE SET ex.title = $title,
                              ex.entity_type = 'exercise',
                              ex.status = 'active',
                              ex.visibility = 'shared',
                              ex.created_at = datetime($now),
                              ex.updated_at = datetime($now)
                """,
                exercise_uid=exercise_uid,
                title=title,
                now=now_iso,
            )
            if group_uid is not None:
                await session.run(
                    """
                    MATCH (ex:Entity:Exercise {uid: $exercise_uid})
                    MATCH (g:Group {uid: $group_uid})
                    MERGE (ex)-[r:SHARED_WITH_GROUP]->(g)
                    ON CREATE SET r.shared_at = datetime($now),
                                  r.share_version = 'original'
                    """,
                    exercise_uid=exercise_uid,
                    group_uid=group_uid,
                    now=now_iso,
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

    Returns a dict with ``teacher_uid``, ``student_uid``, ``group_uid``,
    ``exercise_uid`` suitable for the flow tests to submit against.
    """

    async def _seed(
        *,
        teacher_uid: str = "user_ue_teacher",
        student_uid: str = "user_ue_student",
        group_uid: str = "group.ue_class",
        exercise_uid: str = "exercise.ue_demo",
    ) -> dict[str, Any]:
        await seed_user(teacher_uid, name="Teacher")
        await seed_user(student_uid, name="Student")
        await seed_group(group_uid, teacher_uid)
        await seed_membership(student_uid, group_uid)
        await seed_exercise(exercise_uid, group_uid=group_uid)
        return {
            "teacher_uid": teacher_uid,
            "student_uid": student_uid,
            "group_uid": group_uid,
            "exercise_uid": exercise_uid,
        }

    return _seed
