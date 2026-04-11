"""
Knowledge Domain Protocols
==========================

Protocol for the KnowledgeDomainBackend — read-only queries for
KnowledgeDomain taxonomy nodes.

Implementation: adapters/persistence/neo4j/knowledge_domain_backend.py
Consumer: KnowledgeDomainService
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class KnowledgeDomainBackendOperations(Protocol):
    """Backend operations for KnowledgeDomain taxonomy queries."""

    async def get_all_domains(self) -> Result[list[dict[str, Any]]]: ...

    async def get_ku_uids_in_domain(self, domain_uid: str) -> Result[list[dict[str, Any]]]: ...

    async def get_domains_for_ku(self, ku_uid: str) -> Result[list[dict[str, Any]]]: ...
