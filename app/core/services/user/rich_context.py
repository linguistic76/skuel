"""
Context-First rich-context accessors
====================================

THE shared access path for ``UserContext.entities_rich`` — the MEGA-QUERY's
``{"entity": {...node properties...}, "graph_context": {...}}`` items.

Context-First Pattern: UserContext is the source of truth for user state.
Services consume context data when available and fall back to Neo4j only when
an entity is not in context. Before Tier 6 each domain progress/planning
service hand-rolled its own accessor trio plus a ``_dict_to_<domain>``
converter — already drifted (None-guards, enum defaults, legacy key
fallbacks). This module is the single implementation, parameterized by domain
key and DTO/model classes; conversion goes through the same DTO layer
(``dto_class.from_dict`` → ``model_class.from_dto``) the Neo4j fallback paths
use, so both paths produce identical models.

See: /docs/architecture/UNIFIED_USER_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.dto_converters import to_domain_model

if TYPE_CHECKING:
    from core.models.protocols import DomainModelProtocol, DTOProtocol
    from core.ports.query_types import RichEntityItem
    from core.services.user import UserContext


def find_rich_entity_item(
    user_context: UserContext | None, domain_key: str, uid: str
) -> RichEntityItem | None:
    """Return the full rich item (entity + graph_context) for ``uid``, or None.

    Args:
        user_context: User's context; None forces the caller's Neo4j fallback.
        domain_key: entities_rich key ("tasks", "goals", "habits", "events", ...)
        uid: Entity UID to look up.
    """
    if user_context is None:
        return None
    for item in user_context.entities_rich.get(domain_key, []):
        entity = item.get("entity", {})
        if entity.get("uid") == uid:
            return item
    return None


def find_rich_graph_context(
    user_context: UserContext | None, domain_key: str, uid: str
) -> dict[str, Any] | None:
    """Return the non-empty ``graph_context`` dict for ``uid``, or None."""
    item = find_rich_entity_item(user_context, domain_key, uid)
    if item is None:
        return None
    graph_ctx = item.get("graph_context", {})
    return graph_ctx or None


def rich_entity_to_model[D: DTOProtocol, M: DomainModelProtocol](
    entity_dict: dict[str, Any] | None, dto_class: type[D], model_class: type[M]
) -> M | None:
    """Convert a raw rich-context entity dict to a domain model via the DTO layer.

    Returns None for empty/uid-less dicts. Copies the dict before conversion —
    ``from_dict`` parses in place, and the rich-context cache must keep its raw
    (ISO-string) shape for other consumers.
    """
    if not entity_dict or not entity_dict.get("uid"):
        return None
    return to_domain_model(dict(entity_dict), dto_class, model_class)


def get_model_from_rich_context[D: DTOProtocol, M: DomainModelProtocol](
    user_context: UserContext | None,
    domain_key: str,
    uid: str,
    dto_class: type[D],
    model_class: type[M],
) -> M | None:
    """Context-First entity lookup: rich-context hit → domain model, else None.

    The single replacement for the per-domain ``_get_<domain>_from_rich_context``
    + ``_dict_to_<domain>`` pairs.
    """
    item = find_rich_entity_item(user_context, domain_key, uid)
    if item is None:
        return None
    return rich_entity_to_model(item.get("entity", {}), dto_class, model_class)


def rich_graph_uids(graph_ctx: dict[str, Any], key: str) -> list[str]:
    """Extract non-empty ``uid`` values from a graph_context neighbor list."""
    return [n["uid"] for n in graph_ctx.get(key, []) if n and n.get("uid")]
