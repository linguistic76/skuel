"""
Generic Neo4j Node Mapper
=========================

A single, generic mapper that handles all Neo4j node↔domain conversions
using Python's type hints and introspection. Eliminates thousands of lines
of repetitive mapping code across all backends.

Key Features:
- Automatic enum conversion (value extraction and reconstruction)
- Date/datetime ISO format handling
- JSON serialization for lists/sets
- Nested object flattening
- Type-safe reconstruction using annotations
"""

import inspect
import json
import sys
import types
from collections.abc import Mapping
from dataclasses import MISSING, Field, dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any, TypeVar, Union, get_args, get_origin, get_type_hints

from core.models.type_hints import Neo4jProperties
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.neo4j_temporal import (
    convert_neo4j_date,
    convert_neo4j_datetime,
    convert_neo4j_time,
    is_neo4j_date,
    is_neo4j_datetime,
    is_neo4j_time,
)
from core.utils.type_converters import read_enum_value

T = TypeVar("T")

logger = get_logger(__name__)


class UnreadableStoredValueError(Exception):
    """A stored property its field's declared type cannot read.

    ``from_neo4j_node`` raises it rather than build a model that holds a value of
    another type: a read meeting one fails, and no reader is handed the raw value,
    a default, or ``None`` for a field that requires a value. It is not a
    ``ValueError``, so neither a caller's ``DATA_CONVERSION_EXCEPTIONS`` catch nor
    ``with_error_handling``'s validation category takes it for bad input; a backend
    read answers it as a failed ``Result``. The stored-value census
    (``./dev stored-value-census``) names every one the graph holds.
    """

    def __init__(
        self,
        entity_class: type,
        uid: object,
        field: str,
        value: object,
        reason: str,
    ) -> None:
        self.entity_class = entity_class.__name__
        self.uid = uid
        self.field = field
        self.value = value
        self.reason = reason
        super().__init__(
            f"{self.entity_class} {uid!r}: stored {field}={value!r:.80} is unreadable ({reason})"
        )


# ============================================================================
# GRAPH-NATIVE MIGRATION - SKIP RELATIONSHIP FIELDS
# ============================================================================
# These fields should NOT be serialized to Neo4j node properties.
# Relationships are stored as graph edges, not node properties.
#
# Migration Date: October 6, 2025
# See: /docs/migrations/GRAPH_NATIVE_MIGRATION_PLAN.md
#
RELATIONSHIP_SKIP_FIELDS = {
    # Knowledge Unit relationships
    "prerequisites",
    "enables",
    "related_to",
    "prerequisite_uids",
    "enables_uids",
    "related_concept_uids",
    "used_in_step_uids",
    "featured_in_path_uids",
    # Learning Path/Step relationships
    "learning_path_uids",
    "path_step_uids",
    "step_uids",
    "resource_uids",
    "exercise_uids",
    "builds_on_uids",
    "see_also_uids",
    "applies_to_uids",
    # Hierarchical relationships
    "parent_uid",
    "child_uids",
    "children",
    "parent",
    # Task/Event/Habit relationships
    # Carried by BOTH the Task and Event dataclasses, and documented on both as
    # DERIVED FROM EDGE — the link is (Task|Event)-[:REINFORCES_HABIT]->(Habit).
    # Neither docstring's "never written to Neo4j" was true before this entry: it
    # rested on the field being absent from the DTO, and the generated CRUD route
    # persists the ENTITY, so ``POST /api/{tasks,events}/create`` wrote it as a node
    # property that no reader consults. The create path now writes the EDGE instead
    # (TasksCoreService._write_link_edges / EventsCoreService._write_link_edges); the
    # update path already split this field off the property patch
    # (TasksService._split_relationship_intent, EventsService's sibling).
    "reinforces_habit_uid",
    "depends_on_uids",
    "blocks_uids",
    "blocked_by_uids",
    "related_task_uids",
    "related_event_uids",
    "related_habit_uids",
    # Goal relationships
    "supports_goal_uids",
    "supported_by_uids",
    "milestone_uids",
    # Carried by Task and Event, documented as DERIVED FROM EDGE — the link is
    # (Task|Event)-[:CONTRIBUTES_TO_GOAL]->(Goal), populated at fetch time by the
    # goal-link enrichers. Skipped so a writer persisting an ENRICHED entity cannot
    # leak it.
    "contributes_to_goal_uid",
    # The same edge's create-only INPUT on Task and Event (plural — one edge per goal),
    # turned into edges by TasksCoreService._write_link_edges and
    # EventsCoreService._write_link_edges. Skipped so the uids never land as a node
    # property no reader consults.
    "contributes_to_goal_uids",
    # A task's principles — (Task)-[:ALIGNED_WITH_PRINCIPLE]->(Principle), written by
    # task create and update; any other door (a vault frontmatter key) must not land
    # the uids as a node property no reader consults.
    "aligned_principle_uids",
    # Carried by Habit only and DERIVED AT READ, not from an edge: the habit's
    # adherence now (core.models.habit.adherence), hydrated after the read by
    # enrich_habits_with_adherence. A stored number goes stale the first day
    # nothing is done, so no writer — an enriched Habit re-applied included —
    # may persist it.
    "success_rate",
    # Domain relationships
    "domain_uids",
    "used_by_uids",
    "references_uids",
    "referenced_by_uids",
}

