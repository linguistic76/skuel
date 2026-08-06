"""
Conversion Helpers Mixin
========================

Provides DTO/domain model conversion and result handling helpers.

These are foundational methods used by other mixins and service methods
for converting between backend data and domain models.

REQUIRES (Mixin Dependencies):
    - None - This is a foundational mixin with no dependencies

PROVIDES (Methods for Other Mixins):
    - _to_domain_model: Convert backend data to domain model
    - _to_domain_models: Bulk convert backend data to domain models
    - _validate_required_user_uid: Validate presence of user_uid

Methods:
    - _to_domain_model: Convert backend data to domain model
    - _to_domain_models: Bulk convert backend data to domain models
    - _validate_required_user_uid: Validate presence of user_uid
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.protocols import DomainModelProtocol, DTOProtocol
from core.models.type_hints import UserUID
from core.ports import BackendOperations
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

    def _validate_required_user_uid(self, user_uid: UserUID | None, operation: str) -> Result[None]:
        """
        Validate that user_uid is present for an operation.

        Common pattern across all Activity domain create methods.

        Args:
            user_uid: The user UID to validate
            operation: Operation name for error message (e.g., "task creation")

        Returns:
            Result.ok(None) if valid, Result.fail() if user_uid is missing.

        Example:
            validation = self._validate_required_user_uid(user_uid, "task creation")
            if validation.is_error:
                return Result.fail(validation)
        """
        if not user_uid:
            return Result.fail(
                Errors.validation(
                    message=f"user_uid is required for {operation}",
                    field="user_uid",
                    value=user_uid,
                )
            )
        return Result.ok(None)

    # _create_and_convert is DELETED (August 2026). It persisted a DTO property dict and
    # re-converted the backend's return value, and its last caller was
    # TasksCoreService.create_task — the sixth and final Activity Domain create path to
    # route through the shared, event-publishing ``create()`` primitive instead. Reaching
    # backend.create by that side road is exactly what let a create door skip
    # _validate_create and publish nothing; there is no caller left and no shape that
    # wants one. Persist the ENTITY via CrudOperationsMixin.create.


# ============================================================================
# PROTOCOL COMPLIANCE VERIFICATION (January 2026)
# ============================================================================
# This block ensures ConversionHelpersMixin stays in sync with the
# ConversionOperations protocol. Any signature mismatch will cause a
# type error during MyPy static analysis (zero runtime cost).
#
# To verify compliance:
# uv run mypy core/services/mixins/conversion_helpers_mixin.py
#
# See: /docs/investigations/PROTOCOL_MIXIN_ALIGNMENT_SOLUTIONS.md
# ============================================================================
if TYPE_CHECKING:
    from core.ports.base_service_interface import ConversionOperations

    # Structural subtyping check - verifies method signatures match
    # If this line fails type-checking, the mixin and protocol are out of sync
    _protocol_check: type[ConversionOperations[Any]] = ConversionHelpersMixin
