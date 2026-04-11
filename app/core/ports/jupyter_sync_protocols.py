"""
Jupyter Sync Protocols
=======================

Protocols for the JupyterSyncBackend — Jupyter-Neo4j-Obsidian
bi-directional sync persistence operations.

Implementation: adapters/persistence/neo4j/jupyter_sync_backend.py
Consumer: JupyterNeo4jSync
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class JupyterSyncBackendOperations(Protocol):
    """Backend operations for Jupyter-Neo4j sync persistence."""

    # ================================================================
    # READ — Fetch content and relationships
    # ================================================================

    async def get_content_with_relationships(self, uid: str) -> Result[list[dict[str, Any]]]: ...

    async def get_conflict_state(self, uid: str) -> Result[list[dict[str, Any]]]: ...

    async def get_entities_needing_sync(
        self, uid: str | None, force: bool
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_entity_relationships(self, uid: str) -> Result[list[dict[str, Any]]]: ...

    # ================================================================
    # WRITE — Update content and metadata
    # ================================================================

    async def update_entity_from_jupyter(
        self, params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]: ...

    async def replace_relationships(
        self, uid: str, prerequisites: list[str], enables: list[str], related_to: list[str]
    ) -> Result[list[dict[str, Any]]]: ...

    async def track_change(
        self, uid: str, change_type: str, content_hash: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def mark_synced(self, uid: str) -> Result[list[dict[str, Any]]]: ...

    async def update_obsidian_hash(
        self, uid: str, hash_value: str
    ) -> Result[list[dict[str, Any]]]: ...