# Properties the embeddings writer owns — ``EmbeddingsBackend.store_embedding_metadata``
# is their ONE writer (ADR-074 §8). The first three are also ``Entity`` fields, which
# ``to_node`` serialises as explicit nulls; under ``SET n += $props`` a null REMOVES
# the property, so an entity writer re-applying a full-model payload to an EXISTING
# node would strip the vector on every re-sync (then the worker re-embeds identical
# text — ``verify_fresh_embeddings`` needs ``has_embedding``). Entity writers drop
# these keys with ``without_embedding_props()`` before any ``+=`` write.
EMBEDDING_OWNED_PROPERTIES: frozenset[str] = frozenset(
    {
        "embedding",
        "embedding_model",
        "embedding_updated_at",
        "embedding_version",
        "embedding_text_hash",
    }
)


def without_embedding_props(props: dict[str, Any]) -> dict[str, Any]:
    """Return ``props`` minus the embedding writer's properties.

    A re-sync refreshes what the file (or caller) authors; the vector and its
    metadata are derived state whose freshness ``verify_fresh_embeddings``
    decides from the stored hash, never from an entity payload. Every other
    key passes through unchanged, explicit ``None`` included — null-under-
    ``+=`` is the channel a cleared field uses to retract its property.
    """
    return {k: v for k, v in props.items() if k not in EMBEDDING_OWNED_PROPERTIES}


