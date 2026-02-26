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
import types
from dataclasses import MISSING, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, TypeVar, Union, get_args, get_origin, get_type_hints

from core.utils.logging import get_logger

T = TypeVar("T")

logger = get_logger(__name__)

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
    "learning_step_uids",
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
    # Domain relationships
    "domain_uids",
    "used_by_uids",
    "references_uids",
    "referenced_by_uids",
}


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

            # Skip None values for optional fields
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
                        isinstance(item, dict) or is_dataclass(item) for item in value
                    )

                    if has_complex_items:
                        # Nested collection - convert to JSON string
                        # e.g., tuple[dict, ...] or tuple[Milestone, ...]
                        serializable_list = []
                        for item in value:
                            if is_dataclass(item):
                                # Convert dataclass to dict first
                                serializable_list.append(Neo4jGenericMapper.to_node(item))
                            elif isinstance(item, dict):
                                serializable_list.append(item)
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

            # Skip None values
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
    def from_node(data: dict[str, Any], entity_class: type[T]) -> T:
        """
        Convert Neo4j node data to domain entity.

        Uses type hints to automatically reconstruct:
        - Enum instances from string values
        - Date/datetime from ISO strings
        - Lists/sets from JSON strings
        - Nested dataclasses

        Args:
            data: Neo4j node properties
            entity_class: Target domain class (must be a dataclass)

        Returns:
            Instance of entity_class with data populated
        """
        if not is_dataclass(entity_class):
            raise ValueError(f"Entity class must be a dataclass, got {entity_class}")

        # Get type hints for the class using the module namespace so that
        # forward references from `from __future__ import annotations` resolve
        # correctly (locals() here doesn't contain the class's own imports).
        import sys as _sys

        try:
            module = _sys.modules.get(entity_class.__module__)
            globalns = getattr(module, "__dict__", {}) if module else {}
            type_hints = get_type_hints(entity_class, globalns=globalns, localns={})
        except (NameError, AttributeError):
            # Fall back to field.type strings if resolution still fails
            type_hints = {}
        kwargs = {}

        for field in fields(entity_class):
            field_name = field.name
            field_type = type_hints.get(field_name, field.type)
            value = data.get(field_name)

            # Skip if not in data
            if field_name not in data:
                # Use field default if available
                if field.default is not MISSING:
                    kwargs[field_name] = field.default
                elif field.default_factory is not MISSING:
                    kwargs[field_name] = field.default_factory()
                continue

            # Handle None values
            if value is None:
                kwargs[field_name] = None
                continue

            # Unwrap Optional types (handle both Union and | syntax)
            origin = get_origin(field_type)
            # Check for UnionType (Python 3.10+ pipe syntax support)
            is_union_type = origin is Union
            # For Python 3.10+, check if types module has UnionType
            if not is_union_type:
                try:
                    union_type = getattr(types, "UnionType", None)
                    if union_type is not None:
                        is_union_type = origin is union_type
                except AttributeError:
                    pass

            if is_union_type:
                args = get_args(field_type)
                # Check if it's Optional (Union with None)
                non_none_types = [t for t in args if t is not type(None)]
                if len(non_none_types) == 1:
                    field_type = non_none_types[0]
                    origin = get_origin(field_type)

            # Convert based on type
            try:
                kwargs[field_name] = Neo4jGenericMapper._convert_value(
                    value, field_type, field_name
                )
            except Exception as e:
                # Log error and use raw value
                logger.warning("Failed to convert field", field=field_name, error=str(e))
                kwargs[field_name] = value

        return entity_class(**kwargs)

    @staticmethod
    def _convert_value(value: Any, target_type: type, field_name: str) -> Any:
        """
        Convert a single value to its target type.

        Internal method that handles the type-specific conversion logic.

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
                except (json.JSONDecodeError, ValueError):
                    pass
            return value

        # Get origin for generic types
        origin = get_origin(target_type)

        # Handle Enum types
        if inspect.isclass(target_type) and issubclass(target_type, Enum):
            # Convert string back to enum
            if isinstance(value, str):
                try:
                    return target_type(value)
                except ValueError as e:
                    # Try by name if value doesn't work
                    for member in target_type:
                        if member.name == value:
                            return member
                    # No match found - raise with context
                    raise ValueError(
                        f"Field '{field_name}': Cannot convert '{value}' to enum {target_type.__name__}. "
                        f"Valid values: {[m.value for m in target_type]}"
                    ) from e
            return value

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
            return value

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
            return value

        # Handle tuples
        elif origin is tuple:
            if isinstance(value, str):
                # Guard: empty string means empty tuple
                if value == "":
                    return ()
                try:
                    # Parse JSON string (may be nested collection - tuple of dicts/dataclasses)
                    parsed = json.loads(value)
                    parsed_list = parsed if isinstance(parsed, list) else [parsed]

                    # Check if element type is a dataclass and reconstruct
                    type_args = get_args(target_type)
                    if type_args and len(type_args) > 0:
                        element_type = type_args[0]
                        if is_dataclass(element_type):
                            # Reconstruct dataclasses from dict representation
                            reconstructed = []
                            for item in parsed_list:
                                if isinstance(item, dict):
                                    reconstructed.append(
                                        Neo4jGenericMapper.from_node(item, element_type)
                                    )
                                else:
                                    reconstructed.append(item)
                            return tuple(reconstructed)

                    return tuple(parsed_list)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Field '{field_name}': Cannot parse JSON string for tuple: {e}"
                    ) from e
            elif isinstance(value, list | tuple):
                return tuple(value)
            return (value,)

        # Handle lists
        elif origin is list:
            if isinstance(value, str):
                # Guard: empty string means empty list
                if value == "":
                    return []
                try:
                    # Parse JSON string (may be nested collection - list of dicts/dataclasses)
                    parsed = json.loads(value)
                    parsed_list = parsed if isinstance(parsed, list) else [parsed]

                    # Check element type and reconstruct
                    type_args = get_args(target_type)
                    if type_args and len(type_args) > 0:
                        element_type = type_args[0]

                        # Handle dataclass elements
                        if is_dataclass(element_type):
                            reconstructed = []
                            for item in parsed_list:
                                if isinstance(item, dict):
                                    reconstructed.append(
                                        Neo4jGenericMapper.from_node(item, element_type)
                                    )
                                else:
                                    reconstructed.append(item)
                            return reconstructed

                        # Handle enum elements
                        if inspect.isclass(element_type) and issubclass(element_type, Enum):
                            # Convert string values back to enum objects
                            converted_list = []
                            for item in parsed_list:
                                if isinstance(item, str):
                                    try:
                                        converted_list.append(element_type(item))
                                    except ValueError:
                                        # Try by name if value doesn't work
                                        for member in element_type:
                                            if member.name == item:
                                                converted_list.append(member)
                                                break
                                        else:
                                            converted_list.append(item)  # Keep original if no match
                                else:
                                    converted_list.append(item)
                            return converted_list

                    return parsed_list
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Field '{field_name}': Cannot parse JSON string for list: {e}"
                    ) from e
            elif isinstance(value, list | tuple):
                return list(value)
            return [value]

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
                    # Parse JSON string
                    return json.loads(value)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Field '{field_name}': Cannot parse JSON string for dict: {e}"
                    ) from e
            return value

        # Handle nested dataclasses
        elif is_dataclass(target_type):
            if isinstance(value, str):
                # Guard: empty string means None for optional nested dataclass
                if value == "":
                    return None
                try:
                    # Parse JSON string and reconstruct
                    parsed = json.loads(value)
                    return Neo4jGenericMapper.from_node(parsed, target_type)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Field '{field_name}': Cannot parse JSON string for nested dataclass {target_type.__name__}: {e}"
                    ) from e
            elif isinstance(value, dict):
                return Neo4jGenericMapper.from_node(value, target_type)
            return value

        # Handle primitives and unknown types
        else:
            return value


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


def from_neo4j_node[T](data: dict[str, Any], entity_class: type[T]) -> T:
    """
    Convert Neo4j node data to domain entity.

    This is the single function that replaces all the repetitive
    node_to_*() functions across backends.

    Examples:
        # Replaces node_to_pure()
        task = from_neo4j_node(node_data, TaskPure)

        # Replaces report_node_to_pure()
        report = from_neo4j_node(node_data, Report)

        # Replaces node_to_pure() for habits
        habit = from_neo4j_node(node_data, HabitPure)
    """
    return _mapper.from_node(data, entity_class)


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
# In tasks_neo4j_backend.py:

from core.utils.neo4j_mapper import to_neo4j_node, from_neo4j_node
from core.models.task_pure import TaskPure

class Neo4jTasksBackend:
    async def create_task(self, task: TaskPure) -> TaskPure:
        # OLD: props = task_to_node(task)
        props = to_neo4j_node(task) # NEW: Generic mapper

        cypher = "CREATE (t:Task $props) RETURN t"
        records = await self.neo4j.execute_query(cypher, {"props": props})

        if records:
            # OLD: return node_to_pure(dict(records[0]["t"]))
            return from_neo4j_node(dict(records[0]["t"]), TaskPure) # NEW
        return task

# In reports backend (generic example):
# NOTE: Journal backend removed (February 2026) — journals are Report nodes
# with report_type="journal". All use UniversalNeo4jBackend[Report].

# Benefits:
# 1. Single implementation for all entities - no more duplication
# 2. Type-safe with automatic conversions
# 3. Handles all edge cases in one place
# 4. New entities automatically supported
# 5. ~90% reduction in mapping code
"""
