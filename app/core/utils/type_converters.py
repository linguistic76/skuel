"""
Type Converter Utilities
========================

Protocol-based type conversion utilities for duck-typed objects.

These functions use Protocol-based type checking (isinstance with @runtime_checkable)
instead of hasattr() to provide type-safe duck typing.

Why these live here (not in protocols):
- Protocols define contracts (what an object CAN do)
- These utilities implement behavior (HOW to convert objects)
- Separation of concerns: protocols/*.py for contracts, utils/ for implementations

Usage:
    from core.utils.type_converters import to_dict, get_enum_value

    # Convert any dict-like object
    data = to_dict(some_object)

    # Extract enum value safely
    value = get_enum_value(some_enum_or_value)

Note:
    These functions are also available from core.ports for
    backward compatibility with existing code. Both locations use the
    same implementation.

Architecture Note:
    The protocols (EnumLike, PydanticModel, etc.) are defined in
    core.ports.base_protocols. This module imports them
    to provide protocol-based type checking without hasattr().
"""

import dataclasses
from typing import Any, Protocol, runtime_checkable

# ============================================================================
# Local Protocol Definitions (to avoid circular imports)
# ============================================================================
# These mirror the protocols in base_protocols.py but are defined here
# to avoid circular import issues. The behavior is identical.


@runtime_checkable
class _PydanticModel(Protocol):
    """Protocol for Pydantic models with model_dump method."""

    def model_dump(self, **kwargs: Any) -> dict[str, Any]: ...


@runtime_checkable
class _HasDict(Protocol):
    """Protocol for objects that can be converted to dict."""

    def dict(self) -> dict[str, Any]: ...


@runtime_checkable
class _HasToDict(Protocol):
    """Protocol for objects with to_dict method."""

    def to_dict(self) -> dict[str, Any]: ...


@runtime_checkable
class _Serializable(Protocol):
    """Protocol for objects that can be serialized to dict."""

    def serialize(self) -> dict[str, Any]: ...


@runtime_checkable
class _EnumLike(Protocol):
    """Protocol for enum-like objects with a value attribute."""

    value: Any


def to_dict(obj: Any) -> Any:
    """
    Universal converter to dictionary format.

    Uses Protocol-based type checking instead of hasattr() to determine
    the appropriate conversion method.

    Conversion priority:
    1. PydanticModel.model_dump() - Pydantic v2 models
    2. HasDict.dict() - Objects with dict() method
    3. HasToDict.to_dict() - Objects with to_dict() method
    4. Serializable.serialize() - Objects with serialize() method
    5. dataclass - Use dataclasses.asdict() for frozen dataclasses
    6. dict - Pass through unchanged
    7. list/tuple - Recursively convert elements
    8. Any - Return as-is (primitives, etc.)

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
    # Check protocols in order of preference (Protocol-based, no hasattr)
    if isinstance(obj, _PydanticModel):
        return obj.model_dump()
    elif isinstance(obj, _HasDict):
        return obj.dict()
    elif isinstance(obj, _HasToDict):
        return obj.to_dict()
    elif isinstance(obj, _Serializable):
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


def get_enum_value(obj: Any) -> Any:
    """
    Extract the value from an enum-like object.

    Uses Protocol-based type checking to safely extract .value from
    enum-like objects without using hasattr().

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
    # Protocol-based checking - no hasattr needed
    if isinstance(obj, _EnumLike):
        return obj.value
    return obj


def normalize_enum_str(value: Any, default: str = "") -> str:
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
    if isinstance(value, _EnumLike):
        return str(value.value).lower()
    return str(value).lower()


def get_enum_attr_str(obj: Any, attr: str, default: str = "") -> str:
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
    if isinstance(value, _EnumLike):
        return str(value.value).lower()
    return str(value).lower()


__all__ = [
    "get_enum_attr_str",
    "get_enum_value",
    "normalize_enum_str",
    "to_dict",
]
