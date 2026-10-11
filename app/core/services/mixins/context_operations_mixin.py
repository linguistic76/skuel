"""
Context Operations Mixin
========================

Provides content retrieval: an entity together with its full body.

REQUIRES (Mixin Dependencies):
    - CrudOperationsMixin: Uses get() method for entity retrieval

PROVIDES:
    - get_with_content: Get entity with full content loaded
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any

from core.models.protocols import DomainModelProtocol
from core.ports import BackendOperations
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result


class ContextOperationsMixin[B: BackendOperations, T: DomainModelProtocol]:
    """
    Mixin providing content retrieval.

    Required attributes from composing class:
        backend: B - Backend implementation
        config_lookup_label: str - LABEL_CONFIGS registry key (e.g., "Task", "PathStep")
        _content_field: str - Field containing content
        get: Method to get entity by UID
    """

    # Type hints for attributes that must be provided by composing class
    backend: B
    _content_field: str

    @property
    @abstractmethod
    def config_lookup_label(self) -> str:
        """LABEL_CONFIGS registry key (e.g., ``"Task"``, ``"PathStep"``) - provided by composing class."""
        ...

    @abstractmethod
    async def get(self, uid: str) -> Result[T]:
        """Get entity by UID - provided by CrudOperationsMixin."""
        ...

    # ========================================================================
    # CONTENT OPERATIONS (January 2026 - Unified)
    # ========================================================================

    @with_error_handling("get_with_content", error_type="database", uid_param="uid")
    async def get_with_content(self, uid: str) -> Result[tuple[T, str | None]]:
        """
        Get entity with full content loaded.

        For entities with separate content storage, this ensures full content
        is retrieved regardless of storage strategy.

        Args:
            uid: Entity UID

        Returns:
            Result[tuple[T, str | None]]: Entity and its content
        """
        if not uid:
            return Result.fail(Errors.validation(message="UID is required", field="uid"))

        entity_result = await self.get(uid)
        if entity_result.is_error:
            return Result.fail(entity_result)

        entity = entity_result.value
        if entity is None:
            return Result.fail(Errors.not_found(resource=self.config_lookup_label, identifier=uid))

        # Check if content is already populated in entity
        content: str | None = getattr(entity, self._content_field, None)

        # If no inline content, fetch from the :Content subtree. A read
        # failure propagates — silently degrading to (entity, None) would
        # render a body-less page and mask a real database error.
        if not content:
            content_method = getattr(self.backend, "get_content", None)
            if content_method:
                content_result = await content_method(uid)
                if content_result.is_error:
                    return Result.fail(content_result)
                content = content_result.value

        return Result.ok((entity, content))


# ============================================================================
# PROTOCOL COMPLIANCE VERIFICATION (January 2026)
# ============================================================================
if TYPE_CHECKING:
    from core.ports.base_service_interface import ContextOperations

    _protocol_check: type[ContextOperations[Any]] = ContextOperationsMixin  # type: ignore[type-abstract]
