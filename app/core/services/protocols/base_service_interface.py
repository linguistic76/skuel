"""
BaseService Interface Protocols
================================

Explicit Protocol interfaces for BaseService mixins.

Purpose:
- Provides type-safe interface for all BaseService methods
- Enables IDE autocomplete for mixin methods (all 7 mixins)
- Documents complete BaseService public API
- Allows static type checking with MyPy

Real-World Usage Examples
-------------------------

1. Generic Service Handlers (Type Safety + Autocomplete):
    from core.services.protocols.base_service_interface import BaseServiceInterface
    from typing import Any

    def validate_service_health(
        service: BaseServiceInterface[Any, Any]
    ) -> dict[str, Any]:
        '''Check if service has required data for analysis.'''
        # IDE autocompletes: search, get_by_status, list_categories, etc.
        categories = service.list_categories()  # Type-checked!
        if categories.is_error:
            return {"healthy": False, "reason": "No categories"}
        return {"healthy": True, "categories": categories.value}

2. Service Container/Registry (Dependency Injection):
    from core.services.protocols.base_service_interface import BaseServiceInterface

    class ServiceRegistry:
        def __init__(self):
            self._services: dict[str, BaseServiceInterface[Any, Any]] = {}

        def register(self, name: str, service: BaseServiceInterface[Any, Any]):
            '''Register a service by name - works with ANY BaseService.'''
            self._services[name] = service

        def get_categories(self, service_name: str) -> list[str]:
            service = self._services[service_name]
            result = service.list_categories()  # IDE knows this method exists!
            return result.value if not result.is_error else []

3. Cross-Domain Analytics (Generic Operations):
    from core.services.protocols.base_service_interface import BaseServiceInterface

    async def analyze_domain_health(
        services: list[tuple[str, BaseServiceInterface[Any, Any]]]
    ) -> dict[str, dict]:
        '''Analyze health across multiple domains generically.'''
        health_report = {}
        for domain_name, service in services:
            # IDE provides autocomplete for all BaseService methods
            categories = await service.list_categories()
            statuses = await service.get_by_status("active")
            health_report[domain_name] = {
                "category_count": len(categories.value or []),
                "active_count": len(statuses.value or []),
            }
        return health_report

When NOT to Use BaseServiceInterface
-------------------------------------
For domain-specific operations, use concrete types or domain protocols:
- TasksService has create_task_with_context() - use TasksOperations
- GoalsService has get_milestones() - use GoalsOperations
- BaseServiceInterface only provides COMMON methods (search, CRUD, etc.)

Production Examples
-------------------
For real-world usage, see:
- /core/utils/service_introspection.py - Generic service utilities using BaseServiceInterface
  - get_service_capabilities() - Analyze service features generically
  - ServiceRegistry - Type-safe service container
  - get_domain_health_report() - Cross-domain analytics

See Also:
- /docs/reference/BASESERVICE_METHOD_INDEX.md - Complete method listing (35-50 methods)
- /docs/reference/SUB_SERVICE_CATALOG.md - Domain-specific method catalog
- /core/services/base_service.py - Implementation (7 mixins)
- /core/services/mixins/ - Individual mixin implementations

Version: 1.0.0
Date: 2026-01-29
"""

from __future__ import annotations

from datetime import date
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

from core.models.graph_context import GraphContext
from core.utils.result_simplified import Result

# Type variables for generics
T = TypeVar("T", contravariant=False, covariant=True)  # Domain model type
B = TypeVar("B")  # Backend operations type
DTO = TypeVar("DTO")  # DTO type


