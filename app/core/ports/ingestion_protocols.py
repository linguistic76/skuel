"""
Ingestion Protocols
====================

Protocols for the IngestionBackend — ingestion audit trail and
incremental ingestion state tracking.

Implementation: adapters/persistence/neo4j/ingestion_backend.py
Consumers: IngestionHistoryService, IngestionTracker
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class IngestionBackendOperations(Protocol):
    """Backend operations for ingestion persistence.

    Covers two services:
    - IngestionHistoryService: audit trail for ingestion operations
    - IngestionTracker: incremental ingestion state (file hash/mtime)
    """

    # ================================================================
    # HISTORY — IngestionHistory node CRUD
    # ================================================================

    async def ensure_history_constraints(self) -> Result[list[dict[str, Any]]]: ...

    async def create_history_entry(
        self, params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]: ...

    async def update_history_entry(
        self, params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]: ...

    async def create_error_nodes(
        self, operation_id: str, errors: list[dict[str, Any]]
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_history(self, limit: int, offset: int) -> Result[list[dict[str, Any]]]: ...

    async def get_history_entry(self, operation_id: str) -> Result[list[dict[str, Any]]]: ...

    async def get_history_count(self) -> Result[list[dict[str, Any]]]: ...

    # ================================================================
    # TRACKER — IngestionMetadata node CRUD
    # ================================================================

    async def ensure_tracker_constraints(self) -> Result[list[dict[str, Any]]]: ...

    async def get_ingestion_metadata(self, paths: list[str]) -> Result[list[dict[str, Any]]]: ...

    async def update_ingestion_metadata(
        self, params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]: ...

    async def update_ingestion_metadata_batch(
        self, items: list[dict[str, Any]]
    ) -> Result[list[dict[str, Any]]]: ...

    async def delete_ingestion_metadata(self, paths: list[str]) -> Result[list[dict[str, Any]]]: ...
