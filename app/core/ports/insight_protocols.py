"""
Insight Protocols — Event-Driven Insight Persistence
====================================================

Protocol Responsibilities
--------------------------
    InsightBackendOperations — Persistence-layer operations consumed by
                               InsightStore (typed against self.backend).

Insights are graph nodes, not an EntityType: the backend speaks raw Neo4j
records over the ``(User)-[:HAS_INSIGHT]->(Insight)-[:ABOUT_ENTITY]->(Entity)``
shape, and ``InsightStore`` converts them to the ``PersistedInsight`` model.

**Why every row is ``dict[str, Any]`` — tier C, and tier B was tested first.**
The ``Any`` policy ranks "use a specific type" above "permanent boundary", so
``Neo4jProperties`` was tried on every signature here: **79 MyPy errors across
the two consumer files** (61 in ``insight_store.py``, 28 in
``user_context_builder.py``). The reason is structural, not incidental — these
dicts are *records*, not property dicts. A record's values are Cypher-alias
results, and four of these ten methods ``RETURN i``: a whole ``:Insight``
**node**, which ``InsightStore`` re-reads as ``dict(record["i"])``.
``Neo4jValue`` cannot describe a node (``dict()`` rejects it), and naming the
driver's ``Node`` class inside ``core/ports`` would be worse than ``Any``.

The remaining six methods are flat projections and *could* carry TypedDicts —
but a TypedDict return with no ``processor`` is an unchecked claim (SoC arc
PR 6, Codex round 3): a renamed Cypher alias would still type-check and read as
zero. Half-typing the port would advertise a shape nothing enforces. Each
signature therefore carries a ``# boundary:`` marker naming the row it actually
returns, which is also the alias contract with the Cypher.

Implementation: adapters/persistence/neo4j/insight_backend.py
See: /docs/patterns/ANY_USAGE_POLICY.md
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class InsightBackendOperations(Protocol):
    """Backend operations consumed by InsightStore.

    Signatures are lifted from ``InsightBackend`` itself, not from a wider
    protocol — the ISP slice is exactly the ten methods the store calls.
    """

    # ── CRUD ──────────────────────────────────────────────────────────────

    async def create_insight(
        self,
        params: dict[str, Any],  # boundary: 17 Cypher params, JSON fields pre-serialized
    ) -> Result[list[dict[str, Any]]]:  # boundary: one record, {uid}
        """Create an Insight node with User and Entity relationships."""
        ...

    async def get(
        self, uid: str, user_uid: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: {i} — whole :Insight node
        """Get a single insight by UID, only when owned by the requesting user (ADR-085 G6)."""
        ...

    async def get_active_insights(
        self,
        user_uid: str,
        domain: str | None,
        limit: int,
    ) -> Result[list[dict[str, Any]]]:  # boundary: {i} — whole :Insight node per row
        """Get active (non-dismissed, non-actioned, non-expired) insights for a user."""
        ...

    async def get_insights_for_entity(
        self,
        entity_uid: str,
        user_uid: str,
        include_dismissed: bool,
    ) -> Result[list[dict[str, Any]]]:  # boundary: {i} — whole :Insight node per row
        """Get insights related to a specific entity."""
        ...

    # ── Status updates ────────────────────────────────────────────────────

    async def dismiss_insight(
        self, uid: str, user_uid: str, notes: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: one record, {uid}
        """Mark an insight as dismissed."""
        ...

    async def mark_actioned(
        self, uid: str, user_uid: str, notes: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: one record, {uid}
        """Mark an insight as actioned."""
        ...

    # ── Maintenance ───────────────────────────────────────────────────────

    async def cleanup_expired(
        self,
    ) -> Result[list[dict[str, Any]]]:  # boundary: one record, {deleted_count}
        """Delete expired insights."""
        ...

    # ── Query / analytics ─────────────────────────────────────────────────

    async def get_insight_history(
        self,
        user_uid: str,
        history_type: str,
        limit: int,
    ) -> Result[list[dict[str, Any]]]:  # boundary: {i} — whole :Insight node per row
        """Get dismissed or actioned insights for the history page."""
        ...

    async def get_insight_stats(
        self, user_uid: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: one record, 6 counts + {domains}
        """Get aggregate statistics about a user's insights."""
        ...

    async def get_insight_counts_by_domain(
        self, user_uid: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: {domain, count} per row
        """Get counts of active insights grouped by domain."""
        ...


__all__ = ["InsightBackendOperations"]
