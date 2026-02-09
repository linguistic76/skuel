"""
Generic Repository Pattern
==========================

A simplified, generic repository pattern that eliminates the need for
hundreds of lines of repetitive port interfaces. Provides core CRUD
operations plus flexible query capabilities.

Key Benefits:
- 5 core methods replace 30+ specific methods
- Type-safe with generics
- Flexible filtering without method explosion
- ~90% code reduction for ports
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from core.utils.result_simplified import Errors, Result

# ============================================================================
# QUERY SPECIFICATION PATTERN
# ============================================================================


class FilterOperator(Enum):
    """Supported filter operators"""

    EQUALS = "="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_OR_EQUAL = ">="
    LESS_OR_EQUAL = "<="
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    BETWEEN = "between"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


@dataclass
class Filter:
    """A single filter condition"""

    field: str
    operator: FilterOperator
    value: Any

    @classmethod
    def eq(cls, field: str, value: Any) -> "Filter":
        """Convenience factory for equality filter"""
        return cls(field, FilterOperator.EQUALS, value)

    @classmethod
    def contains(cls, field: str, value: str) -> "Filter":
        """Convenience factory for contains filter"""
        return cls(field, FilterOperator.CONTAINS, value)

    @classmethod
    def between(cls, field: str, start: Any, end: Any) -> "Filter":
        """Convenience factory for between filter"""
        return cls(field, FilterOperator.BETWEEN, (start, end))


@dataclass
class QuerySpec:
    """
    Specification for complex queries.

    Replaces dozens of specific query methods with a single flexible pattern.
    """

    filters: list[Filter] = field(default_factory=list)
    order_by: str | None = None
    order_desc: bool = False
    limit: int | None = None
    offset: int = 0
    includes: list[str] = field(default_factory=list)  # Related entities to include

    def where(self, field: str, operator: FilterOperator, value: Any) -> "QuerySpec":
        """Fluent interface for adding filters"""
        self.filters.append(Filter(field, operator, value))
        return self

    def where_eq(self, field: str, value: Any) -> "QuerySpec":
        """Shorthand for equality filter"""
        return self.where(field, FilterOperator.EQUALS, value)

    def order(self, field: str, desc: bool = False) -> "QuerySpec":
        """Fluent interface for ordering"""
        self.order_by = field
        self.order_desc = desc
        return self

    def paginate(self, limit: int, offset: int = 0) -> "QuerySpec":
        """Fluent interface for pagination"""
        self.limit = limit
        self.offset = offset
        return self

    def include(self, *relations: str) -> "QuerySpec":
        """Specify related entities to eagerly load"""
        self.includes.extend(relations)
        return self


# ============================================================================
# GENERIC REPOSITORY PROTOCOL
# ============================================================================


class Repository[T, ID](Protocol):
    """
    Generic repository protocol with 5 core methods.

    This replaces hundreds of lines of specific query methods with
    a flexible, composable query pattern.

    Type Parameters:
        T: Domain entity type
        ID: ID type (usually str)
    """

    async def get(self, id: ID) -> Result[T | None]:
        """
        Get a single entity by ID.

        Returns:
            Result.ok(entity) if found
            Result.ok(None) if not found
            Result.fail(error) if operation failed
        """
        ...

    async def find(self, spec: QuerySpec) -> Result[list[T]]:
        """
        Find entities matching a query specification.

        This single method replaces dozens of specific query methods like:
        - get_by_status()
        - get_by_date_range()
        - get_by_category()
        - search_by_title()
        - etc.

        Example:
            # Replace get_journals_by_date_range(start, end)
            spec = QuerySpec().where_between("entry_date", start, end)

            # Replace get_draft_journals()
            spec = QuerySpec().where_eq("status", "draft")

            # Complex query with ordering and pagination
            spec = (QuerySpec()
                .where_eq("status", "published")
                .where("created_at", FilterOperator.GREATER_THAN, yesterday)
                .order("created_at", desc=True)
                .paginate(QueryLimit.SMALL))
        """
        ...

    async def save(self, entity: T) -> Result[T]:
        """
        Save an entity (create or update).

        Intelligently determines whether to create or update based on
        entity state (e.g., presence of ID).
        """
        ...

    async def delete(self, id: ID) -> Result[bool]:
        """
        Delete an entity by ID.

        Returns:
            Result.ok(True) if deleted
            Result.ok(False) if not found
            Result.fail(error) if operation failed
        """
        ...

    async def count(self, spec: QuerySpec | None = None) -> Result[int]:
        """
        Count entities matching a query specification.

        If no spec provided, counts all entities.
        """
        ...


# ============================================================================
# BASE REPOSITORY IMPLEMENTATION
# ============================================================================


class BaseRepository[T, ID](ABC):
    """
    Base implementation with common patterns.

    Concrete repositories can extend this to add domain-specific behavior
    while inheriting the standard implementation.

    Type Parameters:
        T: Domain entity type
        ID: ID type (usually str)
    """

    def __init__(self, entity_name: str) -> None:
        self.entity_name = entity_name

    @abstractmethod
    async def _do_get(self, id: ID) -> T | None:
        """Backend-specific get implementation"""
        pass

    @abstractmethod
    async def _do_find(self, spec: QuerySpec) -> list[T]:
        """Backend-specific find implementation"""
        pass

    @abstractmethod
    async def _do_save(self, entity: T) -> T:
        """Backend-specific save implementation"""
        pass

    @abstractmethod
    async def _do_delete(self, id: ID) -> bool:
        """Backend-specific delete implementation"""
        pass

    @abstractmethod
    async def _do_count(self, spec: QuerySpec | None) -> int:
        """Backend-specific count implementation"""
        pass

    async def get(self, id: ID) -> Result[T | None]:
        """Get with standard error handling"""
        try:
            entity = await self._do_get(id)
            return Result.ok(entity)
        except Exception as e:
            return Result.fail(
                Errors.database(
                    operation="get",
                    message=f"Failed to get {self.entity_name} {id}: {e}",
                    entity=self.entity_name,
                    id=id,
                )
            )

    async def find(self, spec: QuerySpec) -> Result[list[T]]:
        """Find with standard error handling"""
        try:
            entities = await self._do_find(spec)
            return Result.ok(entities)
        except Exception as e:
            return Result.fail(
                Errors.database(
                    operation="find",
                    message=f"Failed to find {self.entity_name}: {e}",
                    entity=self.entity_name,
                    filters=len(spec.filters),
                )
            )

    async def save(self, entity: T) -> Result[T]:
        """Save with standard error handling"""
        try:
            saved = await self._do_save(entity)
            return Result.ok(saved)
        except Exception as e:
            return Result.fail(
                Errors.database(
                    operation="save",
                    message=f"Failed to save {self.entity_name}: {e}",
                    entity=self.entity_name,
                )
            )

    async def delete(self, id: ID) -> Result[bool]:
        """Delete with standard error handling"""
        try:
            deleted = await self._do_delete(id)
            return Result.ok(deleted)
        except Exception as e:
            return Result.fail(
                Errors.database(
                    operation="delete",
                    message=f"Failed to delete {self.entity_name} {id}: {e}",
                    entity=self.entity_name,
                    id=id,
                )
            )

    async def count(self, spec: QuerySpec | None = None) -> Result[int]:
        """Count with standard error handling"""
        try:
            total = await self._do_count(spec)
            return Result.ok(total)
        except Exception as e:
            return Result.fail(
                Errors.database(
                    operation="count",
                    message=f"Failed to count {self.entity_name}: {e}",
                    entity=self.entity_name,
                )
            )


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
# Instead of 712 lines of a monolithic backend port:

class ReportRepository(Repository[Report, str]):
    pass  # That's it! 5 methods instead of 36

# Usage in service:
async def get_draft_reports(self, repo: ReportRepository):
    spec = QuerySpec().where_eq("status", "draft").order("created_at", desc=True)
    return await repo.find(spec)

async def get_reports_by_date(self, repo: ReportRepository, start: date, end: date):
    spec = QuerySpec().where("entry_date", FilterOperator.BETWEEN, (start, end))
    return await repo.find(spec)

async def search_reports(self, repo: ReportRepository, query: str):
    spec = QuerySpec().where("content", FilterOperator.CONTAINS, query).limit(10)
    return await repo.find(spec)

# For domain-specific needs, extend the base:
class ReportRepositoryExtended(Repository[Report, str]):
    # Only add truly unique domain operations
    async def extract_insights(self, id: str) -> Result[dict]:
        # Domain-specific logic
        pass

# Neo4j implementation:
class Neo4jReportRepository(BaseRepository[Report, str]):
    def __init__(self, driver):
        super().__init__("Report")
        self.driver = driver

    async def _do_get(self, id: str) -> Optional[Report]:
        # Neo4j specific implementation
        query = "MATCH (r:Report {uid: $uid}) RETURN r"
        # ... execute and map

    async def _do_find(self, spec: QuerySpec) -> list[Report]:
        # Build Cypher from QuerySpec
        query = self._build_query(spec)
        # ... execute and map

# The service doesn't change:
class ReportService:
    def __init__(self, repo: ReportRepository):
        self.repo = repo  # Still uses protocol
"""
