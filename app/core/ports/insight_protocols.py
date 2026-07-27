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

**Why the row type is ``dict[str, Any]`` and not a TypedDict.** Four of these
ten methods (``get``, ``get_active_insights``, ``get_insights_for_entity``,
``get_insight_history``) ``RETURN i`` — a whole ``:Insight`` node under one key,
which the store re-reads as ``dict(record["i"])``. There is no flat projection
to type. The other six are flat, but a TypedDict return that is not *constructed*
by a ``processor`` is an unchecked claim (SoC arc PR 6, Codex round 3): a renamed
Cypher alias would still type-check and read as zero. So this port mirrors the
implementation exactly rather than advertising a shape nothing enforces.

Implementation: adapters/persistence/neo4j/insight_backend.py
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

    async def create_insight(self, params: dict[str, Any]) -> Result[list[dict[str, Any]]]:
        """Create an Insight node with User and Entity relationships."""
        ...

    async def get(self, uid: str) -> Result[list[dict[str, Any]]]:
        """Get a single insight by UID (one record, whole node under key ``i``)."""
        ...

    async def get_active_insights(
        self,
        user_uid: str,
        domain: str | None,
        limit: int,
    ) -> Result[list[dict[str, Any]]]:
        """Get active (non-dismissed, non-actioned, non-expired) insights for a user."""
        ...

    async def get_insights_for_entity(
        self,
        entity_uid: str,
        user_uid: str,
        include_dismissed: bool,
    ) -> Result[list[dict[str, Any]]]:
        """Get insights related to a specific entity."""
        ...

    # ── Status updates ────────────────────────────────────────────────────

    async def dismiss_insight(
        self, uid: str, user_uid: str, notes: str
    ) -> Result[list[dict[str, Any]]]:
        """Mark an insight as dismissed."""
        ...

    async def mark_actioned(
        self, uid: str, user_uid: str, notes: str
    ) -> Result[list[dict[str, Any]]]:
        """Mark an insight as actioned."""
        ...

    # ── Maintenance ───────────────────────────────────────────────────────

    async def cleanup_expired(self) -> Result[list[dict[str, Any]]]:
        """Delete expired insights, returning ``deleted_count``."""
        ...

    # ── Query / analytics ─────────────────────────────────────────────────

    async def get_insight_history(
        self,
        user_uid: str,
        history_type: str,
        limit: int,
    ) -> Result[list[dict[str, Any]]]:
        """Get dismissed or actioned insights for the history page."""
        ...

    async def get_insight_stats(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get aggregate statistics about a user's insights."""
        ...

    async def get_insight_counts_by_domain(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get counts of active insights grouped by domain."""
        ...


__all__ = ["InsightBackendOperations"]