@runtime_checkable
class ConversionOperations(Protocol[T]):
    """
    Methods provided by ConversionHelpersMixin.

    Purpose: DTO ↔ Domain model conversion and result handling.

    Updated: 2026-01-29 - Signatures now match actual mixin implementation.
    """

    def _ensure_exists(
        self,
        result: Result[T | None],
        resource_name: str,
        identifier: str,
    ) -> Result[T]:
        """
        Convert Result[T | None] to Result[T] with proper null safety.

        Args:
            result: Result that might contain None
            resource_name: Human-readable resource type (e.g., "MOC", "Task")
            identifier: Resource identifier for error message

        Returns:
            Result[T] - guaranteed non-null value or error
        """
        ...

    def _to_domain_model(
        self,
        data: Any,
        dto_class: type[Any],
        model_class: type[T],
    ) -> T:
        """
        Convert backend data to domain model through DTO layer.

        Args:
            data: Raw data from backend (dict, DTO, or object)
            dto_class: DTO class for conversion
            model_class: Target domain model class

        Returns:
            Domain model instance
        """
        ...

    def _to_domain_models(
        self,
        data_list: list[Any],
        dto_class: type[Any],
        model_class: type[T],
    ) -> list[T]:
        """
        Convert list of backend data to domain models.

        Args:
            data_list: List of raw data from backend
            dto_class: DTO class for conversion
            model_class: Target domain model class

        Returns:
            List of domain model instances
        """
        ...

    def _from_domain_model(self, model: T, dto_class: type) -> Any:
        """
        Convert domain model to DTO for backend operations.

        Args:
            model: Domain model instance
            dto_class: Target DTO class

        Returns:
            DTO instance
        """
        ...

    def _records_to_domain_models(
        self,
        records: list[dict[str, Any]],
        node_key: str = "n",
    ) -> list[T]:
        """
        Extract nodes from query records and convert to domain models.

        Args:
            records: List of record dicts from execute_query
            node_key: Key containing the node data (default: "n")

        Returns:
            List of domain model instances
        """
        ...

    def _validate_required_user_uid(
        self,
        user_uid: str | None,
        operation: str,
    ) -> Result[Any] | None:
        """
        Validate that user_uid is present for an operation.

        Args:
            user_uid: The user UID to validate
            operation: Operation name for error message (e.g., "task creation")

        Returns:
            None if valid, Result.fail() if user_uid is missing
        """
        ...

    async def _create_and_convert(
        self,
        data: dict[str, Any],
        dto_class: type[Any],
        model_class: type[T],
    ) -> Result[T]:
        """
        Create entity in backend and convert to domain model.

        Args:
            data: Dictionary data to create (typically from dto.to_dict())
            dto_class: DTO class for conversion
            model_class: Domain model class for conversion

        Returns:
            Result containing created domain model
        """
        ...


@runtime_checkable
class CrudOperations(Protocol[T]):
    """
    Methods provided by CrudOperationsMixin.

    Purpose: CRUD operations with ownership verification.

    Updated: 2026-01-29 - Signatures now match actual mixin implementation.
    """

    async def create(self, entity: T) -> Result[T]:
        """
        Create a new entity.

        Args:
            entity: Domain model instance to create

        Returns:
            Result[T]: Created entity
        """
        ...

    async def get(self, uid: str) -> Result[T]:
        """
        Get entity by UID.

        Returns Result[T] - not found is an error, not a None value.

        Args:
            uid: Entity UID

        Returns:
            Result[T]: The entity if found, error otherwise
        """
        ...

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[T]:
        """
        Update entity (no ownership check).

        Args:
            uid: Entity UID
            updates: Dictionary of fields to update

        Returns:
            Result[T]: Updated entity
        """
        ...

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """
        Delete entity (no ownership check).

        Args:
            uid: Entity UID
            cascade: Whether to cascade delete relationships

        Returns:
            Result[bool]: True if deleted
        """
        ...

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
        user_uid: str | None = None,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[tuple[list[T], int]]:
        """
        List entities with pagination.

        Args:
            limit: Maximum number of entities to return
            offset: Number of entities to skip
            filters: Optional filters to apply
            sort_by: Field to sort by
            sort_order: Sort order ("asc" or "desc")
            user_uid: Optional user UID for user-specific filtering
            order_by: Alias for sort_by (deprecated, use sort_by)
            order_desc: Reverse sort order

        Returns:
            Result[tuple[list[T], int]]: (entities, total_count)
        """
        ...

    # Ownership-verified CRUD
    async def verify_ownership(self, uid: str, user_uid: str) -> Result[T]:
        """
        Get entity with ownership check (404 if not owned).

        Args:
            uid: Entity UID
            user_uid: User UID who should own the entity

        Returns:
            Result[T]: Entity if owned by user, error otherwise
        """
        ...

    async def get_for_user(self, uid: str, user_uid: str) -> Result[T]:
        """
        Alias for verify_ownership().

        Args:
            uid: Entity UID
            user_uid: User UID who should own the entity

        Returns:
            Result[T]: Entity if owned by user, error otherwise
        """
        ...

    async def update_for_user(
        self, uid: str, updates: dict[str, Any], user_uid: str
    ) -> Result[T]:
        """
        Update entity, but only if owned by the specified user.

        Args:
            uid: Entity UID to update
            updates: Dictionary of fields to update
            user_uid: User UID who should own the entity

        Returns:
            Result[T]: Updated entity if owned by user, error otherwise
        """
        ...

    async def delete_for_user(self, uid: str, user_uid: str, cascade: bool = False) -> Result[bool]:
        """
        Delete entity, but only if owned by the specified user.

        Args:
            uid: Entity UID to delete
            user_uid: User UID who should own the entity
            cascade: Whether to cascade delete relationships

        Returns:
            Result[bool]: True if deleted, error otherwise
        """
        ...


