"""
Type Converter Utilities
========================

THE canonical home of SKUEL's duck-typed conversion layer: five
`@runtime_checkable` protocols describing the shapes objects convert
through, and the helpers that perform the conversions.

This module MUST import only the standard library. That constraint is
load-bearing: it makes the module a true import leaf, so any module —
including `core/ports` and `core/models` — can import from it without
ever creating an import cycle. (The previous arrangement duplicated the
protocols and helpers between here and `core.ports.base_protocols` to
dodge a cycle, and the copies drifted. The leaf property is what makes
the single copy possible; do not add first-party imports here.)

Usage:
    from core.utils.type_converters import to_dict, get_enum_value

    # Convert any dict-like object
    data = to_dict(some_object)

    # Extract enum value safely
    value = get_enum_value(some_enum_or_value)
"""

import dataclasses
import math
from typing import Any, Protocol, overload, runtime_checkable


@runtime_checkable
class PydanticModel(Protocol):
    """Protocol for Pydantic models with model_dump method."""

    def model_dump(self, *, exclude_none: bool = False) -> dict[str, Any]:
        """Dump model to dictionary.

        ``exclude_none`` is the whole keyword surface the two consumers use
        (``ConversionServiceV2.create_to_pure`` passes it; ``to_dict`` below
        calls it bare). A real ``pydantic.BaseModel`` still satisfies this —
        its extra keywords all have defaults.
        """
        ...


@runtime_checkable
class HasDict(Protocol):
    """Protocol for objects that can be converted to dict."""

    def dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        ...


