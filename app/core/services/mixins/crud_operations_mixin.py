"""
CRUD Operations Mixin
=====================

Provides core CRUD operations and ownership-verified CRUD for multi-tenant security.

REQUIRES (Mixin Dependencies):
    - None - Foundational CRUD with no dependencies on other mixins

PROVIDES (Methods for All Service Layers):
    Core CRUD:
        - create: Create a new entity
        - get: Get entity by UID
        - update: Update entity (accepts BaseUpdatePayload or dict[str, Any])
        - delete: Delete entity
        - list: List entities with pagination

    Ownership-Verified CRUD (multi-tenant security):
        - verify_ownership: Verify entity belongs to user
        - get_for_user: Get entity only if owned by user
        - update_for_user: Update entity only if owned by user
        - delete_for_user: Delete entity only if owned by user

Methods:
    Core CRUD:
        - create: Create a new entity
        - get: Get entity by UID
        - update: Update entity (accepts BaseUpdatePayload or dict[str, Any])
        - delete: Delete entity
        - list: List entities with pagination

    Ownership-Verified CRUD (multi-tenant security):
        - verify_ownership: Verify entity belongs to user
        - get_for_user: Get entity only if owned by user
        - update_for_user: Update entity only if owned by user
        - delete_for_user: Delete entity only if owned by user

Type Safety (January 2026)
--------------------------
Update methods accept BaseUpdatePayload or domain-specific TypedDicts for type safety.
TypedDicts are structural subtypes of dict[str, Any], so this is backward compatible.

    from core.ports import TaskUpdatePayload

    updates: TaskUpdatePayload = {"status": "completed", "progress": 1.0}
    await service.update(uid, updates)  # IDE autocomplete works!
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.protocols import DomainModelProtocol
from core.ports import BackendOperations
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins


class CrudOperationsMixin[B: BackendOperations, T: DomainModelProtocol]:
    """
    Mixin providing core CRUD operations and ownership-verified CRUD.

    The ownership-verified methods provide multi-tenant security by verifying
    that the requesting user owns the entity before allowing access.

    Design principle: Return "not found" for entities the user doesn't own.
    This prevents information leakage (attacker can't tell if UID exists).

    Required attributes from composing class:
        backend: B - Backend implementation
        _validate_create: Validation hook for create operations
        _validate_update: Validation hook for update operations
    """

    # Type hints for attributes that must be provided by composing class
    backend: B

    def _validate_create(self, entity: T) -> Result[None] | None:
        """Validation hook - override in subclass."""
        return None

    def _validate_update(self, current: T, updates: dict[str, Any]) -> Result[None] | None:
        """
        Validation hook - override in subclass.

        Note: Uses dict[str, Any] because domain-specific validation needs
        to access domain-specific keys (priority, amount, label, etc.)
        """
        return None

    # ========================================================================
    # CORE CRUD OPERATIONS
    # ========================================================================

    async def create(self, entity: T) -> Result[T]:
        """Create a new entity."""
        # Call domain-specific validation hook
        validation = self._validate_create(entity)
        if validation:
            # Validation failed: Result[None] → Result[T] with same error
            return Result.fail(validation.expect_error())

        return await self.backend.create(entity)

    async def get(self, uid: str) -> Result[T]:
        """
        Get entity by UID.

        Returns Result[T] - not found is an error, not a None value.
        This design ensures callers don't need None checks after successful Results.
        """
        if not uid:
            return Result.fail(Errors.validation(message="UID is required", field="uid"))

        result = await self.backend.get(uid)

        # Convert None → NotFound error (backend returns Result.ok(None) when not found)
        if result.is_ok and result.value is None:
            return Result.fail(Errors.not_found(f"Entity {uid} not found"))

        # At this point, result is either an error or has a non-None value
        return result  # type: ignore[return-value]

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[T]:
        """
        Update entity.

        Callers can use TypedDicts (e.g., TaskUpdatePayload) for IDE autocomplete -
        they're structural subtypes of dict[str, Any].

        Args:
            uid: Entity UID to update
            updates: Dictionary of fields to update

        Returns:
            Result[T]: Updated entity or error

        Type Hint Example:
            from core.ports import TaskUpdatePayload
            updates: TaskUpdatePayload = {"status": "completed", "progress": 1.0}
            await service.update(uid, updates)  # IDE autocomplete works!
        """
        if not uid:
            return Result.fail(Errors.validation(message="UID is required", field="uid"))

        # Get current entity and validate update
        current_result = await self.get(uid)
        if current_result.is_error:
            return Result.fail(current_result.expect_error())

        # Call domain-specific validation hook
        validation = self._validate_update(current_result.value, updates)
        if validation:
            # Validation failed: Result[None] → Result[T] with same error
            return Result.fail(validation.expect_error())

        return await self.backend.update(uid, updates)

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """Delete entity."""
        if not uid:
            return Result.fail(Errors.validation(message="UID is required", field="uid"))

        # Check existence first
        exists_result = await self.get(uid)
        if exists_result.is_error:
            return Result.fail(exists_result.expect_error())

        return await self.backend.delete(uid, cascade=cascade)

    # ========================================================================
    # OWNERSHIP-VERIFIED CRUD OPERATIONS (December 2025)
    # ========================================================================
    #
    # These methods provide multi-tenant security by verifying that the
    # requesting user owns the entity before allowing access.
    #
    # Design principle: Return "not found" for entities the user doesn't own.
    # This prevents information leakage (attacker can't tell if UID exists).
    # ========================================================================

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[T]:
        """
        Verify that an entity exists AND belongs to the specified user.

        Returns the entity if owned by user, otherwise returns NotFound error.
        This prevents IDOR (Insecure Direct Object Reference) attacks.

        Args:
            uid: Entity UID to verify
            user_uid: User UID who should own the entity

        Returns:
            Result[T]: The entity if owned by user, NotFound error otherwise

        Security Note:
            Returns "not found" (not "access denied") to prevent information
            leakage about whether a UID exists.
        """
        if not uid:
            return Result.fail(Errors.validation(message="UID is required", field="uid"))
        if not user_uid:
            return Result.fail(Errors.validation(message="user_uid is required", field="user_uid"))

        # Get the entity
        result = await self.get(uid)
        if result.is_error:
            return result

        entity = result.value

        # Check ownership - entity must have user_uid attribute
        entity_user_uid = getattr(entity, "user_uid", None)
        if entity_user_uid is None:
            # Entity type doesn't support ownership (e.g., KU, LP)
            # This is a programming error, not a user error
            return Result.fail(
                Errors.system(
                    message=f"Entity type {type(entity).__name__} does not support ownership verification",
                    operation="verify_ownership",
                )
            )

        if entity_user_uid != user_uid:
            # User doesn't own this entity - return "not found" to prevent info leakage
            return Result.fail(Errors.not_found(f"Entity {uid} not found"))

        return Result.ok(entity)

    async def get_for_user(self, uid: str, user_uid: str) -> Result[T]:
        """
        Get entity by UID, but only if owned by the specified user.

        This is the secure alternative to get() for multi-tenant applications.

        Args:
            uid: Entity UID to retrieve
            user_uid: User UID who should own the entity

        Returns:
            Result[T]: The entity if owned by user, NotFound error otherwise

        Example:
            # In route handler:
            user_uid = require_authenticated_user(request)
            result = await service.get_for_user(uid, user_uid)
            if result.is_error:
                return result  # Returns 404, not 403
        """
        return await self.verify_ownership(uid, user_uid)

    async def update_for_user(self, uid: str, updates: dict[str, Any], user_uid: str) -> Result[T]:
        """
        Update entity, but only if owned by the specified user.

        This is the secure alternative to update() for multi-tenant applications.

        Args:
            uid: Entity UID to update
            updates: Dictionary of fields to update
            user_uid: User UID who should own the entity

        Returns:
            Result[T]: The updated entity if owned by user, error otherwise

        Example:
            from core.ports import TaskUpdatePayload

            user_uid = require_authenticated_user(request)
            updates: TaskUpdatePayload = {"status": "completed", "progress": 1.0}
            result = await service.update_for_user(uid, updates, user_uid)
        """
        # First verify ownership
        ownership_result = await self.verify_ownership(uid, user_uid)
        if ownership_result.is_error:
            return ownership_result

        # Call domain-specific validation hook
        validation = self._validate_update(ownership_result.value, updates)
        if validation:
            return Result.fail(validation.expect_error())

        # Perform the update
        return await self.backend.update(uid, updates)

    async def delete_for_user(self, uid: str, user_uid: str, cascade: bool = False) -> Result[bool]:
        """
        Delete entity, but only if owned by the specified user.

        This is the secure alternative to delete() for multi-tenant applications.

        Args:
            uid: Entity UID to delete
            user_uid: User UID who should own the entity
            cascade: Whether to cascade delete relationships

        Returns:
            Result[bool]: True if deleted, error otherwise

        Example:
            user_uid = require_authenticated_user(request)
            result = await service.delete_for_user(uid, user_uid)
        """
        # First verify ownership
        ownership_result = await self.verify_ownership(uid, user_uid)
        if ownership_result.is_error:
            # Convert Result[T] error to Result[bool] error
            return Result.fail(ownership_result.expect_error())

        # Perform the delete
        return await self.backend.delete(uid, cascade=cascade)

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
    ) -> Result[tuple[builtins.list[T], int]]:
        """
        List entities with pagination, filtering, and optional user filtering.

        When user_uid is provided, uses graph relationship filtering via
        backend.get_user_entities() to find entities owned by the user.

        Args:
            limit: Maximum number of results
            offset: Pagination offset
            filters: Additional filters (dict)
            sort_by: Field to sort by
            sort_order: Sort order ('asc' or 'desc')
            user_uid: Optional user UID for user-specific filtering
            order_by: Alias for sort_by
            order_desc: Alias for desc sort order

        Returns:
            Result[tuple[list[T], int]]: Tuple of (entities, total_count) for pagination
        """
        # Validate pagination
        if limit < 1 or limit > 1000:
            return Result.fail(
                Errors.validation(message="Limit must be between 1 and 1000", field="limit")
            )

        if offset < 0:
            return Result.fail(
                Errors.validation(message="Offset cannot be negative", field="offset")
            )

        # Handle aliases for CRUDRouteFactory compatibility
        if order_by:
            sort_by = order_by
        if order_desc:
            sort_order = "desc"

        # If user_uid provided, use graph relationship filtering
        if user_uid:
            return await self.backend.get_user_entities(
                user_uid=user_uid,
                filters=filters or {},
                limit=limit,
                offset=offset,
                sort_by=sort_by or "created_at",
                sort_order=sort_order,
            )

        # Standard list without user filtering
        return await self.backend.list(
            limit=limit,
            offset=offset,
            filters=filters or {},
            sort_by=sort_by,
            sort_order=sort_order,
        )


# ============================================================================
# PROTOCOL COMPLIANCE VERIFICATION (January 2026)
# ============================================================================
if TYPE_CHECKING:
    from core.ports.base_service_interface import CrudOperations

    _protocol_check: type[CrudOperations[Any]] = CrudOperationsMixin  # type: ignore[type-arg]
