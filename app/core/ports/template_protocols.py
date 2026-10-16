"""
Activity Template Protocols
============================

Route-facing protocol for the 6 PS-owned Activity Template services
(Task/Goal/Habit/Event/Choice/Principle), plus the persistence port their one
read delegates to. Templates are vault-authored, so both are read-only.

Implemented by every ``_BaseTemplateService`` subclass in
``core/services/templates/__init__.py``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.utils.result_simplified import Result


@runtime_checkable
class TemplateAttachmentOperations(Protocol):
    """Persistence port for the PS→Activity-Template edge read.

    The 6 Activity Template services delegate their read here so the Cypher lives
    below the hexagonal boundary (ADR-044). ``edge_name`` is a typed
    ``RelationshipName`` (one of the ``HAS_*_TEMPLATE`` members) and
    ``template_label`` the matching template ``NeoLabel``, both supplied by the
    service — the enums, not caller discipline, keep the interpolation
    injection-safe. The read binds both ends by kind: the source is a PathStep and
    the far end carries ``template_label``. Read-only: the content-vault sync is
    the one writer of these edges. Implemented by
    ``adapters/persistence/neo4j/template_attachment_backend.py``.
    """

    async def list_for_pathstep(
        self, ps_uid: str, edge_name: RelationshipName, template_label: NeoLabel
    ) -> Result[list[dict[str, Any]]]:
        """Return ``props`` rows for the ``template_label`` nodes ``ps_uid`` attaches."""
        ...


@runtime_checkable
class ActivityTemplateOperations(Protocol):
    """The read surface of all 6 Activity Template services — the one type a
    consumer holds.

    Creation, update and attachment are the vault's job (an ``_tmpl.md`` file plus
    the step's ``{domain}_template_uids:`` frontmatter; ADR-091 S8). The concrete
    services still inherit ``BaseService``'s generic writers, so no consumer holds
    the concrete class: the ``Services`` container fields and the templates panel
    on the PS detail page type every template service as this protocol, and no
    writer is reachable by type.

    Not generic in the template type — every member here returns property dicts
    read back from the graph, so no template model appears in the signature.

    See: /docs/guides/ACTIVITY_TEMPLATE_AUTHORING.md
    """

    async def list_for_pathstep(self, ps_uid: str) -> Result[list[dict[str, Any]]]:
        """List template property dicts attached to ``ps_uid``."""
        ...
