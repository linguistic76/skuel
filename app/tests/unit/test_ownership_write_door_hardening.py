"""
Ownership write doors — the two soft spots ADR-086 left open, now closed
=======================================================================

ADR-086 ratified ``(User)-[:OWNS]->(entity)`` as THE ownership edge and the
invariant every write door owes: **``user_uid`` property == ``:OWNS`` owner**.
It also graded the doors honestly rather than claiming they all enforce it —
and recorded hardening the soft ones as open work:

- **Door 2, bulk ingestion** — the owner is ``MATCH``ed inside a row-preserving
  unit ``CALL`` subquery *after* the node persists, so an unknown owner used to
  yield a property-only node while the ingest reported success.
- **Door 4, hand-written writers** — Exercise and Group persist the node, then
  write the edge in a *separate* query and only ``logger.warning`` when it
  fails, returning ok. (FormSubmission, also filed under door 4, is actually
  structural: one atomic ``MATCH``+``CREATE``, no record → fail.)

Both directions orphan data rather than disclose it — a property-only node
names a user who does not exist, so no live requester's property-scoped read
matches it — which is why ADR-086 could sanction property-scoped reads over a
soft door. Orphaning is still a defect, and a *silent* one: the caller is told
the write succeeded and only an integration test or a manual audit finds it.

These tests pin the loud half. Doors 1 (generic CRUD) and 3 (UserEntry) were
already structural and are unchanged.

See: /docs/decisions/ADR-086-universal-owns-and-attends-attendance.md
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.persistence.neo4j.bulk_upsert_backend import BulkUpsertBackend
from core.models.enums import EntityType, ExerciseScope
from core.models.exercises.exercise import Exercise
from core.services.exercises.exercise_service import ExerciseService
from core.utils.result_simplified import Errors, Result

pytestmark = pytest.mark.anyio


# ============================================================================
# Door 4 — Exercise: the edge write is load-bearing, not advisory
# ============================================================================


def _exercise(**overrides: object) -> Exercise:
    defaults: dict[str, object] = {
        "uid": "ex.test.owned",
        "entity_type": EntityType.EXERCISE,
        "title": "Sample",
        "instructions": "Do the thing.",
        "scope": ExerciseScope.ASSESSMENT,
        "owner_uid": "user_owner",
    }
    defaults.update(overrides)
    return Exercise(**defaults)  # type: ignore[arg-type]


class TestExerciseOwnsDoor:
    async def test_owns_failure_fails_the_create(self) -> None:
        """A failed OWNS write is returned, not warned about.

        The node is already persisted when the edge write runs, so the old
        warn-and-return-ok left an owner holding a create that reported success
        while the edge was missing — invisible to every :OWNS-traversing read
        (MEGA-QUERY anchors, ``get_user_exercises``, the GDPR cascade).
        """
        exercise = _exercise()
        backend = AsyncMock()
        backend.create = AsyncMock(return_value=Result.ok(exercise))
        backend.create_owns_relationship = AsyncMock(
            return_value=Result.fail(Errors.database(operation="owns", message="boom"))
        )
        service = ExerciseService(backend=backend)

        result = await service.create(exercise)

        assert result.is_error
        backend.create_owns_relationship.assert_awaited_once()

    async def test_owns_success_still_returns_the_exercise(self) -> None:
        """Positive control — the failure path above is not simply 'create is broken'."""
        exercise = _exercise()
        backend = AsyncMock()
        backend.create = AsyncMock(return_value=Result.ok(exercise))
        backend.create_owns_relationship = AsyncMock(return_value=Result.ok([]))
        service = ExerciseService(backend=backend)

        result = await service.create(exercise)

        assert result.is_ok
        assert result.value.uid == exercise.uid

    async def test_ownerless_curriculum_never_reaches_the_edge_write(self) -> None:
        """CURRICULUM exercises carry no owner — no edge is owed, so none is attempted.

        Without this the hardening above would break file-ingested curriculum
        content, which is deliberately ownerless (the validator forces
        ``scope: curriculum`` and no owner).
        """
        exercise = _exercise(uid="ex.test.curriculum", scope=ExerciseScope.CURRICULUM)
        object.__setattr__(exercise, "owner_uid", None)
        backend = AsyncMock()
        backend.create = AsyncMock(return_value=Result.ok(exercise))
        backend.create_owns_relationship = AsyncMock(
            return_value=Result.fail(Errors.database(operation="owns", message="boom"))
        )
        service = ExerciseService(backend=backend)

        result = await service.create(exercise)

        assert result.is_ok
        backend.create_owns_relationship.assert_not_awaited()


# ============================================================================
# Door 2 — bulk ingestion: refuse an owner the graph does not have
# ============================================================================


class _FakeResult:
    def __init__(self, record: dict[str, Any] | None) -> None:
        self._record = record

    async def single(self) -> dict[str, Any] | None:
        return self._record


class _FakeSession:
    """Records the Cypher the pre-flight runs and answers with a canned miss set."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        self.queries: list[tuple[str, dict[str, Any]]] = []

    async def run(self, query: str, params: dict[str, Any] | None = None) -> _FakeResult:
        self.queries.append((query, params or {}))
        return _FakeResult({"missing": self.missing})


