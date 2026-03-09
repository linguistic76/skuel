"""
Time Query Mixin
================

Provides date-based query operations for calendar and scheduling.

REQUIRES (Mixin Dependencies):
    - ConversionHelpersMixin: Uses _to_domain_models() for result conversion

PROVIDES (Methods for Calendar/Scheduling):
    - get_user_items_in_range_base: Generic date range query
    - get_user_items_in_range: Configured date range query
    - get_due_soon: Get entities due within N days
    - get_overdue: Get entities past their due date

Methods:
    - get_user_items_in_range_base: Generic date range query
    - get_user_items_in_range: Configured date range query
    - get_due_soon: Get entities due within N days
    - get_overdue: Get entities past their due date
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from core.models.protocols import DomainModelProtocol, DTOProtocol
from adapters.persistence.neo4j.query import build_user_activity_query
from core.ports import BackendOperations
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    from datetime import date
    from logging import Logger


class TimeQueryMixin[B: BackendOperations, T: DomainModelProtocol]:
    """
    Mixin providing date-based query operations.

    These methods enable calendar integration and scheduling queries across
    all Activity Domains.

    Required attributes from composing class:
        backend: B - Backend implementation
        logger: Logger - For debug logging
        entity_label: str - Neo4j node label
        service_name: str - For error messages
        _date_field: str - Date field for range queries
        _completed_statuses: list[str] - Statuses to exclude
        _dto_class: type[DTOProtocol] - DTO class
        _model_class: type[T] - Domain model class
        _to_domain_models: Conversion method
        _get_config_value: Config accessor method
    """

    # Type hints for attributes that must be provided by composing class
    backend: B
    logger: Logger
    service_name: str
    _date_field: str
    _completed_statuses: ClassVar[list[str]]
    _dto_class: type[DTOProtocol] | None
    _model_class: type[T] | None

    @property
    def entity_label(self) -> str:
        """Entity label - must be provided by composing class."""
        raise NotImplementedError

    def _to_domain_models(
        self, data_list: builtins.list[Any], dto_class: type[DTOProtocol], model_class: type[T]
    ) -> builtins.list[T]:
        """Conversion method - provided by ConversionHelpersMixin."""
        raise NotImplementedError

    def _get_config_value(self, attr_name: str, default: Any = None) -> Any:
        """Config accessor - must be provided by composing class."""
        raise NotImplementedError

    # ========================================================================
    # DATE RANGE QUERIES
    # ========================================================================

    async def get_user_items_in_range_base(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        date_field: str,
        dto_class: type[DTOProtocol],
        model_class: type[T],
        exclude_statuses: builtins.list[str] | None = None,
    ) -> Result[builtins.list[T]]:
        """
        Generic user items in date range query - DRY principle.

        This method consolidates the duplicate implementations across all 7 core services
        (tasks, goals, events, habits, finance, choices, principles).

        Pattern:
        1. Build Cypher query using CypherGenerator.build_user_activity_query()
        2. Execute query against backend
        3. Convert results to domain models using _to_domain_models()

        Args:
            user_uid: User identifier (REQUIRED)
            start_date: Start of date range
            end_date: End of date range
            date_field: Domain-specific date field name
            dto_class: DTO class for conversion (e.g., TaskDTO, GoalDTO)
            model_class: Domain model class (e.g., Task, Goal)
            exclude_statuses: List of status values to exclude (optional)

        Returns:
            Result containing list of domain model instances
        """
        # Validate required parameters
        if not user_uid:
            return Result.fail(Errors.validation(message="user_uid is required", field="user_uid"))

        if not date_field:
            return Result.fail(
                Errors.validation(message="date_field is required", field="date_field")
            )

        # Build Cypher query using unified helper
        query, params = build_user_activity_query(
            user_uid=user_uid,
            node_label=self.entity_label,  # Uses abstract property!
            date_field=date_field,
            start_date=start_date,
            end_date=end_date,
            exclude_statuses=exclude_statuses or [],
        )

        # Execute query
        results = await self.backend.execute_query(query, params)

        # Handle query errors
        if results.is_error:
            return Result.fail(results.expect_error())

        # Convert to domain models using existing helper
        items = self._to_domain_models(results.value, dto_class, model_class)

        # Log for debugging
        self.logger.debug(
            f"Found {len(items)} {self.entity_label}(s) for user {user_uid} "
            f"in range {start_date} to {end_date}"
        )

        return Result.ok(items)

    async def get_user_items_in_range(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
    ) -> Result[builtins.list[T]]:
        """
        Get user's items in date range - unified implementation using class attributes.

        **CONSOLIDATED (November 27, 2025):** This method replaces the duplicate
        implementations that existed in each domain service. Domains now configure
        behavior via class attributes (_date_field, _completed_statuses, etc.)
        instead of overriding this method.

        **Class Attributes Used:**
        - _date_field: Date field for range query (e.g., "due_date", "target_date")
        - _completed_statuses: Statuses to exclude when include_completed=False
        - _dto_class: DTO class for conversion
        - _model_class: Domain model class for conversion

        This provides a unified query API for meta-services (Calendar, Reports)
        that need consistent querying across all activity domains.

        Args:
            user_uid: User identifier
            start_date: Start of date range
            end_date: End of date range
            include_completed: Include completed/archived items (default False)

        Returns:
            Result containing list of domain model instances
        """
        # Fail-fast: configuration is required
        dto_class = self._get_config_value("dto_class")
        model_class = self._get_config_value("model_class")

        if dto_class is None or model_class is None:
            return Result.fail(
                Errors.system(
                    message=f"{self.service_name} must configure dto_class and model_class "
                    "via DomainConfig or class attributes",
                    operation="get_user_items_in_range",
                )
            )

        # Determine statuses to exclude (use config accessor)
        completed_statuses = self._get_config_value("completed_statuses", [])
        exclude_statuses = [] if include_completed else list(completed_statuses)

        # Delegate to base implementation (use config-accessed values)
        date_field = self._get_config_value("date_field", "created_at")

        return await self.get_user_items_in_range_base(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            date_field=date_field,
            dto_class=dto_class,
            model_class=model_class,
            exclude_statuses=exclude_statuses,
        )

    # ========================================================================
    # TIME-BASED QUERIES (January 2026)
    # ========================================================================

    async def get_due_soon(
        self,
        days_ahead: int = 7,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[builtins.list[T]]:
        """
        Get entities due within specified number of days.

        Uses class-configured _date_field for date comparison and
        _completed_statuses for exclusion filtering. Sorts by date
        field ASC (nearest first).

        Args:
            days_ahead: Number of days to look ahead (default 7)
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing entities due soon, sorted by date

        Note:
            Returns empty list for domains without meaningful date field
            (i.e., _date_field == "created_at"). Override this method if
            domain uses custom "due" logic (e.g., Habits use frequency-based
            calculations).
        """
        from adapters.persistence.neo4j.query.cypher import build_due_soon_query

        # Get configured date field
        date_field = self._get_config_value("date_field", "created_at")

        # If date_field is created_at (default), this domain likely doesn't have
        # meaningful "due soon" semantics - return empty list
        if date_field == "created_at":
            self.logger.debug(
                f"{self.service_name}: get_due_soon() not meaningful for this domain "
                f"(date_field={date_field}). Override if custom logic needed."
            )
            return Result.ok([])

        # Validate configuration
        if self._dto_class is None or self._model_class is None:
            return Result.fail(
                Errors.system(
                    message=f"{self.service_name} must configure _dto_class and _model_class",
                    operation="get_due_soon",
                )
            )

        # Get statuses to exclude from temporal queries
        exclude_statuses = list(self._get_config_value("temporal_exclude_statuses", []))

        # Build and execute query
        query, params = build_due_soon_query(
            node_label=self.entity_label,
            date_field=date_field,
            days_ahead=days_ahead,
            exclude_statuses=exclude_statuses if exclude_statuses else None,
            user_uid=user_uid,
            limit=limit,
            secondary_sort_field=self._get_config_value("temporal_secondary_sort"),
        )

        result = await self.backend.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to domain models
        items = self._to_domain_models(result.value, self._dto_class, self._model_class)

        self.logger.debug(f"Found {len(items)} {self.entity_label}(s) due within {days_ahead} days")

        return Result.ok(items)

    async def get_overdue(
        self,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[builtins.list[T]]:
        """
        Get entities past their due date.

        Uses class-configured _date_field for date comparison and
        _completed_statuses for exclusion filtering. Sorts by date
        field ASC (oldest first - most overdue first).

        Args:
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing overdue entities, sorted by how overdue

        Note:
            Returns empty list for domains without meaningful date field
            (i.e., _date_field == "created_at"). Override this method if
            domain uses custom "overdue" logic.
        """
        from adapters.persistence.neo4j.query.cypher import build_overdue_query

        # Get configured date field
        date_field = self._get_config_value("date_field", "created_at")

        # If date_field is created_at (default), this domain likely doesn't have
        # meaningful "overdue" semantics - return empty list
        if date_field == "created_at":
            self.logger.debug(
                f"{self.service_name}: get_overdue() not meaningful for this domain "
                f"(date_field={date_field}). Override if custom logic needed."
            )
            return Result.ok([])

        # Validate configuration
        if self._dto_class is None or self._model_class is None:
            return Result.fail(
                Errors.system(
                    message=f"{self.service_name} must configure _dto_class and _model_class",
                    operation="get_overdue",
                )
            )

        # Get statuses to exclude from temporal queries
        exclude_statuses = list(self._get_config_value("temporal_exclude_statuses", []))

        # Build and execute query
        query, params = build_overdue_query(
            node_label=self.entity_label,
            date_field=date_field,
            exclude_statuses=exclude_statuses if exclude_statuses else None,
            user_uid=user_uid,
            limit=limit,
            secondary_sort_field=self._get_config_value("temporal_secondary_sort"),
        )

        result = await self.backend.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to domain models
        items = self._to_domain_models(result.value, self._dto_class, self._model_class)

        self.logger.debug(f"Found {len(items)} overdue {self.entity_label}(s)")

        return Result.ok(items)


# ============================================================================
# PROTOCOL COMPLIANCE VERIFICATION (January 2026)
# ============================================================================
if TYPE_CHECKING:
    from core.ports.base_service_interface import TimeQueryOperations

    _protocol_check: type[TimeQueryOperations[Any]] = TimeQueryMixin  # type: ignore[type-arg]
