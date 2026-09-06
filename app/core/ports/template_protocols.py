"""
Activity Template Protocols
============================

Route-facing protocol for the 6 PS-owned Activity Template services
(Task/Goal/Habit/Event/Choice/Principle). Captures only the methods called
from ``adapters/inbound/templates_ui.py`` so that the route layer can iterate
over a heterogeneous ``dict[str, ActivityTemplateOperations]`` without losing
type information — one method, since templates are vault-authored and the
route surface is the read-only PS panel.

Implemented by every ``_BaseTemplateService`` subclass in
``core/services/templates/__init__.py``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

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
class ActivityTemplateOperations(Protocol):
    """PS-attachment read surface shared by all 6 Activity Template services.

    Narrow by design (ISP): the one consumer is the read-only templates panel
    on the PS detail page, which asks each of the six services what is attached
    to a PathStep. Creation, update and attachment are the vault's job (an
    ``_tmpl.md`` file plus the step's ``{domain}_template_uids:`` frontmatter);
    the JSON CRUD calls the concrete services directly.

    Not generic in the template type — every member here returns property dicts
    read back from the graph, so no template model appears in the signature.

    See: /docs/guides/ACTIVITY_TEMPLATE_AUTHORING.md
    """

    async def list_for_pathstep(self, ps_uid: str) -> Result[list[dict[str, Any]]]:
        """List template property dicts attached to ``ps_uid``."""
        ...
