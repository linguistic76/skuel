"""
Type Hints and Type Safety
===========================

Centralized type definitions for the entire system.
Provides NewType definitions, type aliases, and type guards
for improved type safety and code clarity.

Using NewType ensures that UIDs and other identifiers
cannot be accidentally mixed up.
"""

__version__ = "1.0"


from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    NewType,
    Protocol,
    TypeGuard,
    TypeVar,
    runtime_checkable,
)

if TYPE_CHECKING:
    from core.models.base_models_consolidated import BaseEntity
    from core.services.protocols.calendar_protocol import CalendarTrackable
    from core.utils.result_simplified import Result as _Result

    # Type alias for Result used at boundaries (avoids circular import)
    BoundaryResult = _Result


# ============================================================================
# IDENTIFIER TYPES
# ============================================================================

# Strong typing for different kinds of UIDs to prevent mixing
UserUID = NewType("UserUID", str)
TaskUID = NewType("TaskUID", str)
HabitUID = NewType("HabitUID", str)
EventUID = NewType("EventUID", str)
LearningUID = NewType("LearningUID", str)
ProgressUID = NewType("ProgressUID", str)
SessionUID = NewType("SessionUID", str)
RelationshipUID = NewType("RelationshipUID", str)

# Generic entity UID for when type doesn't matter
EntityUID = NewType("EntityUID", str)

# Graph-specific types
NodeUID = NewType("NodeUID", str)
EdgeUID = NewType("EdgeUID", str)
GraphUID = NewType("GraphUID", str)

# Type alias for any UID
type AnyUID = (
    UserUID | TaskUID | HabitUID | EventUID | LearningUID | ProgressUID | SessionUID | EntityUID
)


# ============================================================================
# VALUE TYPES
# ============================================================================

# Time and duration types
Minutes = NewType("Minutes", int)
Hours = NewType("Hours", float)
Days = NewType("Days", int)
Timestamp = NewType("Timestamp", datetime)

# Scoring and metrics
Score = NewType("Score", float)  # 0.0 to 1.0
Percentage = NewType("Percentage", float)  # 0.0 to 100.0
MasteryLevel = NewType("MasteryLevel", float)  # 0.0 to 1.0

# Counts and quantities
Count = NewType("Count", int)
StreakDays = NewType("StreakDays", int)

# Text types
Title = NewType("Title", str)
Description = NewType("Description", str)
Tag = NewType("Tag", str)
Username = NewType("Username", str)
Email = NewType("Email", str)

# YAML/Markdown source tracking
YamlSource = NewType("YamlSource", str)
MarkdownSource = NewType("MarkdownSource", str)


# ============================================================================
# COLLECTION TYPES
# ============================================================================

# Common collection patterns
type TagList = list[Tag]
type UIDSet = set[EntityUID]
type UIDList = list[EntityUID]
type Metadata = dict[str, Any]

# Relationship mappings
type UIDMapping = dict[EntityUID, EntityUID]
type ProgressMapping = dict[EntityUID, ProgressUID]
type ScoreMapping = dict[EntityUID, Score]

# Time windows
type TimeRange = tuple[datetime, datetime]
type DateRange = tuple[date, date]


# ============================================================================
# FUNCTION TYPES
# ============================================================================

# Validator function signature
type Validator = Callable[[Any], list[str]]

# Filter function signature
type EntityFilter = Callable[[Any], bool]

# Scorer function signature
type Scorer = Callable[[Any], Score]

# Update function signature
type Updater = Callable[[Any, dict[str, Any]], Any]


# ============================================================================
# LITERAL TYPES
# ============================================================================

# Context types for user context
ContextType = Literal["search", "conversation", "path", "calendar", "generic"]

# Time period literals
TimePeriod = Literal["day", "week", "month", "quarter", "year"]

# Comparison operators
ComparisonOp = Literal["eq", "ne", "lt", "le", "gt", "ge"]

# Sort directions
SortDirection = Literal["asc", "desc"]

# Graph operation types
GraphOperation = Literal["merge", "create", "match", "delete"]
EdgeDirection = Literal["outgoing", "incoming", "both"]


# ============================================================================
# TYPE VARIABLES
# ============================================================================

# Generic type variables
T = TypeVar("T")
T_Entity = TypeVar("T_Entity", bound="BaseEntity")
T_Trackable = TypeVar("T_Trackable", bound="CalendarTrackable")


# ============================================================================
# PROTOCOLS (STRUCTURAL TYPING)
# ============================================================================


@runtime_checkable
class Identifiable(Protocol):
    """Protocol for entities with UIDs"""

    uid: str


