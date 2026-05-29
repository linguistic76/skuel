"""Typed scalar extractors for Neo4j property bags.

Neo4j returns node/relationship properties as a loosely-typed
``Neo4jProperties`` mapping (``str | int | float | bool | list | date |
datetime | None``). Service code that reads a *known-shape* value out of that
bag must narrow it to the concrete type its consumer expects. These helpers are
the single narrowing seam at the backend-result boundary: they raise
``TypeError`` (a member of ``DATA_CONVERSION_EXCEPTIONS``) when a value is
present but the wrong type, turning silent schema drift into a fail-fast at the
read boundary instead of a mismatched ``arg-type`` deep in a consumer.

This generalises the CLAUDE.md doctrine — "narrow Neo4j property types with
``int()``/``float()``/``str()`` casts before arithmetic" — from arithmetic to
*all* typed consumers (``str``, ``UserUID``, ``list[str]``). Prefer one
extractor call per backend-result field over an inline cast at every consumer.

Sites that already wrap their backend calls in ``DATA_CONVERSION_EXCEPTIONS`` /
``Exception`` safety-nets translate the raised ``TypeError`` to a
``Result.fail(Errors.database(...))`` automatically.

See: ``/docs/patterns/NEO4J_QUERY_TIMEOUT.md`` (sibling boundary helpers),
``core/utils/neo4j_mapper.py`` (full node↔dataclass mapping).
"""

from __future__ import annotations

from core.models.type_hints import Neo4jProperties, TypeConverter, UserUID

_MISSING = object()


def neo4j_str(props: Neo4jProperties, key: str, default: str | None = None) -> str:
    """Narrow a Neo4j property to ``str``.

    Returns ``default`` when the key is absent or maps to ``None`` (and a
    default was supplied). Raises ``TypeError`` if the value is present but not
    a string, or if it is missing/None and no default was given.
    """
    value = props.get(key, _MISSING)
    if value is _MISSING or value is None:
        if default is not None:
            return default
        raise TypeError(f"Neo4j property {key!r} is missing or None (expected str)")
    if not isinstance(value, str):
        raise TypeError(f"Neo4j property {key!r} has type {type(value).__name__}, expected str")
    return value


def neo4j_user_uid(props: Neo4jProperties, key: str) -> UserUID:
    """Narrow a Neo4j property to a validated ``UserUID``.

    Raises ``TypeError`` if the value is missing/None/non-string, and
    ``ValueError`` (via ``TypeConverter.to_user_uid``) if it is not the
    canonical ``user_<name>`` form.
    """
    return TypeConverter.to_user_uid(neo4j_str(props, key))


def neo4j_str_list(props: Neo4jProperties, key: str) -> list[str]:
    """Narrow a Neo4j property to ``list[str]``.

    Absent/None yields an empty list. Raises ``TypeError`` if the value is a
    non-list scalar or a list containing a non-string element.
    """
    value = props.get(key, _MISSING)
    if value is _MISSING or value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"Neo4j property {key!r} has type {type(value).__name__}, expected list")
    for item in value:
        if not isinstance(item, str):
            raise TypeError(
                f"Neo4j property {key!r} contains {type(item).__name__}, expected list[str]"
            )
    return value


__all__ = ["neo4j_str", "neo4j_str_list", "neo4j_user_uid"]