class Neo4jGenericMapper:
    """
    Generic mapper for Neo4j node↔domain conversions.

    Replaces thousands of lines of repetitive mapping code with a single
    implementation that uses type introspection.

    Graph-Native Migration:
    - Relationship fields are skipped during serialization
    - Relationships stored ONLY as Neo4j edges, not node properties
    """

    @staticmethod
    def to_node(entity: Any) -> dict[str, Any]:
        """
        Convert any domain entity to Neo4j node properties.

        Handles:
        - Dict entities (from UnifiedIngestionService)
        - Dataclass fields with type-aware serialization
        - Enum values (extracts .value)
        - Date/datetime to ISO format
        - Lists/sets to JSON strings
        - None values appropriately

        Args:
            entity: Domain entity (dataclass or dict)

        Returns:
            Dictionary of Neo4j-compatible properties
        """
        # Handle dict entities directly (from UnifiedIngestionService)
        if isinstance(entity, dict):
            return Neo4jGenericMapper._dict_to_node(entity)

        if not is_dataclass(entity):
            raise ValueError(f"Entity must be a dataclass or dict, got {type(entity)}")

        node_data: dict[str, Any] = {}

        for field in fields(entity):
            # Skip relationship fields - these become graph edges
            if field.name in RELATIONSHIP_SKIP_FIELDS:
                continue

            value = getattr(entity, field.name)

            # Unwrap read-only dict proxies — MappingProxyType wraps frozen model
            # dicts for deep immutability; convert back to plain dict for serialization
            if isinstance(value, types.MappingProxyType):
                value = dict(value)

            # Keep None as an explicit null. Under ``SET n += $props`` a null
            # REMOVES the property — the channel a cleared field uses to retract
            # on re-sync (``fulfills_exercise_uid``); under
            # ``SET n = $props`` / CREATE it is simply absent. Keys another writer
            # owns are the caller's to drop (``without_embedding_props``).
            if value is None:
                node_data[field.name] = None
                continue

            # Handle different types
            if isinstance(value, Enum):
                # Extract enum value
                node_data[field.name] = value.value
            elif isinstance(value, date | datetime):
                # Convert to ISO format
                node_data[field.name] = value.isoformat()
            elif isinstance(value, list | set | tuple):
                # Convert collections to Neo4j lists
                # Neo4j supports native lists of primitives only
                # Nested collections (list of dicts, tuple of dataclasses) must be JSON-encoded
                if value:
                    # Convert sets/tuples to lists
                    if isinstance(value, set | tuple):
                        value = list(value)

                    # Check if this is a nested collection (contains dicts or dataclasses)
                    has_complex_items = any(
                        isinstance(item, dict | types.MappingProxyType) or is_dataclass(item)
                        for item in value
                    )

                    if has_complex_items:
                        # Nested collection - convert to JSON string
                        # e.g., tuple[dict, ...] or tuple[Milestone, ...]
                        serializable_list = []
                        for item in value:
                            if is_dataclass(item):
                                # Convert dataclass to dict first
                                serializable_list.append(Neo4jGenericMapper.to_node(item))
                            elif isinstance(item, dict | types.MappingProxyType):
                                serializable_list.append(dict(item))
                            else:
                                serializable_list.append(item)
                        node_data[field.name] = json.dumps(serializable_list)
                    else:
                        # Simple collection - store as Neo4j list
                        # Convert enum objects to their values
                        processed_value = []
                        for item in value:
                            if isinstance(item, Enum):
                                processed_value.append(item.value)
                            else:
                                processed_value.append(item)

                        # Store as native Python list (Neo4j driver converts to Neo4j list)
                        node_data[field.name] = processed_value
                else:
                    node_data[field.name] = []  # Empty list instead of None
            elif isinstance(value, dict):
                # Convert dicts to JSON strings
                # Neo4j properties must be primitives or arrays - dicts not supported
                if value:
                    node_data[field.name] = json.dumps(value)
                else:
                    node_data[field.name] = None
            elif is_dataclass(value):
                # Flatten nested dataclasses (like insights, metadata)
                nested = Neo4jGenericMapper.to_node(value)
                # Store as JSON string
                node_data[field.name] = json.dumps(nested)
            else:
                # Store primitive values directly
                node_data[field.name] = value

        return node_data

    @staticmethod
    def _dict_to_node(entity: dict[str, Any]) -> dict[str, Any]:
        """
        Convert a dict entity to Neo4j node properties.

        Used by UnifiedIngestionService which passes dicts rather than dataclasses.
        Applies the same serialization rules as to_node() for dataclasses.

        Args:
            entity: Dict of entity properties

        Returns:
            Dictionary of Neo4j-compatible properties
        """
        node_data: dict[str, Any] = {}

        for key, value in entity.items():
            # Skip relationship fields - these become graph edges
            if key in RELATIONSHIP_SKIP_FIELDS:
                continue

            # Explicit null, as in to_node(): null-under-``+=`` retracts the property.
            if value is None:
                node_data[key] = None
                continue

            # Handle different types
            if isinstance(value, Enum):
                node_data[key] = value.value
            elif isinstance(value, date | datetime):
                node_data[key] = value.isoformat()
            elif isinstance(value, list | set | tuple):
                if value:
                    if isinstance(value, set | tuple):
                        value = list(value)
                    # Check for complex items
                    has_complex_items = any(
                        isinstance(item, dict) or is_dataclass(item) for item in value
                    )
                    if has_complex_items:
                        serializable_list = []
                        for item in value:
                            if is_dataclass(item):
                                serializable_list.append(Neo4jGenericMapper.to_node(item))
                            elif isinstance(item, dict):
                                serializable_list.append(item)
                            else:
                                serializable_list.append(item)
                        node_data[key] = json.dumps(serializable_list)
                    else:
                        # Simple list - convert enums if present
                        processed_value = []
                        for item in value:
                            if isinstance(item, Enum):
                                processed_value.append(item.value)
                            else:
                                processed_value.append(item)
                        node_data[key] = processed_value
                else:
                    node_data[key] = []
            elif isinstance(value, dict):
                if value:
                    node_data[key] = json.dumps(value)
                else:
                    node_data[key] = None
            elif is_dataclass(value):
                nested = Neo4jGenericMapper.to_node(value)
                node_data[key] = json.dumps(nested)
            else:
                # Store primitive values directly
                node_data[key] = value

        return node_data

    @staticmethod
    def from_node(data: Mapping[str, Any], entity_class: type[T]) -> T:  # boundary: node properties
        """
        Convert Neo4j node data to domain entity.

        Uses type hints to automatically reconstruct:
        - Enum instances from string values (``read_enum_value``)
        - Date/datetime/time from ISO strings or the driver's temporals
        - Lists/tuples/sets/dicts from JSON strings
        - Nested dataclasses

        Every field holds a value of its declared type, or the read fails: a stored
        value the type cannot read raises ``UnreadableStoredValueError``, never a model
        holding the raw value, a default, or ``None`` for a field that requires one.

        Args:
            data: Neo4j node properties
            entity_class: Target domain class (must be a dataclass)

        Returns:
            Instance of entity_class with data populated

        Raises:
            UnreadableStoredValueError: a stored value its field's type cannot read.
        """
        kwargs: dict[str, Any] = {}  # boundary: one value per field, each its own type
        for spec in _field_specs(entity_class):
            name = spec.field.name
            # Neo4j stores no null: a null field reads as an absent one does.
            if name not in data or _null_takes_the_default(data, spec):
                if spec.field.default is not MISSING:
                    kwargs[name] = spec.field.default
                elif spec.field.default_factory is not MISSING:
                    kwargs[name] = spec.field.default_factory()
                continue
            kwargs[name] = _read_field(data, entity_class, spec)
        return entity_class(**kwargs)

    @staticmethod
    def _convert_value(value: Any, target_type: type, field_name: str) -> Any:
        """
        Convert a single value to its target type.

        Internal method that handles the type-specific conversion logic. Raises
        ``ValueError`` (or the parser's own error) for a value the type cannot
        read; ``from_node`` names the node and field and raises
        ``UnreadableStoredValueError``.

        Args:
            value: The value to convert
            target_type: The target type to convert to
            field_name: Name of the field being converted (for error messages)
        """
        # Handle None
        if value is None:
            return None

        # Guard: if target_type is still a string annotation (get_type_hints fallback),
        # detect common dict/list patterns and attempt JSON parsing.
        if isinstance(target_type, str):
            # Always convert neo4j temporal types to Python natives, even when
            # the target type annotation couldn't be resolved — prevents
            # AttributeError on strftime/date operations in callers.
            if is_neo4j_time(value):
                return convert_neo4j_time(value)
            if is_neo4j_date(value):
                return convert_neo4j_date(value)
            if is_neo4j_datetime(value):
                return convert_neo4j_datetime(value)
            if (
                (
                    target_type == "dict"
                    or target_type.startswith("dict[")
                    or target_type == "list"
                    or target_type.startswith("list[")
                )
                and isinstance(value, str)
                and value
            ):
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, ValueError):  # fmt: skip
                    pass
            return value

        # Get origin for generic types
        origin = get_origin(target_type)

        # Handle Enum types
        if inspect.isclass(target_type) and issubclass(target_type, Enum):
            if isinstance(value, target_type):
                return value
            if isinstance(value, str):
                return read_enum_value(value, target_type, may_be_absent=True)
            raise ValueError(_not_a(value, target_type.__name__))

        # Handle date
        elif target_type is date or (
            inspect.isclass(target_type)
            and issubclass(target_type, date)
            and not issubclass(target_type, datetime)
        ):
            if isinstance(value, str):
                try:
                    # Handle datetime strings for date fields
                    if "T" in value:
                        return datetime.fromisoformat(value).date()
                    return date.fromisoformat(value)
                except ValueError as e:
                    raise ValueError(
                        f"Field '{field_name}': Cannot parse '{value}' as date. "
                        f"Expected ISO format (YYYY-MM-DD)"
                    ) from e
            if is_neo4j_date(value):
                return convert_neo4j_date(value)
            if isinstance(value, date) and not isinstance(value, datetime):
                return value
            raise ValueError(_not_a(value, "date"))

        # Handle datetime
        elif target_type is datetime or (
            inspect.isclass(target_type) and issubclass(target_type, datetime)
        ):
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value)
                except ValueError as e:
                    raise ValueError(
                        f"Field '{field_name}': Cannot parse '{value}' as datetime. "
                        f"Expected ISO format (YYYY-MM-DDTHH:MM:SS)"
                    ) from e
            if is_neo4j_datetime(value):
                return convert_neo4j_datetime(value)
            if isinstance(value, datetime):
                return value
            raise ValueError(_not_a(value, "datetime"))

        # Handle time
        elif target_type is time or (
            inspect.isclass(target_type) and issubclass(target_type, time)
        ):
            if isinstance(value, str):
                try:
                    return time.fromisoformat(value)
                except ValueError as e:
                    raise ValueError(
                        f"Field '{field_name}': Cannot parse '{value}' as time. "
                        f"Expected ISO format (HH:MM:SS)"
                    ) from e
            if is_neo4j_time(value):
                return convert_neo4j_time(value)
            if isinstance(value, time):
                return value
            raise ValueError(_not_a(value, "time"))

        # Handle tuples and lists: a JSON string or a stored list, each item read
        # as the element type when that is a dataclass or an enum
        elif origin is tuple or origin is list:
            type_args = get_args(target_type)
            element_type = type_args[0] if type_args else None
            items = [
                _read_element(item, element_type)
                for item in _sequence_items(value, origin.__name__, field_name)
            ]
            return tuple(items) if origin is tuple else items

        # Handle sets
        elif origin is set:
            if isinstance(value, str):
                # Guard: empty string means empty set
                if value == "":
                    return set()
                try:
                    # Parse JSON string
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return set(parsed)
                    return {parsed}
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Field '{field_name}': Cannot parse JSON string for set: {e}"
                    ) from e
            elif isinstance(value, list | tuple | set):
                return set(value)
            return {value}

        # Handle dicts
        elif origin is dict or target_type is dict:
            if isinstance(value, str):
                # Guard: empty string means empty dict
                if value == "":
                    return {}
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Field '{field_name}': Cannot parse JSON string for dict: {e}"
                    ) from e
                if not isinstance(parsed, dict):
                    raise ValueError(_not_a(parsed, "dict", "its JSON holds"))
                return parsed
            if isinstance(value, Mapping):
                return value
            raise ValueError(_not_a(value, "dict"))

        # Handle nested dataclasses
        elif is_dataclass(target_type):
            if isinstance(value, target_type):
                return value
            if isinstance(value, str):
                # Guard: empty string means None for optional nested dataclass
                if value == "":
                    return None
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Field '{field_name}': Cannot parse JSON string for nested dataclass {target_type.__name__}: {e}"
                    ) from e
                if not isinstance(parsed, dict):
                    raise ValueError(_not_a(parsed, target_type.__name__, "its JSON holds"))
                return Neo4jGenericMapper.from_node(parsed, target_type)
            if isinstance(value, Mapping):
                return Neo4jGenericMapper.from_node(value, target_type)
            raise ValueError(_not_a(value, target_type.__name__))

        # Handle primitives and unknown types
        else:
            return value