@runtime_checkable
class Timestamped(Protocol):
    """Protocol for entities with timestamps"""

    created_at: datetime
    updated_at: datetime | None


@runtime_checkable
class Prioritizable(Protocol):
    """Protocol for entities with priority"""

    priority: Any  # Should be Priority enum


@runtime_checkable
class Completable(Protocol):
    """Protocol for entities that can be completed"""

    def is_complete(self) -> bool: ...
    def get_completion_percentage(self) -> Percentage: ...


@runtime_checkable
class Validatable(Protocol):
    """Protocol for entities that can be validated"""

    def validate(self) -> list[str]: ...
    def is_valid(self) -> bool: ...


# ============================================================================
# TYPE GUARDS
# ============================================================================


def is_valid_uid(value: Any) -> TypeGuard[EntityUID]:
    """
    Check if value is a valid UID.

    SKUEL uses two UID formats:
    1. Dot notation (curriculum): ku.yoga.meditation, path.beginner.python
    2. Underscore notation (activity): task_implement-auth_a1b2, event_ab12cd34

    Args:
        value: Value to check

    Returns:
        True if value matches either UID format
    """
    if not isinstance(value, str):
        return False
    if not value or len(value) < 2:
        return False

    # Dot notation: prefix.parts (at least prefix.something)
    if "." in value:
        parts = value.split(".")
        # Must have at least prefix.slug (2 parts)
        if len(parts) < 2:
            return False
        # Prefix must be alphabetic (ku, path, dom, moc, ls, lp, etc.)
        if not parts[0].isalpha():
            return False
        # All parts must be non-empty
        return all(part for part in parts)

    # Underscore notation: prefix_random or prefix_slug_random
    if "_" in value:
        parts = value.split("_")
        # Must have at least prefix_random (2 parts)
        if len(parts) < 2:
            return False
        # Prefix must be alphabetic (task, event, habit, etc.)
        if not parts[0].isalpha():
            return False
        # Last part should be alphanumeric (the random suffix)
        return parts[-1].replace("-", "").isalnum()

    return False


def is_valid_email(value: Any) -> TypeGuard[Email]:
    """Check if value is a valid email"""
    if not isinstance(value, str):
        return False
    import re

    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, value))


def is_valid_percentage(value: Any) -> TypeGuard[Percentage]:
    """Check if value is a valid percentage"""
    return isinstance(value, int | float) and 0 <= value <= 100


def is_valid_score(value: Any) -> TypeGuard[Score]:
    """Check if value is a valid score"""
    return isinstance(value, int | float) and 0 <= value <= 1


def is_valid_timestamp(value: Any) -> TypeGuard[Timestamp]:
    """Check if value is a valid timestamp"""
    return isinstance(value, datetime)


# ============================================================================
# TYPE CONVERSION HELPERS
# ============================================================================


class TypeConverter:
    """Helper class for safe type conversions"""

    @staticmethod
    def to_entity_uid(value: str) -> EntityUID:
        """
        Convert string to EntityUID with validation.

        Raises ValueError if invalid. For Result-based conversion at boundaries,
        use to_entity_uid_safe() instead.
        """
        if not is_valid_uid(value):
            raise ValueError(f"Invalid UID format: {value}")
        return EntityUID(value)

    @staticmethod
    def to_entity_uid_safe(value: str) -> "BoundaryResult[EntityUID]":
        """
        Convert string to EntityUID with Result-based error handling.

        This is the preferred method for HTTP boundaries where errors should
        be returned as Result failures rather than exceptions.

        Args:
            value: Raw string UID from request

        Returns:
            Result[EntityUID] - Ok(EntityUID) if valid, Err with validation error if not

        Example:
            # In route handler:
            uid_result = TypeConverter.to_entity_uid_safe(raw_uid)
            if uid_result.is_error:
                return uid_result  # Returns 400 via @boundary_handler

            # Now we have typed EntityUID
            entity_uid = uid_result.value
            return await service.get(entity_uid)
        """
        from core.utils.result_simplified import Errors, Result

        if not is_valid_uid(value):
            return Result.fail(
                Errors.validation(
                    message=f"Invalid UID format: {value}",
                    field="uid",
                    value=value,
                    user_message="The provided identifier is not in a valid format",
                )
            )
        return Result.ok(EntityUID(value))

    @staticmethod
    def to_user_uid(value: str) -> UserUID:
        """Convert string to UserUID with validation"""
        if not value.startswith("user_"):
            raise ValueError(f"Invalid UserUID: {value}")
        return UserUID(value)

    @staticmethod
    def to_percentage(value: float) -> Percentage:
        """Convert float to Percentage with validation"""
        if not is_valid_percentage(value):
            raise ValueError(f"Invalid percentage: {value}")
        return Percentage(value)

    @staticmethod
    def to_score(value: float) -> Score:
        """Convert float to Score with validation"""
        if not is_valid_score(value):
            raise ValueError(f"Invalid score: {value}")
        return Score(value)

    @staticmethod
    def minutes_to_hours(minutes: Minutes) -> Hours:
        """Convert minutes to hours"""
        return Hours(minutes / 60.0)

    @staticmethod
    def hours_to_minutes(hours: Hours) -> Minutes:
        """Convert hours to minutes"""
        return Minutes(int(hours * 60))


