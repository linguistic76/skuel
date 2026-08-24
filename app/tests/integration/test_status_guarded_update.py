"""``update_with_status_guard`` against a real Neo4j — the ADR-087 proof.

Two claims, and only a database can settle either.

**The branch matrix.** The conditional merges must select the right patch from the
prior the statement reads, and must leave the node *byte-identical* when the guard
refuses. Unit tests can pin which guard a service builds; whether Cypher honours it —
including that a ``null`` merge REMOVES a property rather than storing one, and that a
refused write does not even bump ``updated_at`` — is a property of the statement.

**The atomicity.** The whole point of the primitive is that two concurrent writers
cannot both observe the same prior. That is a claim about a node write-lock under real
contention, so it is asserted by racing writers with ``asyncio.gather`` and checking the
invariant that follows: across N concurrent completes on one task, exactly ONE sees a
non-completed prior — i.e. exactly one reports ``is_repeat=False``. A single failing
iteration falsifies the design, so the race runs repeatedly rather than once.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import EntityStatus
from core.models.enums.entity_enums import EntityType
from core.models.task.task import Task
from core.models.update_contracts import StatusWriteGuard
from core.services.completion_stamp import is_completion_transition, status_transition_guard

USER = "user_status_guard"
_COMPLETED = frozenset({EntityStatus.COMPLETED.value})
_TERMINAL = frozenset(s.value for s in EntityStatus if s.is_terminal())
_RACE_ITERATIONS = 20


@pytest.mark.asyncio
class TestStatusGuardedUpdate:
    @pytest_asyncio.fixture
    async def backend(self, neo4j_driver, clean_neo4j):
        return UniversalNeo4jBackend[Task](
            neo4j_driver, "Entity", Task, default_filters={"entity_type": "task"}
        )

    @pytest_asyncio.fixture
    async def seed(self, backend):
        """Create one task at a given status and return its uid."""
        counter = {"n": 0}

        async def _seed(status: EntityStatus = EntityStatus.ACTIVE, **fields) -> str:
            counter["n"] += 1
            uid = f"task.guard_{counter['n']}"
            result = await backend.create(
                Task(uid=uid, user_uid=USER, title="guarded", status=status, **fields)
            )
            assert result.is_ok
            return uid

        return _seed

    async def _props(self, neo4j_driver, uid: str) -> dict:
        async with neo4j_driver.session() as session:
            result = await session.run("MATCH (n:Entity {uid: $uid}) RETURN n", uid=uid)
            record = await result.single()
            return dict(record["n"]) if record else {}

    # -- branch matrix ------------------------------------------------------

    async def test_a_completion_stamps_and_returns_the_prior(self, backend, seed, neo4j_driver):
        uid = await seed(EntityStatus.ACTIVE)
        guard = status_transition_guard(EntityType.TASK, {"status": "completed"})

        result = await backend.update_with_status_guard(uid, {"status": "completed"}, guard.value)

        assert result.is_ok
        outcome = result.value
        assert outcome.applied is True
        assert outcome.prior_status == EntityStatus.ACTIVE.value
        # The writer decides the storage type: an ISO string, as every other writer stores.
        props = await self._props(neo4j_driver, uid)
        assert props["completion_date"] == date.today().isoformat()
        assert props["status"] == EntityStatus.COMPLETED.value

    async def test_reposting_completed_does_not_re_date(self, backend, seed, neo4j_driver):
        """The condition is what protects the original stamp — not a pre-read."""
        uid = await seed(EntityStatus.ACTIVE)
        guard = status_transition_guard(EntityType.TASK, {"status": "completed"})
        first = await backend.update_with_status_guard(uid, {"status": "completed"}, guard.value)
        assert first.is_ok
        stamped = (await self._props(neo4j_driver, uid))["completion_date"]

        # A second guard built later carries a fresh stamp value; the prior declines it.
        again = status_transition_guard(EntityType.TASK, {"status": "completed"})
        _statuses, patch = again.value.patch_if_prior_not_in
        patch["completion_date"] = date(2099, 1, 1)

        second = await backend.update_with_status_guard(uid, {"status": "completed"}, again.value)

        assert second.is_ok
        assert second.value.prior_status == EntityStatus.COMPLETED.value
        assert (await self._props(neo4j_driver, uid))["completion_date"] == stamped

    async def test_a_reopen_removes_the_stamp_property(self, backend, seed, neo4j_driver):
        """A ``None`` in the patch must REMOVE the property, not store a null."""
        uid = await seed(EntityStatus.ACTIVE)
        complete = status_transition_guard(EntityType.TASK, {"status": "completed"})
        assert (
            await backend.update_with_status_guard(uid, {"status": "completed"}, complete.value)
        ).is_ok
        assert "completion_date" in await self._props(neo4j_driver, uid)

        reopen = status_transition_guard(EntityType.TASK, {"status": "active"})
        result = await backend.update_with_status_guard(uid, {"status": "active"}, reopen.value)

        assert result.is_ok
        assert result.value.prior_status == EntityStatus.COMPLETED.value
        assert "completion_date" not in await self._props(neo4j_driver, uid)

    async def test_the_stamp_invariant_holds_across_the_cycle(self, backend, seed, neo4j_driver):
        """Non-null exactly when completed — swept over complete → reopen → complete."""
        uid = await seed(EntityStatus.ACTIVE)
        for target in ("completed", "active", "completed"):
            guard = status_transition_guard(EntityType.TASK, {"status": target})
            assert (
                await backend.update_with_status_guard(uid, {"status": target}, guard.value)
            ).is_ok
            props = await self._props(neo4j_driver, uid)
            assert ("completion_date" in props) is (props["status"] == "completed")

    async def test_a_refused_write_leaves_the_node_byte_identical(
        self, backend, seed, neo4j_driver
    ):
        """Guarded out means untouched — ``updated_at`` included, because it rides
        inside the conditional patch rather than being written unconditionally."""
        uid = await seed(EntityStatus.CANCELLED)
        before = await self._props(neo4j_driver, uid)

        result = await backend.update_with_status_guard(
            uid,
            {"status": EntityStatus.SCHEDULED.value, "title": "should not land"},
            StatusWriteGuard(refuse_if_prior_in=_TERMINAL),
        )

        assert result.is_ok, "a guarded-out write is an outcome, not an error"
        assert result.value.applied is False
        assert result.value.prior_status == EntityStatus.CANCELLED.value
        assert result.value.entity.title == "guarded"
        assert await self._props(neo4j_driver, uid) == before

    async def test_a_permitted_prior_passes_the_same_refuse_guard(self, backend, seed):
        uid = await seed(EntityStatus.ACTIVE)

        result = await backend.update_with_status_guard(
            uid,
            {"status": EntityStatus.SCHEDULED.value},
            StatusWriteGuard(refuse_if_prior_in=_TERMINAL),
        )

        assert result.is_ok
        assert result.value.applied is True
        assert result.value.entity.status == EntityStatus.SCHEDULED

    async def test_guarded_out_and_not_found_are_distinguishable(self, backend, seed):
        """One query leg tells them apart: a row proves existence, no row proves absence."""
        uid = await seed(EntityStatus.CANCELLED)
        guard = StatusWriteGuard(refuse_if_prior_in=_TERMINAL)

        refused = await backend.update_with_status_guard(uid, {"title": "x"}, guard)
        missing = await backend.update_with_status_guard(
            "task.does_not_exist", {"title": "x"}, guard
        )

        assert refused.is_ok and refused.value.applied is False
        assert missing.is_error
        assert missing.expect_error().category.value == "not_found"

    async def test_an_empty_write_with_no_patches_is_refused(self, backend, seed):
        uid = await seed(EntityStatus.ACTIVE)
        result = await backend.update_with_status_guard(uid, {}, StatusWriteGuard())
        assert result.is_error
        assert result.expect_error().category.value == "validation"

    async def test_a_patch_only_write_is_allowed(self, backend, seed, neo4j_driver):
        """Empty base updates are legal when a conditional patch carries the write."""
        uid = await seed(EntityStatus.ACTIVE)
        result = await backend.update_with_status_guard(
            uid, {}, StatusWriteGuard(patch_if_prior_not_in=(_COMPLETED, {"actual_minutes": 7}))
        )
        assert result.is_ok
        assert (await self._props(neo4j_driver, uid))["actual_minutes"] == 7

    async def test_the_base_patch_is_serialized_like_every_other_write(
        self, backend, seed, neo4j_driver
    ):
        """A raw ``date`` in the caller's patch must land as an ISO string, not a
        native Neo4j Date. ``update()`` maps its patch before writing; if this path
        did not, the same field would carry two storage types depending on which door
        wrote it — and the readers that compare it as a string would silently miss rows.
        """
        uid = await seed(EntityStatus.ACTIVE)

        result = await backend.update_with_status_guard(
            uid,
            {"due_date": date(2026, 9, 1), "status": EntityStatus.PAUSED.value},
            StatusWriteGuard(),
        )

        assert result.is_ok
        props = await self._props(neo4j_driver, uid)
        assert props["due_date"] == "2026-09-01"
        assert isinstance(props["updated_at"], str)

    async def test_the_lock_sentinel_never_lingers(self, backend, seed, neo4j_driver):
        uid = await seed(EntityStatus.ACTIVE)
        guard = status_transition_guard(EntityType.TASK, {"status": "completed"})
        assert (
            await backend.update_with_status_guard(uid, {"status": "completed"}, guard.value)
        ).is_ok
        assert "_sg_lock" not in await self._props(neo4j_driver, uid)

    # -- atomicity ----------------------------------------------------------

    async def test_concurrent_completes_produce_exactly_one_non_repeat(self, backend, seed):
        """The arc's proof. Four writers complete the same task at once; exactly one
        may report ``is_repeat=False``. Without the lock-first SET this fails almost
        every iteration (measured: 39/40 trials produced 2-4 such writers)."""
        for _ in range(_RACE_ITERATIONS):
            uid = await seed(EntityStatus.ACTIVE)
            changes = {"status": "completed"}

            async def _complete(task_uid: str = uid, patch: dict = changes):
                guard = status_transition_guard(EntityType.TASK, patch)
                return await backend.update_with_status_guard(task_uid, dict(patch), guard.value)

            results = await asyncio.gather(*[_complete() for _ in range(4)])

            assert all(r.is_ok for r in results)
            verdicts = [is_completion_transition(r.value.prior_status, changes) for r in results]
            assert sum(verdicts) == 1, f"priors were {[r.value.prior_status for r in results]}"

    async def test_a_concurrent_complete_and_reopen_leave_a_consistent_node(
        self, backend, seed, neo4j_driver
    ):
        """Either order is legal; what must never happen is a final state where the
        stamp and the status disagree. That is the three-click Undo vector: under the
        old read-then-write shape a complete serialized after a reopen wrote
        ``status=completed`` carrying the pre-reopen "already completed" verdict, so it
        declined to stamp and left a completed task with no completion_date."""
        for _ in range(_RACE_ITERATIONS):
            uid = await seed(EntityStatus.ACTIVE)

            async def _write(target: str, task_uid: str = uid):
                guard = status_transition_guard(EntityType.TASK, {"status": target})
                return await backend.update_with_status_guard(
                    task_uid, {"status": target}, guard.value
                )

            results = await asyncio.gather(_write("completed"), _write("active"))
            assert all(r.is_ok for r in results)

            props = await self._props(neo4j_driver, uid)
            assert ("completion_date" in props) is (props["status"] == "completed"), props
            # The two priors form a serialization chain: one saw the seeded status, the
            # other saw what its partner wrote.
            priors = {r.value.prior_status for r in results}
            assert priors <= {EntityStatus.ACTIVE.value, EntityStatus.COMPLETED.value}
            assert EntityStatus.ACTIVE.value in priors