@dataclass(frozen=True)
class _FieldSpec:
    """One dataclass field, its resolved type with ``| None`` unwrapped, and whether ``None`` is allowed."""

    field: Field[Any]  # boundary: a dataclass field of any type
    target_type: Any  # boundary: a resolved annotation — a class, a generic alias, or a str
    optional: bool


def _field_specs(entity_class: type) -> tuple[_FieldSpec, ...]:
    """The fields of ``entity_class``, each with the type the mapper reads it as."""
    if not is_dataclass(entity_class):
        raise ValueError(f"Entity class must be a dataclass, got {entity_class}")

    # Get type hints for the class using the module namespace so that
    # forward references from `from __future__ import annotations` resolve
    # correctly (locals() here doesn't contain the class's own imports).
    try:
        module = sys.modules.get(entity_class.__module__)
        globalns = getattr(module, "__dict__", {}) if module else {}
        type_hints = get_type_hints(entity_class, globalns=globalns, localns={})
    except (NameError, AttributeError):  # fmt: skip
        # Fall back to field.type strings if resolution still fails
        type_hints = {}

    specs = []
    for dataclass_field in fields(entity_class):
        field_type = type_hints.get(dataclass_field.name, dataclass_field.type)
        optional = False
        # Unwrap Optional types (both Union and | syntax)
        origin = get_origin(field_type)
        if origin is Union or origin is types.UnionType:
            args = get_args(field_type)
            optional = type(None) in args
            non_none_types = [t for t in args if t is not type(None)]
            if len(non_none_types) == 1:
                field_type = non_none_types[0]
        specs.append(_FieldSpec(dataclass_field, field_type, optional))
    return tuple(specs)


