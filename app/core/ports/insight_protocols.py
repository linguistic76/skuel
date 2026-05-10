"""
Insight Protocols
==================

Protocols for the InsightBackend — insight graph node CRUD operations.

Implementation: adapters/persistence/neo4j/insight_backend.py
Consumer: InsightStore
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class InsightBackendOperations(Protocol):
    """Backend operations for insight persistence."""

    # CRUD
    async def create_insight(self, params: dict[str, Any]) -> Result[list[dict[str, Any]]]: ...
    async def get(self, uid: str) -> Result[list[dict[str, Any]]]: ...

    async def get_active_insights(
        self, user_uid: str, domain: str | None, limit: int
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_insights_for_entity(
        self, entity_uid: str, user_uid: str, include_dismissed: bool
    ) -> Result[list[dict[str, Any]]]: ...

    # Status updates
    async def dismiss_insight(
        self, uid: str, user_uid: str, notes: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def mark_actioned(
        self, uid: str, user_uid: str, notes: str
    ) -> Result[list[dict[str, Any]]]: ...

    # Maintenance
    async def cleanup_expired(self) -> Result[list[dict[str, Any]]]: ...

    # Query / analytics
    async def get_insight_history(
        self, user_uid: str, history_type: str, limit: int
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_insight_stats(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...

    async def get_insight_counts_by_domain(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...
