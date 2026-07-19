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
``adapters/persistence/neo4j/neo4j_mapper.py`` (full node↔dataclass mapping, below the hexagonal boundary).
"""

from __future__ import annotations

import json
from contextlib import suppress
from typing import Any

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


# =============================================================================
# VALUE COERCION (moved from the node mapper in Tier 6 — the mapper now lives
# in adapters/persistence/neo4j/; these value-level helpers are the core-side
# seam for raw Cypher results and stay with the other scalar extractors)
# =============================================================================


def coerce_int(value: object, default: int = 0) -> int:
    """Coerce a Neo4j property (or any heterogeneous value) to ``int``.

    Neo4j records expose values as ``str | int | float | bool | list | datetime | None``.
    Passing such a value directly to ``int()`` trips mypy (``datetime`` / ``list``
    don't satisfy ``SupportsInt``) and can crash at runtime. This helper narrows
    the input and falls back to ``default`` for non-numeric shapes.

    Args:
        value: Raw value from a record / mixed-type dict.
        default: Fallback when ``value`` is ``None`` or non-numeric.

    Returns:
        Integer representation, or ``default``.
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except (ValueError, TypeError):  # fmt: skip
            return default
    return default


def coerce_float(value: object, default: float = 0.0) -> float:
    """Coerce a Neo4j property (or any heterogeneous value) to ``float``.

    Counterpart to :func:`coerce_int` for ``float`` conversion — see that
    function's docstring for rationale.

    Args:
        value: Raw value from a record / mixed-type dict.
        default: Fallback when ``value`` is ``None`` or non-numeric.

    Returns:
        Float representation, or ``default``.
    """
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except (ValueError, TypeError):  # fmt: skip
            return default
    return default


def parse_neo4j_json(value: Any, default: Any = None) -> Any:
    """Parse a JSON-encoded value from a Neo4j node property.

    Neo4j cannot store nested structures (dicts, lists of dicts), so they
    are stored as JSON strings.  This helper transparently handles the
    round-trip: if *value* is a JSON string it is parsed; if it is already
    a native Python type it is returned as-is; ``None`` / empty string
    returns *default*.

    Use this when consuming raw Cypher query results (custom queries that
    bypass ``from_neo4j_node``).

    Args:
        value: Raw value from a Neo4j record.
        default: Fallback when *value* is ``None``, empty, or unparseable.

    Returns:
        Parsed Python object, the original value, or *default*.
    """
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):  # fmt: skip
        return default


def deserialize_json_fields(data: dict[str, Any], *fields: str) -> dict[str, Any]:
    """Deserialize JSON-string fields **in place** on a Neo4j result dict.

    For services that run custom Cypher and get back raw node property
    dicts, this replaces the repetitive pattern::

        if isinstance(d.get("f"), str):
            d["f"] = json.loads(d["f"])

    Args:
        data: Mutable dict of node properties (modified in place).
        *fields: Names of fields that may be JSON-encoded strings.

    Returns:
        The same *data* dict (for chaining convenience).
    """
    for field in fields:
        val = data.get(field)
        if isinstance(val, str) and val:
            with suppress(json.JSONDecodeError, ValueError):
                data[field] = json.loads(val)
    return data