def _read_field(
    data: Mapping[str, Any], entity_class: type, spec: _FieldSpec
) -> Any:  # boundary: node properties in, the field's value out
    """One stored field read as its type; ``UnreadableStoredValueError`` when it cannot be."""
    name = spec.field.name
    value = data[name]
    if value is None:
        if spec.optional:
            return None
        raise UnreadableStoredValueError(
            entity_class, data.get("uid"), name, value, "is null, and the field requires a value"
        )
    try:
        converted = Neo4jGenericMapper._convert_value(value, spec.target_type, name)
    except (UnreadableStoredValueError, *DATA_CONVERSION_EXCEPTIONS) as error:
        raise UnreadableStoredValueError(
            entity_class, data.get("uid"), name, value, str(error)
        ) from error
    if converted is None and not spec.optional:
        raise UnreadableStoredValueError(
            entity_class,
            data.get("uid"),
            name,
            value,
            "reads as absent, and the field requires a value",
        )
    return converted


def _null_takes_the_default(data: Mapping[str, Any], spec: _FieldSpec) -> bool:
    """A null on a field that cannot hold one but has a default: read as the key's absence."""
    return (
        data[spec.field.name] is None
        and not spec.optional
        and (spec.field.default is not MISSING or spec.field.default_factory is not MISSING)
    )


