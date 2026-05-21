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

from core.utils.result_simplified import Result


@runtime_checkable
class ActivityTemplateOperations(Protocol):
    """CRUD + PS-attachment surface shared by all 6 Activity Template services.

    Entity type is intentionally ``Any`` — the route layer pulls services from
    a domain-keyed dict, so the concrete TemplateType is not statically known.
    """

    async def create(self, entity: Any) -> Result[Any]:
        """Create a template node."""
        ...

    async def get(self, uid: str) -> Result[Any]:
        """Fetch a template by UID. Returns Result[Template | None]."""
        ...

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[Any]:
        """Apply a partial update."""
        ...

    async def attach_to_pathstep(self, ps_uid: str, template_uid: str) -> Result[bool]:
        """MERGE the HAS_*_TEMPLATE edge between PS and template."""
        ...

    async def detach_from_pathstep(self, ps_uid: str, template_uid: str) -> Result[bool]:
        """DELETE the HAS_*_TEMPLATE edge."""
        ...

    async def list_for_pathstep(self, ps_uid: str) -> Result[list[dict[str, Any]]]:
        """List template property dicts attached to ``ps_uid``."""
        ...
