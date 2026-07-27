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

**Why three returns are ``dict[str, Any]`` — tier C, with tier B tested first.**
``Neo4jProperties`` was tried on these signatures and produced **28 MyPy errors
in ``user_context_builder.py`` alone** (79 across both new ports' consumers).
These are not property dicts: the MEGA-QUERY returns one deeply nested
``{uids, entities, rich}`` object spanning every domain, and ``fetch_user_groups``
returns five heterogeneous collections. ``Neo4jValue`` describes a scalar
property, which is a different thing. ``fetch_current_path_steps`` is the
counter-example that proves the rest is not laziness — it *is* flat, so it
returns a real ``CurrentPathStepItem`` TypedDict, which the implementation
**constructs** row by row rather than merely annotating.

Implementation: adapters/persistence/neo4j/user_context_queries.py
See: /docs/patterns/ANY_USAGE_POLICY.md
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
    ) -> Result[dict[str, Any]]:  # boundary: nested {uids, entities, rich}, all domains
        """Run the MEGA-QUERY — ``uids`` + ``entities`` + ``rich`` in one round-trip."""
        ...

    async def execute_consolidated_query(
        self, user_uid: UserUID
    ) -> Result[dict[str, Any]]:  # boundary: per-domain UID lists, keyed by domain
        """Run the standard-depth CONSOLIDATED_QUERY (UIDs only)."""
        ...

    async def fetch_current_path_steps(
        self, user_uid: UserUID
    ) -> Result[list[CurrentPathStepItem]]:
        """Fetch path steps the user is actively studying (IN_PROGRESS)."""
        ...

    async def fetch_user_groups(
        self, user_uid: UserUID
    ) -> Result[dict[str, Any]]:  # boundary: 2 GroupSummary lists + 3 UID lists
        """Fetch group memberships, ownerships, and group-shared curriculum (ADR-053)."""
        ...


__all__ = ["UserContextQueryOperations"]
