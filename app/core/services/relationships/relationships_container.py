"""
Domain Relationships Container - Generic Relationship Data Container
=====================================================================

Provides a generic container for relationship data that can be used
across all domains, replacing domain-specific containers like
TaskRelationships, GoalRelationships, etc.

The container is dynamically configured based on RelationshipConfig,
allowing a single class to serve all domains.

Version: 1.0.0
Date: 2025-12-03
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar

from core.services.relationships.extended_config import ExtendedRelationshipConfig, QuerySpec

if TYPE_CHECKING:
    from core.services.relationships.unified_relationship_service import UnifiedRelationshipService
    from core.utils.result_simplified import Result

T = TypeVar("T", bound="DomainRelationships")


@dataclass
class DomainRelationships:
    """
    Generic container for domain relationship data.

    This is a base class that can be subclassed for specific domains,
    or used directly with dynamic field population.

    The container stores lists of UIDs for each relationship type,
    fetched from the graph via the relationship service.

    Example Usage:
        # Using with UnifiedRelationshipService
        service = UnifiedRelationshipService(backend, TASK_CONFIG)
        rels = await DomainRelationships.fetch("task:123", service)

        # Access relationship data
        if rels.has_field("applies_knowledge_uids"):
            knowledge = rels.get_field("applies_knowledge_uids")
    """

    # Dynamically populated relationship UID lists
    _data: dict[str, list[str]] = field(default_factory=dict)

    # Configuration reference
    _config: ExtendedRelationshipConfig | None = field(default=None, repr=False)

    def get_field(self, field_name: str) -> list[str]:
        """
        Get a relationship field by name.

        Args:
            field_name: Name of the relationship field

        Returns:
            List of UIDs, or empty list if field not found
        """
        return self._data.get(field_name, [])

    def has_field(self, field_name: str) -> bool:
        """Check if a field exists and has data."""
        return field_name in self._data and len(self._data[field_name]) > 0

    def set_field(self, field_name: str, uids: list[str]) -> None:
        """Set a relationship field."""
        self._data[field_name] = uids

    @property
    def all_fields(self) -> dict[str, list[str]]:
        """Get all relationship data as a dict."""
        return self._data.copy()

    def total_count(self) -> int:
        """Get total count of all relationship UIDs."""
        return sum(len(uids) for uids in self._data.values())

    @classmethod
    async def fetch(
        cls: type[T],
        entity_uid: str,
        service: UnifiedRelationshipService,
    ) -> T:
        """
        Fetch all relationship data from graph in parallel.

        Uses the service's configuration to determine which relationships
        to fetch, then executes all queries concurrently.

        Args:
            entity_uid: UID of entity to fetch relationships for
            service: UnifiedRelationshipService instance

        Returns:
            DomainRelationships instance with all data populated

        Example:
            rels = await DomainRelationships.fetch("task:123", tasks_service)
            print(f"Applied knowledge: {rels.get_field('applies_knowledge_uids')}")
        """
        config = service.config

        # Get query specs from config
        query_specs_attr = getattr(config, "query_specs", None)
        if query_specs_attr:
            query_specs = query_specs_attr
        else:
            # Fall back to building from relationships
            query_specs = cls._build_query_specs_from_config(config)

        # Build coroutines for parallel execution
        coroutines = []
        field_names = []

        for spec in query_specs:
            field_names.append(spec.field_name)
            coroutines.append(service.get_related_uids(spec.method_suffix, entity_uid))

        # Execute all queries in parallel
        results: tuple[Result, ...] = await asyncio.gather(*coroutines)

        # Build data dict from results
        data: dict[str, list[str]] = {}
        for field_name, result in zip(field_names, results, strict=False):
            data[field_name] = result.value if result.is_ok else []

        # Create and return instance
        instance = cls()
        instance._data = data
        instance._config = config
        return instance

    @classmethod
    def _build_query_specs_from_config(cls, config: Any) -> list[QuerySpec]:
        """
        Build query specs from relationship configuration.

        Falls back to this when ExtendedRelationshipConfig.query_specs
        is not available.
        """
        specs = []

        # Build from outgoing relationships
        for method_suffix, rel_spec in config.outgoing_relationships.items():
            specs.append(
                QuerySpec(
                    field_name=f"{method_suffix}_uids",
                    method_suffix=method_suffix,
                    relationship=rel_spec.relationship,
                    direction=rel_spec.direction,
                )
            )

        # Build from incoming relationships
        for method_suffix, rel_spec in config.incoming_relationships.items():
            specs.append(
                QuerySpec(
                    field_name=f"{method_suffix}_uids",
                    method_suffix=method_suffix,
                    relationship=rel_spec.relationship,
                    direction=rel_spec.direction,
                )
            )

        return specs

    @classmethod
    def empty(cls: type[T]) -> T:
        """
        Create empty relationships container (for testing or new entities).

        Returns:
            Empty DomainRelationships instance
        """
        return cls()

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    def has_any_knowledge(self) -> bool:
        """Check if entity has any knowledge connections."""
        knowledge_fields = [
            "knowledge_uids",
            "applies_knowledge_uids",
            "prerequisite_knowledge_uids",
            "required_knowledge_uids",
            "inferred_knowledge_uids",
        ]
        return any(self.has_field(f) for f in knowledge_fields)

    def has_prerequisites(self) -> bool:
        """Check if entity has any prerequisites."""
        prereq_fields = [
            "prerequisite_task_uids",
            "prerequisite_knowledge_uids",
            "prerequisite_habit_uids",
            "prerequisites_uids",
        ]
        return any(self.has_field(f) for f in prereq_fields)

    def get_all_knowledge_uids(self) -> set[str]:
        """Get all unique knowledge UIDs across all relationship types."""
        knowledge_fields = [
            "knowledge_uids",
            "applies_knowledge_uids",
            "prerequisite_knowledge_uids",
            "required_knowledge_uids",
            "inferred_knowledge_uids",
        ]
        all_uids: set[str] = set()
        for field_name in knowledge_fields:
            all_uids.update(self.get_field(field_name))
        return all_uids


# Type alias for backwards compatibility
GenericRelationships = DomainRelationships
