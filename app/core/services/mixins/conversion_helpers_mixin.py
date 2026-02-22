"""
Conversion Helpers Mixin
========================

Provides DTO/domain model conversion and result handling helpers.

These are foundational methods used by other mixins and service methods
for converting between backend data and domain models.

REQUIRES (Mixin Dependencies):
    - None - This is a foundational mixin with no dependencies

PROVIDES (Methods for Other Mixins):
    - _ensure_exists: Convert Result[T | None] to Result[T] with null safety
    - _to_domain_model: Convert backend data to domain model
    - _to_domain_models: Bulk convert backend data to domain models
    - _from_domain_model: Convert domain model to DTO
    - _records_to_domain_models: Extract and convert Neo4j query records
    - _validate_required_user_uid: Validate presence of user_uid
    - _create_and_convert: Create entity and convert to domain model

Methods:
    - _ensure_exists: Convert Result[T | None] to Result[T] with null safety
    - _to_domain_model: Convert backend data to domain model
    - _to_domain_models: Bulk convert backend data to domain models
    - _from_domain_model: Convert domain model to DTO
    - _records_to_domain_models: Extract and convert Neo4j query records
    - _validate_required_user_uid: Validate presence of user_uid
    - _create_and_convert: Create entity and convert to domain model
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.protocols import DomainModelProtocol, DTOProtocol
from core.ports import BackendOperations
from core.utils.dto_converters import (
    from_domain_model as _from_domain_model_fn,
)
from core.utils.dto_converters import (
    to_domain_model as _to_domain_model_fn,
)
from core.utils.dto_converters import (
    to_domain_models as _to_domain_models_fn,
)
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins


class ConversionHelpersMixin[B: BackendOperations, T: DomainModelProtocol]:
    """
    Mixin providing DTO conversion and result handling helpers.

    These methods handle the common patterns of:
    - Converting between backend data and domain models
    - Ensuring non-null results from optional returns
    - Validating required fields
    - Creating entities with automatic conversion

    Required attributes from composing class:
        backend: B - Backend implementation
        _model_class: type[T] - Domain model class
        _dto_class: type[DTOProtocol] - DTO class for conversion
    """

    # Type hints for attributes that must be provided by composing class
    backend: B
    _model_class: type[T] | None
    _dto_class: type[DTOProtocol] | None

    # ========================================================================
    # RESULT HELPERS - NULL SAFETY
    # ========================================================================

    def _ensure_exists(
        self,
        result: Result[T | None],
        resource_name: str,
        identifier: str,
    ) -> Result[T]:
        """
        Convert Result[T | None] to Result[T] with proper null safety.

        This helper solves the "Optional → Non-Optional" pattern where backend
        operations return Result[T | None] (resource might not exist) but service
        methods need to guarantee Result[T] (resource must exist).

        Architectural Pattern:
            Backend.get() → Result[T | None]  # Honest about nullability
                 ↓
            Service._ensure_exists() → Result[T]  # Validates and converts
                 ↓
            Service.method() → Result[T]  # Fulfills promise

        Args:
            result: Result that might contain None
            resource_name: Human-readable resource type (e.g., "MOC", "Task")
            identifier: Resource identifier for error message

        Returns:
            Result[T] - guaranteed non-null value or error

        Example:
            async def get_task(...) -> Result[Task]:
                ...
                raw_result = await self.backend.get(task_uid)
                return self._ensure_exists(raw_result, "Task", task_uid)
        """
        if result.is_error:
            return Result.fail(result)

        if result.value is None:
            return Result.fail(Errors.not_found(resource=resource_name, identifier=identifier))

        return Result.ok(result.value)

    # ========================================================================
    # DTO CONVERSION HELPERS - DRY PRINCIPLE
    # ========================================================================
    # Mixin interface methods that delegate to standalone conversion functions

    def _to_domain_model(self, data: Any, dto_class: type[DTOProtocol], model_class: type[T]) -> T:
        """Convert backend data to domain model through DTO layer."""
        return _to_domain_model_fn(data, dto_class, model_class)

    def _to_domain_models(
        self, data_list: builtins.list[Any], dto_class: type[DTOProtocol], model_class: type[T]
    ) -> builtins.list[T]:
        """Convert list of backend data to domain models."""
        return _to_domain_models_fn(data_list, dto_class, model_class)

    def _from_domain_model(self, model: T, dto_class: type) -> Any:
        """Convert domain model to DTO for backend operations."""
        return _from_domain_model_fn(model, dto_class)

    def _records_to_domain_models(
        self,
        records: builtins.list[dict[str, Any]],
        node_key: str = "n",
    ) -> builtins.list[T]:
        """
        Extract nodes from query records and convert to domain models.

        Phase 2 consolidation helper: handles the common pattern of extracting
        nodes from RETURN n queries and converting to domain models.

        Args:
            records: List of record dicts from execute_query
            node_key: Key containing the node data (default: "n")

        Returns:
            List of domain model instances
        """
        from core.utils.neo4j_mapper import from_neo4j_node

        return [from_neo4j_node(record[node_key], self._model_class) for record in records]

    # ========================================================================
    # CREATE OPERATION HELPERS (January 2026 - DRY Consolidation)
    # ========================================================================
    # Composable helper methods for the common create pattern:
    # 1. Validate user_uid
    # 2. Create DTO
    # 3. Call backend.create()
    # 4. Convert to domain model
    # 5. Publish event
    #
    # Subclasses compose these as needed, adding domain-specific logic between steps.

    def _validate_required_user_uid(
        self, user_uid: str | None, operation: str
    ) -> Result[Any] | None:
        """
        Validate that user_uid is present for an operation.

        Common pattern across all Activity domain create methods.

        Args:
            user_uid: The user UID to validate
            operation: Operation name for error message (e.g., "task creation")

        Returns:
            None if valid, Result.fail() if user_uid is missing.
            Returns Result[Any] to be compatible with any Result[T] return type.

        Example:
            validation = self._validate_required_user_uid(user_uid, "task creation")
            if validation:
                return validation
        """
        if not user_uid:
            return Result.fail(
                Errors.validation(
                    message=f"user_uid is required for {operation}",
                    field="user_uid",
                    value=user_uid,
                )
            )
        return None

    async def _create_and_convert(
        self,
        data: dict[str, Any],
        dto_class: type[DTOProtocol],
        model_class: type[T],
    ) -> Result[T]:
        """
        Create entity in backend and convert to domain model.

        Consolidates the common pattern:
        1. Call backend.create(data)
        2. Check for errors
        3. Convert result to domain model

        Args:
            data: Dictionary data to create (typically from dto.to_dict())
            dto_class: DTO class for conversion
            model_class: Domain model class for conversion

        Returns:
            Result containing created domain model

        Example:
            dto = TaskDTO(uid=..., title=..., ...)
            result = await self._create_and_convert(dto.to_dict(), TaskDTO, Task)
            if result.is_error:
                return result
            task = result.value
        """
        create_result = await self.backend.create(data)
        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        model = self._to_domain_model(create_result.value, dto_class, model_class)
        return Result.ok(model)


# ============================================================================
# PROTOCOL COMPLIANCE VERIFICATION (January 2026)
# ============================================================================
# This block ensures ConversionHelpersMixin stays in sync with the
# ConversionOperations protocol. Any signature mismatch will cause a
# type error during MyPy static analysis (zero runtime cost).
#
# To verify compliance:
#   poetry run mypy core/services/mixins/conversion_helpers_mixin.py
#
# See: /docs/investigations/PROTOCOL_MIXIN_ALIGNMENT_SOLUTIONS.md
# ============================================================================
if TYPE_CHECKING:
    from core.ports.base_service_interface import ConversionOperations

    # Structural subtyping check - verifies method signatures match
    # If this line fails type-checking, the mixin and protocol are out of sync
    _protocol_check: type[ConversionOperations[Any]] = ConversionHelpersMixin  # type: ignore[type-arg]