@runtime_checkable
class SearchOperations(Protocol[T]):
    """
    Methods provided by SearchOperationsMixin.

    Purpose: Text search, filtering, and graph-aware queries.

    Updated: 2026-01-29 - Signatures now match actual mixin implementation.
    """

    async def search(self, query: str, limit: int = 50) -> Result[list[T]]:
        """
        Text search across configured search fields.

        Args:
            query: Search string (case-insensitive)
            limit: Maximum results to return (default 50)

        Returns:
            Result containing matching entities
        """
        ...

    async def search_by_tags(
        self,
        tags: list[str],
        match_all: bool = False,
        limit: int = 50,
    ) -> Result[list[T]]:
        """
        Search entities by tags (array field search).

        Args:
            tags: List of tag values to search for
            match_all: If True, require ALL tags; if False, ANY tag matches
            limit: Maximum results (default 50)

        Returns:
            Result containing entities with matching tags
        """
        ...

    async def get_by_status(self, status: str, limit: int = 100) -> Result[list[T]]:
        """
        Filter entities by status field.

        Args:
            status: Status string (e.g., "active", "completed", "archived")
            limit: Maximum results to return

        Returns:
            Result containing entities with matching status
        """
        ...

    async def get_by_category(
        self, category: str, user_uid: str | None = None, limit: int = 100
    ) -> Result[list[T]]:
        """
        Filter entities by category field.

        Args:
            category: Category name to filter by
            user_uid: Optional user filter
            limit: Maximum results to return

        Returns:
            Result containing entities in the specified category
        """
        ...

    async def get_by_relationship(
        self,
        related_uid: str,
        relationship_type: Any,  # RelationshipName enum
        direction: str = "outgoing",
    ) -> Result[list[T]]:
        """
        Get entities connected via graph relationship.

        Args:
            related_uid: UID of the related entity (source node)
            relationship_type: Type-safe RelationshipName enum
            direction: "outgoing", "incoming", or "both" (default "outgoing")

        Returns:
            Result containing related entities
        """
        ...

    async def search_connected_to(
        self,
        query: str,
        related_uid: str,
        relationship_type: Any,  # RelationshipName enum
        direction: str = "outgoing",
        limit: int = 50,
    ) -> Result[list[T]]:
        """
        Graph-aware search: text search + relationship traversal in ONE query.

        Args:
            query: Search text (case-insensitive CONTAINS)
            related_uid: UID of the entity to traverse from
            relationship_type: Type-safe RelationshipName enum
            direction: "outgoing", "incoming", or "both" (default "outgoing")
            limit: Maximum results (default 50)

        Returns:
            Result containing entities matching query AND connected via relationship
        """
        ...

    async def graph_aware_faceted_search(
        self,
        request: Any,  # SearchRequest
        user_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Graph-aware faceted search - THE unified method for all domains.

        Args:
            request: SearchRequest with query and facets
            user_uid: User identifier for ownership and graph patterns

        Returns:
            Result[list[dict]]: Results with _graph_context enrichment
        """
        ...


@runtime_checkable
class RelationshipOperations(Protocol[T]):
    """
    Methods provided by RelationshipOperationsMixin.

    Purpose: Graph relationship operations and traversal.

    Updated: 2026-01-29 - Signatures now match actual mixin implementation.
    """

    async def add_relationship(
        self,
        from_uid: str,
        rel_type: str | Any,  # str or RelationshipName enum
        to_uid: str,
        properties: dict[str, Any] | None = None,
    ) -> Result[bool]:
        """
        Add a relationship between two entities.

        Args:
            from_uid: Source entity UID
            rel_type: Relationship type (string or RelationshipName enum)
            to_uid: Target entity UID
            properties: Optional relationship properties

        Returns:
            Result[bool]: True if relationship was created successfully
        """
        ...

    async def get_relationships(
        self,
        uid: str,
        rel_type: str | None = None,
        direction: str = "both",  # 'in', 'out', 'both'
    ) -> Result[list[Any]]:  # list[Relationship]
        """
        Get all relationships for an entity.

        Args:
            uid: Entity UID
            rel_type: Optional filter by relationship type
            direction: Direction of relationships to retrieve

        Returns:
            Result[list[Relationship]]: Entity relationships
        """
        ...

    async def traverse(
        self, start_uid: str, rel_pattern: str, max_depth: int = 3, include_properties: bool = False
    ) -> Result[list[Any]]:  # list[GraphPath]
        """
        Traverse the graph following a relationship pattern.

        Args:
            start_uid: Starting entity UID
            rel_pattern: Pattern like "REQUIRES*" or "ENABLES+"
            max_depth: Maximum traversal depth
            include_properties: Include relationship properties

        Returns:
            Result[list[GraphPath]]: Traversal paths
        """
        ...

    async def get_prerequisites(self, uid: str, depth: int = 3) -> Result[list[T]]:
        """
        Get prerequisite entities.

        Args:
            uid: Entity UID
            depth: Maximum depth to traverse (default: 3)

        Returns:
            Result[list[T]]: Prerequisite entities
        """
        ...

    async def get_enables(self, uid: str, depth: int = 3) -> Result[list[T]]:
        """
        Get entities enabled by this entity.

        Args:
            uid: Entity UID
            depth: Maximum depth to traverse (default: 3)

        Returns:
            Result[list[T]]: Entities that this entity enables
        """
        ...

    async def add_prerequisite(
        self,
        entity_uid: str,
        prerequisite_uid: str,
        confidence: float = 1.0,
    ) -> Result[bool]:
        """
        Add a prerequisite relationship.

        Args:
            entity_uid: The entity that requires the prerequisite
            prerequisite_uid: The prerequisite entity UID
            confidence: Relationship confidence (0.0-1.0)

        Returns:
            Result[bool]: True if relationship was created
        """
        ...

    async def get_hierarchy(self, uid: str) -> Result[dict[str, Any]]:
        """
        Get hierarchical structure for this entity.

        Args:
            uid: Entity UID

        Returns:
            Result[dict]: Hierarchical context with parents and children
        """
        ...


@runtime_checkable
class TimeQueryOperations(Protocol[T]):
    """
    Methods provided by TimeQueryMixin.

    Purpose: Calendar and scheduling queries.

    Updated: 2026-01-29 - Signatures now match actual mixin implementation.
    """

    async def get_user_items_in_range(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
    ) -> Result[list[T]]:
        """
        Get user's items in date range.

        Args:
            user_uid: User UID
            start_date: Range start date
            end_date: Range end date
            include_completed: Whether to include completed items

        Returns:
            Result[list[T]]: Entities in the date range
        """
        ...

    async def get_due_soon(
        self,
        days_ahead: int = 7,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[list[T]]:
        """
        Get entities due within specified number of days.

        Args:
            days_ahead: Number of days ahead to check
            user_uid: Optional user filter
            limit: Maximum results to return

        Returns:
            Result[list[T]]: Entities due soon
        """
        ...

    async def get_overdue(
        self,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[list[T]]:
        """
        Get entities past their due date.

        Args:
            user_uid: Optional user filter
            limit: Maximum results to return

        Returns:
            Result[list[T]]: Overdue entities
        """
        ...


@runtime_checkable
class UserProgressOperations(Protocol[T]):
    """
    Methods provided by UserProgressMixin.

    Purpose: Progress and mastery tracking (curriculum-origin, now universal).
    """

    async def get_user_progress(self, user_uid: str, entity_uid: str) -> Result[dict[str, Any]]:
        """
        Get user's progress/mastery for an entity.

        Args:
            user_uid: User UID
            entity_uid: Entity UID

        Returns:
            Result[dict]: Progress stats for entity
        """
        ...

    async def update_user_mastery(
        self,
        user_uid: str,
        entity_uid: str,
        mastery_level: float,
    ) -> Result[bool]:
        """
        Update user's mastery level for an entity.

        Args:
            user_uid: User UID
            entity_uid: Entity UID
            mastery_level: Mastery score (0.0-1.0)

        Returns:
            Result[bool]: True if updated
        """
        ...

    async def get_user_curriculum(
        self,
        user_uid: str,
        include_completed: bool = False,
    ) -> Result[list[T]]:
        """
        Get entities the user is studying/has mastered.

        Args:
            user_uid: User UID
            include_completed: Whether to include completed items

        Returns:
            Result[list[T]]: Entities in user's curriculum
        """
        ...


@runtime_checkable
class ContextOperations(Protocol[T]):
    """
    Methods provided by ContextOperationsMixin.

    Purpose: Retrieve entities with enriched graph context.

    Updated: 2026-01-29 - Signatures now match actual mixin implementation.
    """

    async def get_with_content(self, uid: str) -> Result[T]:
        """Get entity with content fields populated."""
        ...

    async def get_with_context(
        self,
        uid: str,
        depth: int = 2,
        min_confidence: float = 0.7,
        include_relationships: Any | None = None,  # Sequence[str]
        exclude_relationships: Any | None = None,  # Sequence[str]
    ) -> Result[T]:
        """
        Get entity with graph neighborhood context.

        Args:
            uid: Entity UID
            depth: Maximum graph traversal depth
            min_confidence: Minimum relationship confidence to include
            include_relationships: Optional whitelist of relationship types
            exclude_relationships: Optional blacklist of relationship types

        Returns:
            Result[T]: Entity with graph_context metadata
        """
        ...

    async def _basic_get_with_context(
        self,
        uid: str,
        depth: int = 2,
        min_confidence: float = 0.7,
    ) -> Result[T]:
        """
        Basic get_with_context for entities not in UnifiedRelationshipRegistry.

        Args:
            uid: Entity UID
            depth: Maximum graph traversal depth
            min_confidence: Minimum relationship confidence to include

        Returns:
            Result[T]: Entity with graph_context metadata
        """
        ...


@runtime_checkable
class BaseServiceInterface(
    ConversionOperations[T],
    CrudOperations[T],
    SearchOperations[T],
    RelationshipOperations[T],
    TimeQueryOperations[T],
    UserProgressOperations[T],
    ContextOperations[T],
    Protocol[T],
):
    """
    Complete BaseService interface.

    Combines all 7 mixin interfaces into a unified protocol.

    This protocol represents the FULL public API of BaseService:
    - ConversionHelpersMixin: DTO conversion
    - CrudOperationsMixin: CRUD + ownership verification
    - SearchOperationsMixin: Search and filtering
    - RelationshipOperationsMixin: Graph relationships
    - TimeQueryMixin: Date-based queries
    - UserProgressMixin: Progress tracking
    - ContextOperationsMixin: Graph context retrieval

    Use this protocol for type hints when you need the complete BaseService interface.

    Example:
        def process_items(service: BaseServiceInterface[Task]) -> Result[list[Task]]:
            # IDE will autocomplete ALL BaseService methods
            return await service.search("query", limit=10)

    Type Parameters:
        T: Domain model type (e.g., Task, Goal, Habit)

    See Also:
        - /docs/reference/BASESERVICE_METHOD_INDEX.md - All methods
        - /core/services/base_service.py - Implementation
        - /core/services/mixins/ - Individual mixins
    """

    # Additional BaseService-specific attributes/methods
    @property
    def entity_label(self) -> str:
        """Return the graph label for entities (e.g., 'Task', 'Goal')."""
        ...

    @property
    def service_name(self) -> str:
        """Return the service name for logging (e.g., 'tasks', 'goals')."""
        ...


# Convenient type aliases for common use cases
ActivityService = BaseServiceInterface[Any]  # Generic activity service
DomainService = BaseServiceInterface[Any]  # Generic domain service
