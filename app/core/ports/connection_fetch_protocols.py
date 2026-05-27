"""
Connection-Fetch Protocols
==========================

Port for cross-domain connection fetching used by Activity Domain list/detail
pages. Authors + executes the parameterized Cypher below the hexagonal boundary
so ``core/utils/`` stays Cypher-free (ADR-044).

Implementation: adapters/persistence/neo4j/connection_fetch_backend.py
Consumer: adapters/inbound/activity_ui_factory.py (via ActivityUIConfig.backend)

The configs live in core (pure data): core/utils/connection_configs.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from core.utils.connection_configs import ConnectionConfig


@runtime_checkable
class ConnectionFetchOperations(Protocol):
    """Fetch cross-domain connections and curriculum origin for activities."""

    async def fetch_entity_connections(
        self, config: ConnectionConfig, entity_uids: list[str]
    ) -> dict[str, list[dict[str, str]]]:
        """Batch-fetch cross-domain connections for a list of entities.

        Returns a map of ``entity_uid -> list of connection dicts``, each with
        keys ``rel_type``, ``connected_uid``, ``title``, ``connected_type``.
        Empty dict on no input or query failure (page-resilient).
        """
        ...

    async def fetch_source_pathstep(self, ps_uid: str) -> dict[str, str] | None:
        """Resolve a spawned activity's ``source_path_step_uid`` to its PathStep.

        Returns ``{"uid", "title"}`` or ``None`` if the PathStep is missing or
        the lookup fails.
        """
        ...
