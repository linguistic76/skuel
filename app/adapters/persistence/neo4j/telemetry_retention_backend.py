"""
Telemetry Retention Backend (ADR-080 Horizon 0)
===============================================

Age-based prune of the unbounded-growth telemetry types so the graph stays
AuraDB-Free node-cap-safe. Driven by the one-shot ``./dev telemetry-retention``
script (``scripts/telemetry_retention.py``) — never a background loop, so the
CORE "no background workers" guarantee holds.

Like :SearchEvent, these are plain infrastructure nodes/edges (not EntityTypes),
so this backend takes a ``Neo4jQueryExecutor`` directly rather than extending
``UniversalNeo4jBackend`` (SearchEventBackend / InsightBackend precedent).

**Timestamp storage is decided by each WRITER** (the temporal-storage-bug-class —
the #1 correctness risk here). Verified against the live graph 2026-07-22:

  - ``AuthEvent.timestamp``      ZONED DATETIME  (session_backend.log_auth_event
                                 wraps ``datetime($iso)``)
  - ``SearchEvent.created_at``   ZONED DATETIME  (search_event_backend wraps
                                 ``datetime($iso)``)
  - ``VIEWED.last_viewed_at``    ZONED DATETIME  (_learning_state_mixin wraps
                                 ``datetime($now)``)
  - ``Interaction.created_at``   **STRING**  (written through the universal
                                 backend's ``to_neo4j_node`` mapper, which
                                 ``.isoformat()``-serializes datetimes) → its
                                 filter parses with Cypher ``datetime(...)``.

**Saved discussions (:ConversationSession / :ConversationTurn) are deliberately
NOT pruned.** They are explicitly-saved user content (ADR-078 "Save this chat",
"ephemeral-by-default; explicit Save only"), not auto-accreting telemetry — a
retention run must never delete something a user chose to keep. Only auto-growing
system telemetry is in scope here.

Deletion is batched: each batch is its own auto-committed transaction (the
executor opens a fresh session per ``execute_query``), so a large prune never
holds one giant transaction open against a per-tx-ceilinged managed instance.

Every label / edge is a ``NeoLabel`` / ``RelationshipName`` member (SKUEL030).
Expired :Session / :PasswordResetToken are pruned on their own ``expires_at`` by
``SessionBackend.cleanup_expired_*`` — reused, not duplicated here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

_AUTH_EVENT = NeoLabel.AUTH_EVENT.value
_SEARCH_EVENT = NeoLabel.SEARCH_EVENT.value
_INTERACTION = NeoLabel.INTERACTION.value
_VIEWED = RelationshipName.VIEWED.value


class TelemetryRetentionBackend:
    """Age-based prune of unbounded-growth telemetry (ADR-080 Horizon 0)."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    # ------------------------------------------------------------------ #
    # Node types (native-datetime timestamp)
    # ------------------------------------------------------------------ #

    async def prune_auth_events(self, *, days: int, batch_size: int, dry_run: bool) -> Result[int]:
        """Prune :AuthEvent nodes older than ``days`` (native ``timestamp``)."""
        return await self._prune_nodes(
            label=_AUTH_EVENT,
            time_field="timestamp",
            native=True,
            days=days,
            batch_size=batch_size,
            dry_run=dry_run,
        )

    async def prune_search_events(
        self, *, days: int, batch_size: int, dry_run: bool
    ) -> Result[int]:
        """Prune :SearchEvent nodes older than ``days`` (native ``created_at``)."""
        return await self._prune_nodes(
            label=_SEARCH_EVENT,
            time_field="created_at",
            native=True,
            days=days,
            batch_size=batch_size,
            dry_run=dry_run,
        )

    async def prune_interactions(self, *, days: int, batch_size: int, dry_run: bool) -> Result[int]:
        """Prune :Interaction nodes older than ``days``.

        ``created_at`` is a **string** here (universal-backend writer), so its
        predicate parses with Cypher ``datetime(e.created_at)`` — the single
        difference from the native-datetime node types.
        """
        return await self._prune_nodes(
            label=_INTERACTION,
            time_field="created_at",
            native=False,
            days=days,
            batch_size=batch_size,
            dry_run=dry_run,
        )

    # ------------------------------------------------------------------ #
    # Edge type (native-datetime property)
    # ------------------------------------------------------------------ #

    async def prune_viewed_edges(self, *, days: int, batch_size: int, dry_run: bool) -> Result[int]:
        """Prune stale :VIEWED edges (native ``last_viewed_at`` older than ``days``).

        Deletes only the learner-state edge, never the Ku/PathStep it points at.
        """
        where = "r.last_viewed_at < datetime() - duration({days: $days})"
        count_q = f"MATCH ()-[r:{_VIEWED}]->() WHERE {where} RETURN count(r) AS cnt"
        delete_q = (
            f"MATCH ()-[r:{_VIEWED}]->() WHERE {where} "
            f"WITH r LIMIT $batch DELETE r RETURN count(r) AS cnt"
        )
        return await self._run(count_q, delete_q, days=days, batch_size=batch_size, dry_run=dry_run)

    # NOTE: There is deliberately NO prune method for :ConversationSession /
    # :ConversationTurn. Saved discussions are explicitly-kept user content
    # (ADR-078), not auto-accreting telemetry — see the module docstring.

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    async def _prune_nodes(
        self,
        *,
        label: str,
        time_field: str,
        native: bool,
        days: int,
        batch_size: int,
        dry_run: bool,
    ) -> Result[int]:
        """Build + run the count/delete pair for a single node label.

        ``native`` picks the predicate shape: a stored ZONED DATETIME compares
        directly, a stored ISO string is parsed with ``datetime(...)`` first.
        """
        lhs = f"e.{time_field}" if native else f"datetime(e.{time_field})"
        where = f"{lhs} < datetime() - duration({{days: $days}})"
        count_q = f"MATCH (e:{label}) WHERE {where} RETURN count(e) AS cnt"
        delete_q = (
            f"MATCH (e:{label}) WHERE {where} "
            "WITH e LIMIT $batch DETACH DELETE e RETURN count(e) AS cnt"
        )
        return await self._run(count_q, delete_q, days=days, batch_size=batch_size, dry_run=dry_run)

    async def _run(
        self,
        count_query: str,
        delete_query: str,
        *,
        days: int,
        batch_size: int,
        dry_run: bool,
    ) -> Result[int]:
        """Count (dry-run) or batch-delete until drained; return the total.

        Dry-run runs only the COUNT and deletes nothing. A real run loops the
        batched DELETE — each batch its own transaction — until a batch removes
        fewer than ``batch_size`` rows (the candidate set is drained).
        """
        if dry_run:
            result = await self._executor.execute_query(count_query, {"days": days})
            if result.is_error:
                return Result.fail(result)
            rows = result.value or []
            return Result.ok(int(rows[0]["cnt"]) if rows else 0)

        total = 0
        params = {"days": days, "batch": batch_size}
        while True:
            result = await self._executor.execute_query(delete_query, params)
            if result.is_error:
                return Result.fail(result)
            rows = result.value or []
            deleted = int(rows[0]["cnt"]) if rows else 0
            total += deleted
            if deleted < batch_size:
                break
        return Result.ok(total)


__all__ = ["TelemetryRetentionBackend"]
