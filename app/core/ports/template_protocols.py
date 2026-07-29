"""
Activity Template Protocols
============================

Route-facing protocol for the 6 PS-owned Activity Template services
(Task/Goal/Habit/Event/Choice/Principle). Captures only the methods called
from ``adapters/inbound/templates_ui.py`` so that the route layer can iterate
over a heterogeneous ``dict[str, ActivityTemplateOperations]`` without losing
type information.

Implemented by every ``_BaseTemplateService`` subclass in
``core/services/templates/__init__.py``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.models.protocols import DomainModelProtocol
from core.models.relationship_names import RelationshipName
from core.utils.result_simplified import Result


@runtime_checkable
class TemplateAttachmentOperations(Protocol):
    """Persistence port for PS↔Activity-Template edge Cypher.

    The 6 Activity Template services delegate their attach/detach/list Cypher
    here so it lives below the hexagonal boundary (ADR-044). ``edge_name`` is a
    typed ``RelationshipName`` (one of the ``HAS_*_TEMPLATE`` members) supplied by
    the service — the enum, not caller discipline, is what keeps the interpolation
    injection-safe. Implemented by
    ``adapters/persistence/neo4j/template_attachment_backend.py``.
    """

    async def attach(
        self, ps_uid: str, template_uid: str, edge_name: RelationshipName
    ) -> Result[list[dict[str, Any]]]:
        """Attach a template to a PathStep under ``edge_name``; idempotent.

        One row per attached pair — empty when either endpoint is missing, which
        is how the caller tells "attached" apart from "no such node".
        """
        ...

    async def detach(
        self, ps_uid: str, template_uid: str, edge_name: RelationshipName
    ) -> Result[list[dict[str, Any]]]:
        """Detach a template from a PathStep; return a ``removed`` count row.

        Idempotent — detaching an unattached pair reports zero removed.
        """
        ...

    async def list_for_pathstep(
        self, ps_uid: str, edge_name: RelationshipName
    ) -> Result[list[dict[str, Any]]]:
        """Return ``props`` rows for templates attached to ``ps_uid`` via ``edge_name``."""
        ...


@runtime_checkable
class ActivityTemplateOperations[T: DomainModelProtocol](Protocol):
    """CRUD + PS-attachment surface shared by all 6 Activity Template services.

    Generic in the template type, because the implementers already are:
    every one is a ``_BaseTemplateService[XTemplate]``, so its ``create``
    really is ``create(entity: TaskTemplate) -> Result[TaskTemplate]``.
    The heterogeneity is the route layer's — ``templates_ui.py`` holds a
    domain-keyed dict — so the ``Any`` belongs at that one consumer, not
    in the port. (Neither a 6-way union nor the shared ``DomainModelProtocol``
    bound works in its place: the parameter position is contravariant, and
    both make every concrete ``create`` a conformance error.)
    """

    async def create(self, entity: T) -> Result[T]:
        """Create a template node."""
        ...

    async def get(self, uid: str) -> Result[T]:
        """Fetch a template by UID. Returns Result[Template | None]."""
        ...

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[T]:
        """Apply a partial update."""
        ...

    async def attach_to_pathstep(self, ps_uid: str, template_uid: str) -> Result[bool]:
        """Attach this template to a PathStep; idempotent, NotFound if either is missing."""
        ...

    async def detach_from_pathstep(self, ps_uid: str, template_uid: str) -> Result[bool]:
        """Detach this template from a PathStep; False when it was not attached."""
        ...

    async def list_for_pathstep(self, ps_uid: str) -> Result[list[dict[str, Any]]]:
        """List template property dicts attached to ``ps_uid``."""
        ...
