"""The enrollment cap is decided by the write: concurrent starts never hold more than it.

``PsBackend.mark_in_progress`` is one statement. It locks the learner's ``User`` node
first, then, under that lock, reads mastery, the hold and the tally, and writes a new
start only while the learner holds fewer than ``ENROLLMENT_CAP`` steps. Every
learner-state write takes the same lock first (``LOCK_LEARNER``): the PathStep writes,
the Ku writes, and the pathways door's two. Sign-in writes the User node first too. So
one learner's writes run one at a time, in one order (User, then the step or Ku), and
none of them deadlocks.

Each claim has a control: the same mix with the lock replaced by a bare ``WITH u``.
Without it, concurrent starts overshoot the cap (measured: 20 of 20 trials of 6
starts over 1 held), and the learner-write mix deadlocks (measured: 44, 50 and 48 of
130 calls in three runs; 0 with the lock). An auto-commit statement answers a
deadlock as an error, which the learner sees as a failed click.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest

from adapters.persistence.neo4j import _learning_state_mixin, user_backend
from adapters.persistence.neo4j.backends import curriculum_backends
from core.models.auth.session import create_session
from core.services.ps.ps_mastery_service import (
    ENROLLMENT_CAP,
    ENROLLMENT_CAP_RULE,
    PsMasteryService,
)
from core.services.ps.ps_prerequisite_gate import PsPrerequisiteGate
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from neo4j import AsyncDriver

    from core.utils.result_simplified import Result

pytestmark = pytest.mark.asyncio(loop_scope="session")

STARTS = 6
TRIALS = 10
_UNLOCKED = "WITH u"


def _unlock(monkeypatch: pytest.MonkeyPatch, *modules: object) -> None:
    """Replace the learner lock with a bare ``WITH u`` in each module that composes it."""
    for module in modules:
        assert "SET u.uid = u.uid" in module.LOCK_LEARNER  # type: ignore[attr-defined]
        monkeypatch.setattr(module, "LOCK_LEARNER", _UNLOCKED)


async def _learner(
    driver: AsyncDriver, tag: str, steps: int, held: int = 1
) -> tuple[str, list[str]]:
    """A fresh learner, ``steps`` published PathSteps, and the first ``held`` of them held."""
    run = uuid.uuid4().hex[:8]
    user = seed_user_uid(f"zzcap{tag}{run}")
    step_uids = [f"ps.zzcap.{tag}-{run}-{i}" for i in range(steps)]
    async with driver.session() as session:
        await session.run("MERGE (u:User {uid: $u}) ON CREATE SET u.title = $u", u=user)
        await session.run(
            """
            UNWIND $steps AS uid
            CREATE (:Entity:PathStep {uid: uid, entity_type: 'path_step', title: uid,
                                      status: 'active', publication_state: 'published'})
            """,
            steps=step_uids,
        )
        await session.run(
            """
            MATCH (u:User {uid: $u})
            UNWIND $held AS uid
            MATCH (ps:PathStep {uid: uid})
            CREATE (u)-[:IN_PROGRESS {started_at: datetime()}]->(ps)
            """,
            u=user,
            held=step_uids[:held],
        )
    return user, step_uids


async def _held(driver: AsyncDriver, user: str) -> list[str]:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (:User {uid: $u})-[:IN_PROGRESS]->(ps:PathStep) RETURN ps.uid AS uid",
            u=user,
        )
        return sorted([record["uid"] async for record in result])


def _mastery(driver: AsyncDriver) -> PsMasteryService:
    backends = build_production_backends(driver)
    return PsMasteryService(
        backend=backends["ps_backend"],
        prerequisite_gate=PsPrerequisiteGate(backends["ps_intelligence_backend"]),
    )


def _rule(result: object) -> object:
    return result.expect_error().details.get("rule")  # type: ignore[attr-defined]


# ------------------------------------------------------------------ the cap


async def test_concurrent_starts_hold_exactly_the_cap(neo4j_driver, clean_neo4j) -> None:
    """A learner holding one step fires six starts at once: one lands, five are capped."""
    service = _mastery(neo4j_driver)
    for _ in range(TRIALS):
        user, steps = await _learner(neo4j_driver, "gather", STARTS + 1)

        results = await asyncio.gather(*(service.mark_in_progress(user, uid) for uid in steps[1:]))

        assert len(await _held(neo4j_driver, user)) == ENROLLMENT_CAP
        assert sum(1 for r in results if r.is_ok) == ENROLLMENT_CAP - 1
        refused = [r for r in results if r.is_error]
        assert [_rule(r) for r in refused] == [ENROLLMENT_CAP_RULE] * (
            STARTS - (ENROLLMENT_CAP - 1)
        )


async def test_without_the_lock_the_same_starts_overshoot(
    neo4j_driver, clean_neo4j, monkeypatch
) -> None:
    """The control: the same statement minus the lock lets concurrent starts past the cap."""
    _unlock(monkeypatch, _learning_state_mixin)
    backend = build_production_backends(neo4j_driver)["ps_backend"]
    overshoots = 0
    for _ in range(TRIALS):
        user, steps = await _learner(neo4j_driver, "control", STARTS + 1)
        now = datetime.now(UTC).isoformat()

        await asyncio.gather(
            *(backend.mark_in_progress(user, uid, now, ENROLLMENT_CAP) for uid in steps[1:])
        )

        overshoots += len(await _held(neo4j_driver, user)) > ENROLLMENT_CAP
    assert overshoots > 0, "the control never raced: it proves nothing about the lock"


async def test_a_restart_beside_a_new_start_takes_no_second_slot(neo4j_driver, clean_neo4j) -> None:
    """Re-starting a held step is no new slot, even while a new start races it."""
    backend = build_production_backends(neo4j_driver)["ps_backend"]
    for _ in range(TRIALS):
        user, (held, new, late) = await _learner(neo4j_driver, "restart", 3)
        now = datetime.now(UTC).isoformat()

        results = await asyncio.gather(
            *(backend.mark_in_progress(user, held, now, ENROLLMENT_CAP) for _ in range(3)),
            backend.mark_in_progress(user, new, now, ENROLLMENT_CAP),
        )
        after = await backend.mark_in_progress(user, late, now, ENROLLMENT_CAP)

        rows = [r.value[0] for r in results]
        assert (
            rows[:3] == [{"mastered": False, "held": True, "started": False, "capped": False}] * 3
        )
        assert rows[3] == {"mastered": False, "held": False, "started": True, "capped": False}
        assert after.value == [{"mastered": False, "held": False, "started": False, "capped": True}]
        assert await _held(neo4j_driver, user) == sorted([held, new])


async def test_the_row_reports_mastery_and_no_row_answers_a_draft(
    neo4j_driver, clean_neo4j
) -> None:
    backend = build_production_backends(neo4j_driver)["ps_backend"]
    user, (mastered, draft) = await _learner(neo4j_driver, "row", 2, held=0)
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (u:User {uid: $u}), (m:PathStep {uid: $m}), (d:PathStep {uid: $d})
            CREATE (u)-[:MASTERED {mastered_at: datetime()}]->(m)
            SET d.publication_state = 'draft'
            """,
            u=user,
            m=mastered,
            d=draft,
        )
    now = datetime.now(UTC).isoformat()

    on_mastered = await backend.mark_in_progress(user, mastered, now, ENROLLMENT_CAP)
    on_draft = await backend.mark_in_progress(user, draft, now, ENROLLMENT_CAP)

    assert on_mastered.value == [
        {"mastered": True, "held": False, "started": False, "capped": False}
    ]
    assert on_draft.value == []
    assert await _held(neo4j_driver, user) == []