@runtime_checkable
class HasToDict(Protocol):
    """Protocol for objects with to_dict method."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        ...


@runtime_checkable
class Serializable(Protocol):
    """Protocol for objects that can be serialized to dict."""

    def serialize(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        ...


@runtime_checkable
class EnumLike[V = str | int | float](Protocol):
    """Protocol for enum-like objects with a value attribute.

    ``value`` is a read-only property, not a mutable attribute: ``Enum.value``
    is a descriptor, so a settable-attribute protocol does not match an enum
    statically (it only ever matched at runtime, where ``runtime_checkable``
    just tests for the name). Parameterising it is what lets
    ``get_enum_value`` hand the member's value type back to its caller; the
    ``str | int | float`` default keeps bare ``EnumLike`` narrowing as before.
    """

    @property
    def value(self) -> V: ...


def to_dict(obj: object) -> object:
    """
    Universal converter to dictionary format.

    Every branch is an isinstance narrow, so ``object`` accepts exactly what
    ``Any`` did while forbidding unchecked attribute access inside. The return
    is ``object`` because the arms genuinely differ — ``dict[str, Any]`` from
    the four protocol branches and the dataclass branch, a list from the
    sequence branch, and the input untouched otherwise.

    Conversion priority:
    1. PydanticModel.model_dump() - Pydantic v2 models
    2. HasDict.dict() - Objects with dict() method
    3. HasToDict.to_dict() - Objects with to_dict() method
    4. Serializable.serialize() - Objects with serialize() method
    5. dataclass - Use dataclasses.asdict() for frozen dataclasses
    6. dict - Pass through unchanged
    7. list/tuple - Recursively convert elements
    8. Anything else - Return as-is (primitives, etc.)

    A dataclass that also defines ``to_dict()`` takes the HasToDict branch:
    the protocol branches outrank the structural dataclass check so a type's
    own conversion method always wins over field-dump reflection.

    Args:
        obj: Object to convert to dictionary format

    Returns:
        Dictionary representation of the object, or list of dicts for sequences

    Examples:
        >>> from pydantic import BaseModel
        >>> class User(BaseModel):
        ...     name: str
        >>> to_dict(User(name="Alice"))
        {'name': 'Alice'}

        >>> to_dict([User(name="Alice"), User(name="Bob")])
        [{'name': 'Alice'}, {'name': 'Bob'}]

        >>> to_dict({"key": "value"})
        {'key': 'value'}
    """
    if isinstance(obj, PydanticModel):
        return obj.model_dump()
    elif isinstance(obj, HasDict):
        return obj.dict()
    elif isinstance(obj, HasToDict):
        return obj.to_dict()
    elif isinstance(obj, Serializable):
        return obj.serialize()
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        # Handle frozen dataclasses (SKUEL domain models)
        return dataclasses.asdict(obj)
    elif isinstance(obj, dict):
        return obj
    elif isinstance(obj, list | tuple):
        return [to_dict(item) for item in obj]
    else:
        # Fallback for primitive types
        return obj


@overload
def get_enum_value[V](obj: EnumLike[V]) -> V: ...
@overload
def get_enum_value[T](obj: T) -> T: ...
def get_enum_value(obj: object) -> object:
    """
    Extract the value from an enum-like object.

    Two overloads rather than one signature: callers that pass an enum need
    the member's value type back (``GoalCreated.domain: str | None`` and
    ``GraphContext.query_intent: str`` are both fed from here), and callers
    that pass a plain value need it returned unchanged.

    Args:
        obj: Object to extract value from (enum or plain value)

    Returns:
        The .value if obj is enum-like, otherwise obj unchanged

    Examples:
        >>> from enum import Enum
        >>> class Color(Enum):
        ...     RED = "red"
        >>> get_enum_value(Color.RED)
        'red'

        >>> get_enum_value("already_a_string")
        'already_a_string'

        >>> get_enum_value(42)
        42

    Note:
        This is useful when you need to serialize enums or when working
        with APIs that expect primitive values instead of enum objects.
    """
    if isinstance(obj, EnumLike):
        return obj.value
    return obj


def normalize_enum_str(value: object, default: str = "") -> str:
    """Normalize an enum or string value to a clean lowercase string.

    Replaces the duplicated ``str(val).lower().replace("enumprefix.", "")``
    pattern scattered across UI and service code.

    Args:
        value: An enum instance, string, or None.
        default: Value to return when *value* is None.

    Returns:
        Lowercase string — the enum's ``.value`` when applicable.

    Examples:
        >>> from enum import Enum
        >>> class GoalStatus(str, Enum):
        ...     ACTIVE = "active"
        >>> normalize_enum_str(GoalStatus.ACTIVE)
        'active'

        >>> normalize_enum_str("Pending")
        'pending'

        >>> normalize_enum_str(None, "unknown")
        'unknown'
    """
    if value is None:
        return default
    if isinstance(value, EnumLike):
        return str(value.value).lower()
    return str(value).lower()


def finite_float(
    value: Any,  # boundary: untyped Neo4j property — str, float, list and None all arrive
) -> float | None:
    """Narrow a Neo4j-sourced scalar to a float, or ``None`` if it is not a real number.

    Neo4j properties carry no declared type and nothing coerces on the way in: vault
    ingestion copies frontmatter into node properties unchecked
    (``core/services/ingestion/preparer.py``), so a quoted ``progress_percentage: "40"``
    arrives as ``str`` and YAML's ``.nan`` / ``.inf`` arrive as non-finite floats. Both
    then blow up in arithmetic — ``TypeError`` for the string, ``ValueError`` /
    ``OverflowError`` from ``round()`` for the others.

    The predicate is total rather than a list of the failures seen so far: ``float()``
    either raises or yields a float, and a float is finite, ±inf or nan — so "converts
    and is finite" admits exactly the values arithmetic cannot fail on. Callers decide
    the policy for ``None``: a ``Result.fail`` where there is a channel for it, a
    neutral default where there is not.

    ``Any`` is the honest annotation rather than a scalar union: the parameter's whole
    job is to absorb whatever the property store hands back, and a ``str | float | None``
    union would reject the ``list`` case this function is tested against.

    Args:
        value: Any stored scalar, typically read straight off a domain model field

    Returns:
        The value as a float, or None if it does not convert or is not finite

    Examples:
        >>> finite_float(40)
        40.0
        >>> finite_float("40")
        40.0
        >>> finite_float("forty") is None
        True
        >>> finite_float(float("nan")) is None
        True
        >>> finite_float(None) is None
        True
    """
    try:
        narrowed = float(value)
    except TypeError, ValueError:
        return None
    return narrowed if math.isfinite(narrowed) else None


def get_enum_attr_str(obj: object, attr: str, default: str = "") -> str:
    """Extract an attribute as a lowercase string, handling both enum and string values.

    Combines getattr + enum extraction + lowercase normalization into one call.
    Replaces duplicated domain-specific enum extractors across service facades.

    Args:
        obj: Object to extract attribute from
        attr: Attribute name to read
        default: Value to return if attribute is None or missing

    Returns:
        Lowercase string representation of the attribute value

    Examples:
        >>> from enum import Enum
        >>> class Status(Enum):
        ...     ACTIVE = "active"
        >>> from types import SimpleNamespace
        >>> obj = SimpleNamespace(status=Status.ACTIVE)
        >>> get_enum_attr_str(obj, "status")
        'active'

        >>> get_enum_attr_str(SimpleNamespace(status="Pending"), "status")
        'pending'

        >>> get_enum_attr_str(SimpleNamespace(), "status", "unknown")
        'unknown'
    """
    value = getattr(obj, attr, None)
    if value is None:
        return default
    if isinstance(value, EnumLike):
        return str(value.value).lower()
    return str(value).lower()


__all__ = [
    "EnumLike",
    "HasDict",
    "HasToDict",
    "PydanticModel",
    "Serializable",
    "finite_float",
    "get_enum_attr_str",
    "get_enum_value",
    "normalize_enum_str",
    "to_dict",
]
