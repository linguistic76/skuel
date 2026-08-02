"""
Time Query Mixin
================

Provides date-based query operations for calendar and scheduling.

REQUIRES (Mixin Dependencies):
    - ConversionHelpersMixin: Uses _to_domain_models() for result conversion

PROVIDES (Methods for Calendar/Scheduling):
    - get_user_items_in_range_base: Generic date range query
    - get_user_items_in_range: Configured date range query
    - get_upcoming: Get entities upcoming within N days
    - get_overdue: Get entities past their due date
    - get_active: Get user's non-terminal entities
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from core.models.protocols import DomainModelProtocol, DTOProtocol
from core.models.type_hints import UserUID
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
    all Activity Domains. All Cypher execution is delegated to typed backend
    methods — no query builders are imported from the adapter layer.

    Required attributes from composing class:
        backend: B - Backend implementation
        logger: Logger - For debug logging
        entity_label: str - Neo4j base-label for Cypher matching (e.g., "Entity", "Ku")
        config_lookup_label: str - LABEL_CONFIGS registry key (e.g., "Task", "PathStep"),
            used for domain-specific logs.
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
    @abstractmethod
    def entity_label(self) -> str:
        """Neo4j base-label (e.g., ``"Entity"``, ``"Ku"``) - provided by composing class."""
        ...

    @property
    @abstractmethod
    def config_lookup_label(self) -> str:
        """LABEL_CONFIGS registry key (e.g., ``"Task"``, ``"PathStep"``) - provided by composing class."""
        ...

    @abstractmethod
    def _to_domain_models(
        self, data_list: builtins.list[Any], dto_class: type[DTOProtocol], model_class: type[T]
    ) -> builtins.list[T]:
        """Conversion method - provided by ConversionHelpersMixin."""
        ...

    @abstractmethod
    def _get_config_value(self, attr_name: str, default: Any = None) -> Any:
        """Config accessor - must be provided by composing class."""
        ...

    # ========================================================================
    # DATE RANGE QUERIES
    # ========================================================================

    async def get_user_items_in_range_base(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        date_field: str | builtins.list[str],
        dto_class: type[DTOProtocol],
        model_class: type[T],
        exclude_statuses: builtins.list[str] | None = None,
    ) -> Result[builtins.list[T]]:
        """
        Generic user items in date range query - DRY principle.

        This method consolidates the duplicate implementations across all 7 core services
        (tasks, goals, events, habits, finance, choices, principles).

        Args:
            user_uid: User identifier (REQUIRED)
            start_date: Start of date range
            end_date: End of date range
            date_field: Domain-specific date field name(s) — a list matches items
                where ANY of the fields falls inside the range (OR semantics)
            dto_class: DTO class for conversion (e.g., TaskDTO, GoalDTO)
            model_class: Domain model class (e.g., Task, Goal)
            exclude_statuses: List of status values to exclude (optional)

        Returns:
            Result containing list of domain model instances
        """
        if not user_uid:
            return Result.fail(Errors.validation(message="user_uid is required", field="user_uid"))

        if not date_field:
            return Result.fail(
                Errors.validation(message="date_field is required", field="date_field")
            )

        results = await self.backend.user_activity_range_raw(
            user_uid=user_uid,
            date_field=date_field,
            start_date=start_date,
            end_date=end_date,
            exclude_statuses=exclude_statuses or [],
        )

        if results.is_error:
            return Result.fail(results)

        items = self._to_domain_models(results.value, dto_class, model_class)

        self.logger.debug(
            f"Found {len(items)} {self.config_lookup_label}(s) for user {user_uid} "
            f"in range {start_date} to {end_date}"
        )

        return Result.ok(items)

    async def get_user_items_in_range(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
        date_field: str | builtins.list[str] | None = None,
    ) -> Result[builtins.list[T]]:
        """
        Get user's items in date range - unified implementation using class attributes.

        **CONSOLIDATED (November 27, 2025):** This method replaces the duplicate
        implementations that existed in each domain service. Domains now configure
        behavior via class attributes (_date_field, _completed_statuses, etc.)
        instead of overriding this method.

        Args:
            user_uid: User identifier
            start_date: Start of date range
            end_date: End of date range
            include_completed: Include completed/archived items (default False)
            date_field: Optional override of the domain's configured date field.
                A list matches items where ANY of the fields falls inside the
                range (OR semantics) — e.g. the calendar fetches Tasks by
                due_date OR scheduled_date. Default None uses DomainConfig.

        Returns:
            Result containing list of domain model instances
        """
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

        completed_statuses = self._get_config_value("completed_statuses", [])
        exclude_statuses = [] if include_completed else list(completed_statuses)

        if date_field is None:
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

    async def get_upcoming(
        self,
        days_ahead: int = 7,
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[builtins.list[T]]:
        """
        Get entities upcoming within specified number of days.

        Args:
            days_ahead: Number of days to look ahead (default 7)
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing upcoming entities, sorted by date
        """
        date_field = self._get_config_value("date_field", "created_at")

        if date_field == "created_at":
            self.logger.debug(
                f"{self.service_name}: get_upcoming() not meaningful for this domain "
                f"(date_field={date_field}). Override if custom logic needed."
            )
            return Result.ok([])

        if self._dto_class is None or self._model_class is None:
            return Result.fail(
                Errors.system(
                    message=f"{self.service_name} must configure _dto_class and _model_class",
                    operation="get_upcoming",
                )
            )

        exclude_statuses = list(self._get_config_value("temporal_exclude_statuses", []))

        result = await self.backend.upcoming_raw(
            date_field=date_field,
            days_ahead=days_ahead,
            exclude_statuses=exclude_statuses if exclude_statuses else None,
            user_uid=user_uid,
            limit=limit,
            secondary_sort_field=self._get_config_value("temporal_secondary_sort"),
        )
        if result.is_error:
            return Result.fail(result)

        items = self._to_domain_models(result.value, self._dto_class, self._model_class)

        self.logger.debug(
            f"Found {len(items)} {self.config_lookup_label}(s) upcoming within {days_ahead} days"
        )

        return Result.ok(items)

    async def get_overdue(
        self,
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[builtins.list[T]]:
        """
        Get entities past their due date.

        Args:
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing overdue entities, sorted by how overdue
        """
        date_field = self._get_config_value("date_field", "created_at")

        if date_field == "created_at":
            self.logger.debug(
                f"{self.service_name}: get_overdue() not meaningful for this domain "
                f"(date_field={date_field}). Override if custom logic needed."
            )
            return Result.ok([])

        if self._dto_class is None or self._model_class is None:
            return Result.fail(
                Errors.system(
                    message=f"{self.service_name} must configure _dto_class and _model_class",
                    operation="get_overdue",
                )
            )

        exclude_statuses = list(self._get_config_value("temporal_exclude_statuses", []))

        result = await self.backend.overdue_raw(
            date_field=date_field,
            exclude_statuses=exclude_statuses if exclude_statuses else None,
            user_uid=user_uid,
            limit=limit,
            secondary_sort_field=self._get_config_value("temporal_secondary_sort"),
        )
        if result.is_error:
            return Result.fail(result)

        items = self._to_domain_models(result.value, self._dto_class, self._model_class)

        self.logger.debug(f"Found {len(items)} overdue {self.config_lookup_label}(s)")

        return Result.ok(items)

    async def get_active(
        self,
        user_uid: UserUID,
        limit: int = 100,
    ) -> Result[builtins.list[T]]:
        """
        Get user's active (non-terminal) entities.

        Active = status NOT IN temporal_exclude_statuses (terminal states).
        Domains with different liveness semantics (e.g., Habits' frequency
        window, Principles' is_active flag) override this method.

        Args:
            user_uid: User UID — required (always user-scoped)
            limit: Maximum results to return

        Returns:
            Result containing active entities
        """
        if not user_uid:
            return Result.fail(Errors.validation(message="user_uid is required", field="user_uid"))

        if self._dto_class is None or self._model_class is None:
            return Result.fail(
                Errors.system(
                    message=f"{self.service_name} must configure _dto_class and _model_class",
                    operation="get_active",
                )
            )

        exclude_statuses = list(self._get_config_value("temporal_exclude_statuses", []))

        result = await self.backend.active_raw(
            user_uid=user_uid,
            exclude_statuses=exclude_statuses if exclude_statuses else None,
            limit=limit,
        )
        if result.is_error:
            return Result.fail(result)

        items = self._to_domain_models(result.value, self._dto_class, self._model_class)

        self.logger.debug(
            f"Found {len(items)} active {self.config_lookup_label}(s) for user {user_uid}"
        )

        return Result.ok(items)


# ============================================================================
# PROTOCOL COMPLIANCE VERIFICATION (January 2026)
# ============================================================================
if TYPE_CHECKING:
    from core.ports.base_service_interface import TimeQueryOperations

    _protocol_check: type[TimeQueryOperations[Any]] = TimeQueryMixin  # type: ignore[type-abstract]
