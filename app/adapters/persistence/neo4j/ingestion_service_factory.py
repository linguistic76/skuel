"""
UnifiedIngestionService Composition Factory
===========================================

Builds a :class:`~core.services.ingestion.UnifiedIngestionService` together with
its two Neo4j backends from a single ``driver``.

The service depends on the ``IngestionWriteBackend`` / ``BulkUpsertBackend`` ports
(injected) and never imports the adapter itself (ADR-044 / SKUEL022). This factory
is the one place that wires the concrete backends to the service — it lives below
the hexagonal boundary, where importing both the adapter backends and the core
service is the correct dependency direction (adapter → core).

Usage:
    from adapters.persistence.neo4j.ingestion_service_factory import (
        make_unified_ingestion_service,
    )

    service = make_unified_ingestion_service(driver, chunking_service=chunking)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.services.ingestion import UnifiedIngestionService


def make_unified_ingestion_service(driver: AsyncDriver, **kwargs: Any) -> UnifiedIngestionService:
    """Build a UnifiedIngestionService wired with its Neo4j backends.

    Args:
        driver: Neo4j async driver. Used only to construct the write + bulk-upsert
            backends; the service never touches the driver directly.
        **kwargs: Forwarded verbatim to ``UnifiedIngestionService`` (e.g.
            ``default_user_uid``, ``chunking_service``, ``content_adapter``,
            ``event_bus``, ``ingestion_backend``, ``user_service``).

    Returns:
        A fully-wired UnifiedIngestionService.
    """
    from adapters.persistence.neo4j.bulk_upsert_backend import BulkUpsertBackend
    from adapters.persistence.neo4j.ingestion_write_backend import IngestionWriteBackend
    from core.services.ingestion import UnifiedIngestionService

    return UnifiedIngestionService(
        write_backend=IngestionWriteBackend(driver),
        bulk_backend=BulkUpsertBackend(driver),
        **kwargs,
    )
