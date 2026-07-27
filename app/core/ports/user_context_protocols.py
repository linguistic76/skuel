"""
User Context Protocols — MEGA / CONSOLIDATED Query Execution
============================================================

Protocol Responsibilities
--------------------------
    UserContextQueryOperations — Persistence-layer query execution consumed by
                                 UserContextBuilder (and passed through by the
                                 UserService facade that constructs it).

The MEGA-QUERY and CONSOLIDATED_QUERY live below the boundary (ADR-044); the
executor that runs them is built at the composition root and injected, so no
``core/`` module imports the adapter (SKUEL022 / SKUEL023).

**ISP slice, not the whole executor.** ``UserContextQueryExecutor`` also exposes
``fetch_current_ps_uids``; no consumer calls it, so it is deliberately absent
here — signatures are lifted from the implementation, and the slice is exactly
what ``UserContextBuilder`` uses.

Implementation: adapters/persistence/neo4j/user_context_queries.py
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from core.models.type_hints import UserUID
from core.ports.query_types import CurrentPathStepItem
from core.utils.result_simplified import Result


@runtime_checkable
class UserContextQueryOperations(Protocol):
    """Query execution consumed by UserContextBuilder."""

    async def execute_mega_query(
        self,
        user_uid: UserUID,
        min_confidence: float = 0.7,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> Result[dict[str, Any]]:
        """Run the MEGA-QUERY — ``uids`` + ``entities`` + ``rich`` in one round-trip."""
        ...

    async def execute_consolidated_query(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """Run the standard-depth CONSOLIDATED_QUERY (UIDs only)."""
        ...

    async def fetch_current_path_steps(
        self, user_uid: UserUID
    ) -> Result[list[CurrentPathStepItem]]:
        """Fetch path steps the user is actively studying (IN_PROGRESS)."""
        ...

    async def fetch_user_groups(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """Fetch group memberships, ownerships, and group-shared curriculum (ADR-053)."""
        ...


__all__ = ["UserContextQueryOperations"]
