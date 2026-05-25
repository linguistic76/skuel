"""
PS Engagement Backend Protocol
==============================

Persistence port for the PathStep engagement lifecycle (ADR-059). All Cypher for
the 4-transition lifecycle (publish / engage / complete / abandon) plus its reads
lives below the boundary in
``adapters/persistence/neo4j/ps_engagement_backend.py``; ``PsEngagementService``
and its private helpers (``_EngagementGateway``, ``_TemplateLoader``) depend on
this port and keep only orchestration + domain reconstruction.

Methods return raw property-dict rows; callers reconstruct domain objects
(``Engagement``, ``TemplateBundle``, ``ReviewItem``) above the boundary.

See: /docs/decisions/ADR-044-neo4j-committed-architectural-choice.md
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class PsEngagementOperations(Protocol):
    """Cypher operations for the PathStep engagement lifecycle."""

    # ENGAGED_WITH edge
    async def find_active_engagement(
        self, student_uid: str, ps_uid: str
    ) -> Result[list[dict[str, Any]]]: ...
    async def list_engaged_edges(self, student_uid: str) -> Result[list[dict[str, Any]]]: ...
    async def create_engagement_edge(
        self, student_uid: str, ps_uid: str, since: str
    ) -> Result[list[dict[str, Any]]]: ...
    async def mark_engagement_terminal(
        self, student_uid: str, ps_uid: str, new_state: str, timestamp_field: str, ts: str
    ) -> Result[list[dict[str, Any]]]: ...

    # Template attachment reads
    async def fetch_template_uids(
        self, ps_uid: str, rel_value: str
    ) -> Result[list[dict[str, Any]]]: ...

    # PathStep status (T1 publish)
    async def set_pathstep_published(
        self, ps_uid: str, status: str, updated_at: str
    ) -> Result[list[dict[str, Any]]]: ...

    # Spawned-instance lifecycle (T3 complete / T4 abandon)
    async def delete_instance(
        self, instance_uid: str, operation: str
    ) -> Result[list[dict[str, Any]]]: ...
    async def mark_instance_owned(
        self, instance_uid: str, updated_at: str
    ) -> Result[list[dict[str, Any]]]: ...

    # Reads over spawned instances
    async def fetch_auto_complete_siblings(
        self, student_uid: str, instance_uid: str
    ) -> Result[list[dict[str, Any]]]: ...
    async def list_review_items(
        self, student_uid: str, ps_uid: str
    ) -> Result[list[dict[str, Any]]]: ...
    async def fetch_engaged_instances(
        self, student_uid: str, ps_uid: str
    ) -> Result[list[dict[str, Any]]]: ...