def _not_a(value: object, expected: str, holder: str = "it holds") -> str:
    return f"{holder} a {type(value).__name__}, not a {expected}"


def _sequence_items(
    value: Any, kind: str, field_name: str
) -> list[Any]:  # boundary: a stored collection's items
    """The items a stored list holds: a JSON string's, a native list's, or a lone value."""
    if isinstance(value, str):
        # Guard: empty string means an empty collection
        if value == "":
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Field '{field_name}': Cannot parse JSON string for {kind}: {e}"
            ) from e
        return parsed if isinstance(parsed, list) else [parsed]
    if isinstance(value, list | tuple):
        return list(value)
    return [value]


def _read_element(
    item: Any, element_type: Any
) -> Any:  # boundary: one stored item and its annotation
    """One collection item read as a dataclass or enum element type; any other item as it is."""
    if inspect.isclass(element_type) and is_dataclass(element_type):
        if isinstance(item, element_type):
            return item
        if isinstance(item, Mapping):
            return Neo4jGenericMapper.from_node(item, element_type)
        raise ValueError(_not_a(item, element_type.__name__, "an item is"))
    if inspect.isclass(element_type) and issubclass(element_type, Enum):
        if isinstance(item, element_type):
            return item
        if isinstance(item, str):
            return read_enum_value(item, element_type, may_be_absent=False)
        raise ValueError(_not_a(item, element_type.__name__, "an item is"))
    return item


def unreadable_fields(
    data: Mapping[str, Any], entity_class: type
) -> list[UnreadableStoredValueError]:  # boundary: node properties
    """Every field of ``data`` that ``from_neo4j_node`` would refuse, read without raising.

    The stored-value census reads each node through this: the same field reads
    as a model build, collected rather than stopped at the first.
    """
    refusals = []
    for spec in _field_specs(entity_class):
        if spec.field.name in data and not _null_takes_the_default(data, spec):
            try:
                _read_field(data, entity_class, spec)
            except UnreadableStoredValueError as refusal:
                refusals.append(refusal)
    return refusals


# ============================================================================
# PUBLIC API
# ============================================================================

_mapper = Neo4jGenericMapper()


def to_neo4j_node(entity: Any) -> dict[str, Any]:
    """
    Convert domain entity to Neo4j node properties.

    This is the single function that replaces all the repetitive
    *_to_node() functions across backends.

    Examples:
        # Replaces task_to_node()
        node_props = to_neo4j_node(task)

        # Replaces report_to_node()
        node_props = to_neo4j_node(report)

        # Replaces habit_to_node()
        node_props = to_neo4j_node(habit)
    """
    return _mapper.to_node(entity)


def from_neo4j_node[T](data: Neo4jProperties, entity_class: type[T]) -> T:
    """
    Convert Neo4j node data to domain entity — every backend's one node reader.

    Example:
        task = from_neo4j_node(node_data, Task)

    Each refusal is logged at ERROR here, once per read, whatever its caller then
    does with it.

    Raises:
        UnreadableStoredValueError: a stored value its field's type cannot read.
    """
    try:
        return _mapper.from_node(data, entity_class)
    except UnreadableStoredValueError as refusal:
        logger.error(
            "Unreadable stored value",
            entity_class=refusal.entity_class,
            uid=refusal.uid,
            field=refusal.field,
            reason=refusal.reason,
        )
        raise