# ============================================================================
# RESULT TYPES
# ============================================================================


@dataclass
class Success[T]:
    """Success result wrapper"""

    value: T


@dataclass
class Failure:
    """Failure result wrapper"""

    error: str
    details: dict[str, Any] | None = None


# Result type for operations that can fail
# Note: Cannot use TypeAlias with generic parameters in Python 3.10
# Use Result = Success[T] | Failure directly in type hints where needed


@dataclass
class ValidationResult:
    """Result of validation operation"""

    is_valid: bool
    errors: list[str]
    warnings: list[str] = field(default_factory=list)


# ============================================================================
# LAZY EVALUATION WRAPPER
# ============================================================================


class Lazy[T]:
    """
    Wrapper for lazy evaluation of expensive computations.

    Usage:
        def compute_factory():
            return compute_expensive_value()

        expensive_value = Lazy(compute_factory)
        # Computation happens only when accessed:
        actual_value = expensive_value.value
    """

    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        self._value: T | None = None
        self._computed = False

    @property
    def value(self) -> T:
        """Get the value, computing it if necessary"""
        if not self._computed:
            self._value = self._factory()
            self._computed = True
        return self._value  # type: ignore

    def reset(self) -> None:
        """Reset the lazy value to force recomputation"""
        self._computed = False
        self._value = None

    def is_computed(self) -> bool:
        """Check if value has been computed"""
        return self._computed


# ============================================================================
# CACHED PROPERTY DECORATOR
# ============================================================================


def cached_property[T](func: Callable[[Any], T]) -> property:
    """
    Decorator for creating cached properties.

    The property is computed once and cached for subsequent access.

    Usage:
        class MyClass:
            @cached_property
            def expensive_property(self) -> int:
                return sum(range(1000000))
    """
    attr_name = f"_cached_{func.__name__}"
    sentinel = object()  # Unique sentinel to detect missing attribute

    @property  # type: ignore[misc]
    def _cached_property(self) -> Any:
        if getattr(self, attr_name, sentinel) is sentinel:
            setattr(self, attr_name, func(self))
        return getattr(self, attr_name)

    return _cached_property  # type: ignore[return-value]  # MyPy limitation: can't track @property decorator transformation


# ============================================================================
# EXPORT ALL TYPE DEFINITIONS
# ============================================================================

__all__ = [
    "AnyUID",
    "ComparisonOp",
    "Completable",
    # Literal types
    "ContextType",
    "Count",
    "DateRange",
    "Days",
    "Description",
    "EdgeDirection",
    "EdgeUID",
    "Email",
    "EntityFilter",
    "EntityUID",
    "EventUID",
    "Failure",
    "GraphOperation",
    "GraphUID",
    "HabitUID",
    "Hours",
    # Protocols
    "Identifiable",
    "Lazy",
    "LearningUID",
    "MarkdownSource",
    "MasteryLevel",
    "Metadata",
    # Value types
    "Minutes",
    "NodeUID",
    "Percentage",
    "Prioritizable",
    "ProgressMapping",
    "ProgressUID",
    "RelationshipUID",
    "Score",
    "ScoreMapping",
    "Scorer",
    "SessionUID",
    "SortDirection",
    "StreakDays",
    "Success",
    # Type variables
    "T",
    "T_Entity",
    "T_Trackable",
    "Tag",
    # Collection types
    "TagList",
    "TaskUID",
    "TimePeriod",
    "TimeRange",
    "Timestamp",
    "Timestamped",
    "Title",
    # Helpers
    "TypeConverter",
    "UIDList",
    "UIDMapping",
    "UIDSet",
    "Updater",
    # Identifier types
    "UserUID",
    "Username",
    "Validatable",
    "ValidationResult",
    # Function types
    "Validator",
    "YamlSource",
    "cached_property",
    "is_valid_email",
    "is_valid_percentage",
    "is_valid_score",
    "is_valid_timestamp",
    # Type guards
    "is_valid_uid",
]