# ------------------------------------------------------------ one lock order


async def _learner_write_mix(driver: AsyncDriver) -> list[str]:
    """One learner's writes at once, over every statement that takes their lock.

    The learner holds two steps (A, B) and studies B's Kus. Fired together: three
    starts (C and D new, A held), the derived mastery of B, Mark as read and Review
    again on A, two views, a bookmark, the pathways door's Ku mastery and progress,
    the Ku page's Studying, and a sign-in. Answers each call that failed.
    """
    backends = build_production_backends(driver)
    steps = backends["ps_backend"]
    users = backends["users_backend"]
    kus = backends["ku_backend"]
    sessions = backends["session_backend"]
    failures: list[str] = []
    for _ in range(TRIALS):
        user, (a, b, c, d) = await _learner(driver, "mix", 4, held=2)
        run = uuid.uuid4().hex[:8]
        ku_uids = [f"ku.zzcap.mix-{run}-{i}" for i in range(3)]
        async with driver.session() as session:
            await session.run(
                """
                MATCH (ps:PathStep {uid: $ps})
                UNWIND $kus AS uid
                CREATE (ku:Entity:Ku {uid: uid, entity_type: 'ku', title: uid,
                                      status: 'active'})
                CREATE (ps)-[:USES_KU]->(ku)
                """,
                ps=b,
                kus=ku_uids,
            )
        now = datetime.now(UTC).isoformat()

        # boundary: thirteen writers, each its own Result payload — genuinely heterogeneous
        writes: list[Awaitable[Result[Any]]] = [
            steps.mark_in_progress(user, c, now, ENROLLMENT_CAP),
            steps.mark_in_progress(user, d, now, ENROLLMENT_CAP),
            steps.mark_in_progress(user, a, now, ENROLLMENT_CAP),
            steps.mark_mastered(user, b, now, 1.0, "derived"),
            steps.mark_as_read(user, a),
            steps.mark_as_learning(user, a),
            steps.record_view(user, c, now, 0),
            steps.record_view(user, a, now, 0),
            steps.create_bookmark(user, d),
            users.record_knowledge_mastery(user, ku_uids[0], 0.9),
            users.record_knowledge_progress(user, ku_uids[1], 0.5),
            kus.mark_in_progress(user, ku_uids[2]),
            sessions.create_session(create_session(user, "test", "test").session),
        ]
        results = await asyncio.gather(*writes)

        failures += [str(r.error) for r in results if r.is_error]
    return failures


async def test_one_learners_writes_race_without_deadlock(neo4j_driver, clean_neo4j) -> None:
    failures = await _learner_write_mix(neo4j_driver)

    assert failures == []


async def test_without_the_lock_the_same_writes_deadlock(
    neo4j_driver, clean_neo4j, monkeypatch
) -> None:
    """The control: the same mix, every learner lock replaced by a bare ``WITH u``."""
    _unlock(monkeypatch, _learning_state_mixin, curriculum_backends, user_backend)

    failures = await _learner_write_mix(neo4j_driver)

    assert any("DeadlockDetected" in failure for failure in failures), (
        "the control never deadlocked: it proves nothing about the lock order"
    )