def _items(*owners: str | None) -> list[dict[str, Any]]:
    return [
        {"uid": f"task_{i}", "_node_props": {"uid": f"task_{i}", "user_uid": owner}}
        for i, owner in enumerate(owners)
    ]


class TestBulkOwnerPreflight:
    async def test_refuses_when_an_owner_has_no_user_node(self) -> None:
        session = _FakeSession(missing=["user_ghost"])
        backend = BulkUpsertBackend(driver=MagicMock())

        refusal = await backend._refuse_unknown_owners(
            session, "Entity", _items("user_ghost", "user_real")
        )

        assert refusal is not None
        assert refusal.is_error
        # The error names the owner: the cause (deleted user, stale vault
        # descriptor, mistyped SKUEL_DEFAULT_USER_UID) is diagnosable without
        # re-running the ingest under a debugger.
        assert "user_ghost" in refusal.expect_error().message

    async def test_proceeds_when_every_owner_exists(self) -> None:
        session = _FakeSession(missing=[])
        backend = BulkUpsertBackend(driver=MagicMock())

        refusal = await backend._refuse_unknown_owners(
            session, "Entity", _items("user_real", "user_real")
        )

        assert refusal is None
        # One query for the whole batch, and the duplicate owner is asked about once.
        assert len(session.queries) == 1
        assert session.queries[0][1]["owner_uids"] == ["user_real"]

    async def test_ownerless_batches_never_query(self) -> None:
        """Shared curriculum names no owner — the door owes nothing, so it asks nothing."""
        session = _FakeSession(missing=[])
        backend = BulkUpsertBackend(driver=MagicMock())

        refusal = await backend._refuse_unknown_owners(session, "Entity", _items(None, None))

        assert refusal is None
        assert session.queries == []

    async def test_non_entity_batches_are_out_of_scope(self) -> None:
        """Group pops ownership to ``owner_uid`` before this template runs.

        The check reads exactly what the template's owns clause reads
        (``_node_props.user_uid`` on an ``:Entity`` batch) so the guard cannot
        drift from the write it guards — and so it does not invent a rule for
        a batch whose template writes no owner edge at all.
        """
        session = _FakeSession(missing=["user_ghost"])
        backend = BulkUpsertBackend(driver=MagicMock())

        refusal = await backend._refuse_unknown_owners(session, None, _items("user_ghost"))

        assert refusal is None
        assert session.queries == []

    async def test_a_driver_failure_refuses_rather_than_raising(self) -> None:
        """A Neo4j error in the pre-flight becomes a Result, and it fails CLOSED.

        The pre-flight runs on the raw session, outside ``CypherExecutor`` —
        which is what converts ``NEO4J_EXCEPTIONS`` into a Result for the batch
        write. Without a guard here a timeout or disconnect would raise out of a
        method whose signature promises a ``Result``, and ``ingest_directory``
        branches on ``result.is_ok`` with no try/except around the call (its one
        guard covers the MOC pass, much later). Codex P2 on #1176.

        Fail-closed matters as much as not-raising: an owner set we could not
        verify must refuse, never wave the batch through.
        """
        from neo4j.exceptions import ServiceUnavailable

        class _FailingSession(_FakeSession):
            async def run(self, query: str, params: dict[str, Any] | None = None) -> _FakeResult:
                raise ServiceUnavailable("connection lost")

        backend = BulkUpsertBackend(driver=MagicMock())

        refusal = await backend._refuse_unknown_owners(
            _FailingSession(missing=[]), "Entity", _items("user_real")
        )

        assert refusal is not None and refusal.is_error
        assert "user_real" in refusal.expect_error().message

    async def test_upsert_nodes_returns_the_refusal_before_writing(self) -> None:
        """The refusal short-circuits ``upsert_nodes`` — no batch is executed.

        The whole point is that nothing lands: a post-hoc check would report
        orphans it had already created.
        """
        session = _FakeSession(missing=["user_ghost"])
        backend = BulkUpsertBackend(driver=MagicMock())
        backend._driver.session = MagicMock(return_value=_AsyncCtx(session))
        executed: list[str] = []

        class _ExplodingExecutor:
            def __init__(self, *a: Any, **k: Any) -> None: ...

            async def execute_batch(self, **kwargs: Any) -> Result[dict[str, int]]:
                executed.append("ran")
                return Result.ok({"nodes_created": 1})

        import adapters.persistence.neo4j.bulk_upsert_backend as mod

        original = mod.CypherExecutor
        mod.CypherExecutor = _ExplodingExecutor  # type: ignore[misc,assignment]
        try:
            result = await backend.upsert_nodes(
                entity_label="Task",
                base_label="Entity",
                entities=[{"uid": "task_0", "user_uid": "user_ghost"}],
                relationship_config={},
            )
        finally:
            mod.CypherExecutor = original  # type: ignore[misc]

        assert result.is_error
        assert executed == [], "the batch ran despite an unknown owner"


class _AsyncCtx:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(self, *exc: object) -> None:
        return None
