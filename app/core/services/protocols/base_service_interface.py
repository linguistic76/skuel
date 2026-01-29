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
    """

    def _to_domain_model(self, dto: Any) -> T:
        """Convert DTO to domain model."""
        ...

    def _from_domain_model(self, model: T) -> Any:
        """Convert domain model to DTO."""
        ...

    def _to_domain_models(self, dtos: list[Any]) -> list[T]:
        """Convert list of DTOs to domain models."""
        ...

    def _ensure_exists(self, result: Result[T | None]) -> Result[T]:
        """Convert None result to NotFound error."""
        ...

    def _records_to_domain_models(self, records: list[Any]) -> list[T]:
        """Convert Neo4j records to domain models."""
        ...

    async def _create_and_convert(self, **properties: Any) -> Result[T]:
        """Create entity and convert to domain model."""
        ...


@runtime_checkable
class CrudOperations(Protocol[T]):
    """
    Methods provided by CrudOperationsMixin.

    Purpose: CRUD operations with ownership verification.
    """

    async def create(self, **kwargs: Any) -> Result[T]:
        """Create new entity."""
        ...

    async def get(self, uid: str) -> Result[T | None]:
        """Get entity by UID (no ownership check)."""
        ...

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[T]:
        """Update entity (no ownership check)."""
        ...

    async def delete(self, uid: str) -> Result[bool]:
        """Delete entity (no ownership check)."""
        ...

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Result[tuple[list[T], int]]:
        """List entities with pagination (entities, total_count)."""
        ...

    # Ownership-verified CRUD
    async def verify_ownership(self, uid: str, user_uid: str) -> Result[T]:
        """Get entity with ownership check (404 if not owned)."""
        ...

    async def get_for_user(self, uid: str, user_uid: str) -> Result[T]:
        """Alias for verify_ownership()."""
        ...

    async def update_for_user(
        self, uid: str, user_uid: str, updates: dict[str, Any]
    ) -> Result[T]:
        """Update with ownership verification."""
        ...

    async def delete_for_user(self, uid: str, user_uid: str) -> Result[bool]:
        """Delete with ownership verification."""
        ...


@runtime_checkable
class SearchOperations(Protocol[T]):
    """
    Methods provided by SearchOperationsMixin.

    Purpose: Text search, filtering, and graph-aware queries.
    """

    async def search(
        self, query: str, limit: int = 100, user_uid: str | None = None
    ) -> Result[list[T]]:
        """Full-text search across configured search fields."""
        ...

    async def search_by_tags(
        self, tags: list[str], user_uid: str | None = None
    ) -> Result[list[T]]:
        """Filter by tags."""
        ...

    async def get_by_status(
        self, status: Any, user_uid: str | None = None
    ) -> Result[list[T]]:
        """Filter by status."""
        ...

    async def get_by_category(
        self, category: str, user_uid: str | None = None
    ) -> Result[list[T]]:
        """Filter by category/domain."""
        ...

    async def list_categories(self, user_uid: str | None = None) -> Result[list[str]]:
        """Get available categories."""
        ...

    async def get_by_relationship(
        self, relationship_type: str, target_uid: str
    ) -> Result[list[T]]:
        """Find entities with specific relationship."""
        ...

    async def search_connected_to(
        self, target_uid: str, relationship_type: str, direction: str = "outgoing"
    ) -> Result[list[T]]:
        """Graph traversal search."""
        ...

    async def graph_aware_faceted_search(
        self, filters: dict[str, Any], include_graph_context: bool = False
    ) -> Result[dict[str, Any]]:
        """Advanced search with optional graph context."""
        ...


@runtime_checkable
class RelationshipOperations(Protocol[T]):
    """
    Methods provided by RelationshipOperationsMixin.

    Purpose: Graph relationship operations and traversal.
    """

    async def add_relationship(
        self,
        from_uid: str,
        to_uid: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> Result[bool]:
        """Create relationship between entities."""
        ...

    async def get_relationships(
        self, uid: str, direction: str = "both"
    ) -> Result[list[dict[str, Any]]]:
        """Get relationships for entity."""
        ...

    async def traverse(
        self,
        start_uid: str,
        relationship_types: list[str],
        depth: int = 2,
        direction: str = "outgoing",
    ) -> Result[list[T]]:
        """Graph traversal from start node."""
        ...

    async def get_prerequisites(self, uid: str) -> Result[list[T]]:
        """Get prerequisite entities (configured via DomainConfig)."""
        ...

    async def get_enables(self, uid: str) -> Result[list[T]]:
        """Get entities this enables (configured via DomainConfig)."""
        ...

    async def add_prerequisite(
        self, uid: str, prerequisite_uid: str
    ) -> Result[bool]:
        """Add prerequisite relationship."""
        ...

    async def get_hierarchy(
        self, uid: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """Get hierarchical structure."""
        ...


@runtime_checkable
class TimeQueryOperations(Protocol[T]):
    """
    Methods provided by TimeQueryMixin.

    Purpose: Calendar and scheduling queries.
    """

    async def get_user_items_in_range(
        self, user_uid: str, start_date: date, end_date: date
    ) -> Result[list[T]]:
        """Get entities in date range (uses DomainConfig.date_field)."""
        ...

    async def get_due_soon(
        self, user_uid: str, days: int = 7
    ) -> Result[list[T]]:
        """Get entities due within N days."""
        ...

    async def get_overdue(self, user_uid: str) -> Result[list[T]]:
        """Get overdue entities."""
        ...


@runtime_checkable
class UserProgressOperations(Protocol[T]):
    """
    Methods provided by UserProgressMixin.

    Purpose: Progress and mastery tracking (curriculum-origin, now universal).
    """

    async def get_user_progress(
        self, uid: str, user_uid: str
    ) -> Result[dict[str, Any]]:
        """Get progress stats for entity."""
        ...

    async def update_user_mastery(
        self, uid: str, user_uid: str, mastery_level: float
    ) -> Result[bool]:
        """Update mastery score (0.0-1.0)."""
        ...

    async def get_user_curriculum(self, user_uid: str) -> Result[list[T]]:
        """Get user's curriculum entities."""
        ...


@runtime_checkable
class ContextOperations(Protocol[T]):
    """
    Methods provided by ContextOperationsMixin.

    Purpose: Retrieve entities with enriched graph context.
    """

    async def get_with_content(self, uid: str) -> Result[T]:
        """Get entity with content fields populated."""
        ...

    async def get_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[T, GraphContext]]:
        """Get entity with graph neighborhood (entity, graph_context)."""
        ...

    async def _basic_get_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[T, GraphContext]]:
        """Internal implementation of get_with_context."""
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
