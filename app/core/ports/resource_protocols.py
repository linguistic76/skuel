"""
Resource Protocols - ISP Contract for Curated Content (ContentOrigin.CURATED)
=============================================================================

Backend-level protocol typing ``ResourceService.backend``: base CRUD from
``BackendOperations[Resource]`` plus the one reverse-citation traversal the
service issues. Everything else it calls (``get``, ``list``) is inherited.

See: /docs/patterns/BACKEND_OPERATIONS_ISP.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from core.ports.base_protocols import BackendOperations
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.resource.resource import Resource  # noqa: F401
    from core.models.type_hints import Neo4jProperties


class ResourceBackendOperations(BackendOperations["Resource"], Protocol):
    """Backend operations for Resource — base CRUD + the reverse-citation read.

    Implementation: ResourceBackend (backends/misc_backends.py)
    Consumer: ResourceService.__init__
    """

    async def get_citing_entities(self, resource_uid: str) -> Result[list[Neo4jProperties]]:
        """The Kus / PathSteps that cite this Resource.

        One row per citation edge, each carrying the citing entity's uid, title
        and entity_type plus the edge's locator (null for a whole-work citation).

        Backend: ResourceBackend.get_citing_entities.
        """
        ...
