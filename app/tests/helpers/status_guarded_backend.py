"""A faithful in-memory stand-in for ``update_with_status_guard`` (ADR-087).

Unit tests of a status chokepoint care about how the SERVICE uses the primitive's
contract — which guard it builds, and which verdicts it derives from the prior the
write hands back. They cannot use the real backend, and a bare ``AsyncMock`` would
let a service assert nothing about the guard it just built.

So this fake evaluates the guard the way the Cypher does, against a status it holds
in memory: refuse-set first, then the two conditional patches, then the base patch.
It returns a real :class:`StatusGuardedOutcome` carrying the prior it saw. What it
deliberately does NOT model is the mechanism that makes the real thing correct — the
node write-lock. Concurrency and the storage shapes the merge produces are pinned
against a real Neo4j in ``tests/integration/test_status_guarded_update.py``; this
harness answers "did the service ask for the right thing, and read the answer right".

Three shapes, one guard evaluation (:func:`resolve_merged_patch`): ``guarded_backend``
for one node, ``echoing_guarded_write`` for fixtures that configure ``get``/``update``
return values, and ``guarded_rows_backend`` for the per-row loops that write several
nodes in one call.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock, Mock

from core.models.update_contracts import StatusGuardedOutcome, StatusWriteGuard
from core.utils.result_simplified import Errors, Result


def prior_status_of(entity: Any) -> str | None:
    """The canonical status string of a stored row, model- or dict-shaped.

    Backends hand services domain models (post ``from_neo4j_node``), but several
    older fixtures still stand in with raw property dicts. Both shapes appear in
    tests, and the prior the write returns is a plain string either way.
    """
    if entity is None:
        return None
    status = entity.get("status") if isinstance(entity, dict) else getattr(entity, "status", None)
    if status is None:
        return None
    value = getattr(status, "value", status)
    return value if isinstance(value, str) else None


def resolve_merged_patch(
    prior: str | None, updates: Mapping[str, Any], guard: StatusWriteGuard
) -> dict[str, Any]:
    """What the write would actually merge for this prior — the Cypher's CASE arms.

    Base patch first, then whichever conditional patch the prior selects; an empty
    map when the guard refuses, because a refused write leaves the node
    byte-identical. One implementation, so every fake below resolves a guard the
    same way.
    """
    if prior in guard.refuse_if_prior_in:
        return {}
    merged = dict(updates)
    if guard.patch_if_prior_in is not None:
        statuses, patch = guard.patch_if_prior_in
        if prior in statuses:
            merged.update(patch)
    if guard.patch_if_prior_not_in is not None:
        statuses, patch = guard.patch_if_prior_not_in
        if prior not in statuses:
            merged.update(patch)
    return merged


class StatusGuardedWriteRecorder:
    """Records each guarded write and answers it from an in-memory prior status."""

    def __init__(self, current: Any, updated: Any) -> None:
        self._current = current
        self._updated = updated
        #: Every ``(uid, updates, guard)`` the service asked for, in order.
        self.calls: list[tuple[str, dict[str, Any], StatusWriteGuard]] = []

    def set_state(self, current: Any, updated: Any) -> None:
        """Re-point the in-memory prior and post-write entity — for the second call
        in a sequence (complete, then Undo), where the real graph has already moved."""
        self._current = current
        self._updated = updated

    @property
    def last_guard(self) -> StatusWriteGuard:
        """The guard the most recent call carried."""
        return self.calls[-1][2]

    @property
    def last_updates(self) -> dict[str, Any]:
        """The unconditional patch the most recent call carried."""
        return self.calls[-1][1]

    def merged_patch(self) -> dict[str, Any]:
        """What the write would actually have merged — base patch plus whichever
        conditional patch the prior selected. The resolved view, for tests that
        care about the outcome rather than the condition."""
        _uid, updates, guard = self.calls[-1]
        return resolve_merged_patch(self._prior_status(), updates, guard)

    def _prior_status(self) -> str | None:
        return prior_status_of(self._current)

    def __call__(
        self, uid: str, updates: dict[str, Any], guard: StatusWriteGuard
    ) -> Result[StatusGuardedOutcome[Any]]:
        # Sync on purpose: it is wired as an ``AsyncMock`` side effect, and the mock
        # returns this value from its own await. An async side effect would come back
        # as an un-awaited coroutine.
        self.calls.append((uid, dict(updates), guard))
        prior = self._prior_status()
        applied = prior not in guard.refuse_if_prior_in
        return Result.ok(
            StatusGuardedOutcome(
                applied=applied,
                prior_status=prior,
                entity=self._updated if applied else self._current,
            )
        )


def guarded_backend(current: Any, updated: Any) -> tuple[Mock, StatusGuardedWriteRecorder]:
    """A backend mock whose ``get``/``update`` return domain models (the writer
    shape, post ``from_neo4j_node``) and whose ``update_with_status_guard`` is the
    recorder above.

    Returns the backend and the recorder, so a test can assert on the guard without
    reaching through ``Mock.await_args``.
    """
    recorder = StatusGuardedWriteRecorder(current, updated)
    backend = Mock()
    backend.get = AsyncMock(return_value=Result.ok(current))
    backend.update = AsyncMock(return_value=Result.ok(updated))
    backend.update_with_status_guard = AsyncMock(side_effect=recorder)
    return backend, recorder


def echoing_guarded_write(backend: Mock) -> AsyncMock:
    """A guarded write for fixtures that configure ``get``/``update`` return values.

    Reads the prior from whatever ``backend.get`` is currently set to return and the
    post-write entity from ``backend.update`` — resolved at call time, so a test that
    re-points either after the fixture is built still gets a consistent answer. An
    error configured on ``update`` propagates unchanged, which is how a not-found or a
    transient write failure keeps behaving as it did.
    """

    def _call(
        uid: str, updates: dict[str, Any], guard: StatusWriteGuard
    ) -> Result[StatusGuardedOutcome[Any]]:
        read = backend.get.return_value
        prior = prior_status_of(read.value) if read is not None and read.is_ok else None
        written = backend.update.return_value
        if written.is_error:
            return written
        applied = prior not in guard.refuse_if_prior_in
        return Result.ok(
            StatusGuardedOutcome(
                applied=applied,
                prior_status=prior,
                entity=written.value if applied else (read.value if read is not None else None),
            )
        )

    return AsyncMock(side_effect=_call)


class GuardedRowStore:
    """The multi-row form: a uid → stored-entity map the guarded write is answered from.

    What ``guarded_backend`` is for one node, this is for the per-row loops (bulk
    completion). Each call resolves the guard against THAT row's own status and
    records the patch the write would have merged for it, which is what a per-row
    assertion is about. A uid mapped to ``None`` is a row the write cannot find, and
    fails as the real statement does — no row matched.

    The stored entity is handed back as ``outcome.entity``. That is a faithful stand-in
    for the post-write node wherever the caller reads fields the patch does not touch
    (``due_date`` / ``actual_minutes`` for the completion event); it deliberately does
    not re-materialize the row, since these are frozen models.
    """

    def __init__(self, rows: Mapping[str, Any]) -> None:
        self.rows = dict(rows)
        #: Every ``(uid, updates, guard)`` asked for, in order.
        self.calls: list[tuple[str, dict[str, Any], StatusWriteGuard]] = []
        #: uid → the patch that row's write merged. Absent for a row that was refused
        #: or not found.
        self.merged: dict[str, dict[str, Any]] = {}

    def __call__(
        self, uid: str, updates: dict[str, Any], guard: StatusWriteGuard
    ) -> Result[StatusGuardedOutcome[Any]]:
        # Sync on purpose — see StatusGuardedWriteRecorder.__call__.
        self.calls.append((uid, dict(updates), guard))
        stored = self.rows.get(uid)
        if stored is None:
            return Result.fail(Errors.not_found("resource", f"Entity {uid} not found"))
        prior = prior_status_of(stored)
        applied = prior not in guard.refuse_if_prior_in
        if applied:
            self.merged[uid] = resolve_merged_patch(prior, updates, guard)
        return Result.ok(StatusGuardedOutcome(applied=applied, prior_status=prior, entity=stored))


def guarded_rows_backend(rows: Mapping[str, Any]) -> tuple[Mock, GuardedRowStore]:
    """A backend mock over several rows, whose ``update_with_status_guard`` is a
    :class:`GuardedRowStore`. ``get`` answers from the same map, so a test that still
    needs a read gets an answer consistent with the write."""
    store = GuardedRowStore(rows)

    async def _get(uid: str) -> Result[Any]:
        stored = store.rows.get(uid)
        if stored is None:
            return Result.fail(Errors.not_found("resource", f"Entity {uid} not found"))
        return Result.ok(stored)

    backend = Mock()
    backend.get = AsyncMock(side_effect=_get)
    backend.update_with_status_guard = AsyncMock(side_effect=store)
    return backend, store
