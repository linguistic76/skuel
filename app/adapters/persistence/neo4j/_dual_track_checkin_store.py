"""Atomic dual-track check-in append (ADR-030).

The check-in log is stored as a single JSON-string property (``dual_track_checkins``)
on the subject node — a flat ``list[dict]`` on per-entity subjects (Goals/Habits/
Principles) and a ``dict[dimension -> list[dict]]`` on the ``:User`` node (user-level
Productivity/Engagement/Decision-Quality dims). Appending is a read-modify-write of
that JSON, which two near-simultaneous appends on the *same subject* could otherwise
race (last writer wins, one snapshot lost).

This helper closes that race with a **node write-lock** held for the whole append:
the transaction's first statement writes a sentinel property (``_dtc_lock``), which
acquires Neo4j's write lock on the node. A concurrent appender blocks on that lock
until this transaction commits, then reads the just-written value — so no snapshot is
lost. The lock sentinel is removed in the same transaction, so it never lingers.

Cypher can't append inside a JSON string, so the append/cap happens in Python between
the locked read and the write — but always under the lock, so it is serialized. Both
store callbacks route through here so the per-entity and user-level paths share one
mechanism (One Path Forward). See docs/decisions/ADR-030.

Uses an **explicit transaction (no managed auto-retry)** deliberately: the append is
not idempotent (it blindly appends ``snapshot``), so a managed ``execute_write`` retry
after an unknown commit outcome could duplicate a check-in. An explicit transaction is
at-most-once — a rare transient failure surfaces as an error the (safe-by-design) store
callback swallows, losing that one check-in rather than duplicating it. Losing a check-in
is already within the persistence contract; duplicating one (skewed trends, wasted history
slots) is not.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from core.utils.exception_types import NEO4J_EXCEPTIONS

if TYPE_CHECKING:
    from neo4j import AsyncDriver


def _apply_append(
    raw: Any, snapshot: dict[str, Any], history_limit: int, dimension: str | None
) -> str:
    """Parse the current JSON log, append the snapshot, cap, and re-encode.

    ``raw`` is the stored property: a JSON string, or ``None``/empty when the node
    has no check-ins yet (the mapper writes ``None`` for an empty collection).
    ``dimension=None`` → flat ``list[dict]``; otherwise ``dict[dim -> list[dict]]``.
    """
    if dimension is None:
        current: list[dict[str, Any]] = json.loads(raw) if raw else []
        current.append(snapshot)
        return json.dumps(current[-history_limit:])

    logs: dict[str, list[dict[str, Any]]] = json.loads(raw) if raw else {}
    dim_log = list(logs.get(dimension, []))
    dim_log.append(snapshot)
    logs[dimension] = dim_log[-history_limit:]
    return json.dumps(logs)


async def atomic_append_checkin(
    driver: AsyncDriver,
    *,
    label: str,
    uid: str,
    snapshot: dict[str, Any],
    history_limit: int,
    dimension: str | None = None,
    property_name: str = "dual_track_checkins",
) -> bool:
    """Atomically append a dual-track check-in snapshot to a node's log.

    Serialized via a node write-lock so concurrent same-subject appends can't lose a
    snapshot (ADR-030). Returns ``True`` on append, ``False`` if no node matched
    ``(:label {uid})``.

    Args:
        driver: Neo4j async driver.
        label: Node label to match (e.g. ``"Goal"``, ``"User"``).
        uid: Subject UID.
        snapshot: The check-in snapshot dict (``DualTrackResult.to_checkin_snapshot``).
        history_limit: Max snapshots retained (oldest dropped past this).
        dimension: ``None`` for a flat per-entity log; the dimension/key for the
            ``dict``-keyed log (user-level dual-track dimension, or a Ku uid for the
            user's Knowledge check-ins).
        property_name: The node property holding the JSON log. Defaults to
            ``dual_track_checkins`` (the activity dual-track dimensions); the
            Knowledge dimension uses ``knowledge_checkins`` (keyed by Ku uid) so a
            per-Ku self-rating never collides with the three fixed user-level dims.
    """
    lock_token = uuid4().hex
    # Statement 1 acquires the node write-lock (a real property write) *before* the
    # read, so a concurrent appender blocks here until we commit. Statement 2 writes
    # the new log and drops the sentinel — both inside one explicit transaction.
    read_q = (
        f"MATCH (n:{label} {{uid: $uid}}) SET n._dtc_lock = $token RETURN n.{property_name} AS raw"
    )
    write_q = f"MATCH (n:{label} {{uid: $uid}}) SET n.{property_name} = $val REMOVE n._dtc_lock"

    async with driver.session() as session:
        tx = await session.begin_transaction()
        try:
            result = await tx.run(read_q, uid=uid, token=lock_token)
            record = await result.single()
            if record is None:
                await tx.rollback()
                return False
            new_value = _apply_append(record["raw"], snapshot, history_limit, dimension)
            await tx.run(write_q, uid=uid, val=new_value)
            await tx.commit()
            return True
        except NEO4J_EXCEPTIONS:
            await tx.rollback()
            raise
