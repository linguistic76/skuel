"""
User Progress Mixin
===================

Provides user progress and mastery tracking operations.

These methods track user progress on entities, originally for Curriculum
domains but now available to any domain via _supports_user_progress flag.

REQUIRES (Mixin Dependencies):
    - ConversionHelpersMixin: Uses _records_to_domain_models() for result conversion

PROVIDES (Methods for Progress Tracking):
    - get_user_progress: Get user's progress/mastery for an entity
    - update_user_mastery: Update user's mastery level
    - get_user_curriculum: Get entities the user is studying/has mastered

Methods:
    - get_user_progress: Get user's progress/mastery for an entity
    - update_user_mastery: Update user's mastery level
    - get_user_curriculum: Get entities the user is studying/has mastered
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from core.models.protocols import DomainModelProtocol
from core.models.type_hints import EntityUID, UserUID
from core.ports import BackendOperations
from core.ports.query_types import UserProgressResult
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    from logging import Logger


class UserProgressMixin[B: BackendOperations, T: DomainModelProtocol]:
    """
    Mixin providing user progress and mastery tracking.

    Originally for Curriculum domains, but now available to any domain
    via _supports_user_progress flag.

    Required attributes from composing class:
        backend: B - Backend implementation
        logger: Logger - For logging
        entity_label: str - Neo4j base-label for Cypher matching (e.g., "Entity", "Ku")
        config_lookup_label: str - LABEL_CONFIGS registry key (e.g., "Task", "PathStep"),
            used for domain-specific error messages and logs.
        _supports_user_progress: bool - Enable progress tracking
        _mastery_threshold: float - Threshold for mastery (0.0-1.0)
        _records_to_domain_models: Conversion method
    """

    # Type hints for attributes that must be provided by composing class
    backend: B
    logger: Logger
    _supports_user_progress: ClassVar[bool]
    _mastery_threshold: float

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
    def _records_to_domain_models(
        self, records: builtins.list[dict[str, Any]], node_key: str = "n"
    ) -> builtins.list[T]:
        """DTO conversion - provided by ConversionHelpersMixin."""
        ...

    # ========================================================================
    # USER PROGRESS / MASTERY OPERATIONS (January 2026 - Unified)
    # ========================================================================

    @with_error_handling("get_user_progress", error_type="database")
    async def get_user_progress(
        self, user_uid: UserUID, entity_uid: EntityUID
    ) -> Result[UserProgressResult]:
        """
        Get user's progress/mastery for an entity.

        Requires: _supports_user_progress = True

        Uses: build_user_progress_query from cypher module (consolidation)

        Args:
            user_uid: User UID
            entity_uid: Entity UID

        Returns:
            Result[dict]: Progress data including mastery_level, is_mastered, etc.
        """
        if not self._supports_user_progress:
            return Result.fail(
                Errors.business(
                    rule="user_progress_not_supported",
                    message=f"{self.config_lookup_label} domain does not support user progress tracking",
                )
            )

        if not user_uid or not entity_uid:
            return Result.fail(
                Errors.validation(
                    message="user_uid and entity_uid are required",
                    field="user_uid,entity_uid",
                )
            )

        result = await self.backend.user_progress_raw(
            user_uid=user_uid,
            entity_uid=entity_uid,
            mastery_threshold=self._mastery_threshold,
        )

        if result.is_error:
            return Result.fail(result)

        records = result.value
        if not records:
            return Result.ok(
                {
                    "mastery_level": 0.0,
                    "is_mastered": False,
                    "last_accessed": None,
                    "time_spent": 0,
                    "attempts": 0,
                    "relationship_type": None,
                    "started_at": None,
                    "completed_at": None,
                }
            )

        return Result.ok(records[0].get("progress", {}))

    @with_error_handling("update_user_mastery", error_type="database")
    async def update_user_mastery(
        self,
        user_uid: UserUID,
        entity_uid: EntityUID,
        mastery_level: float,
    ) -> Result[bool]:
        """
        Update user's mastery level for an entity.

        Requires: _supports_user_progress = True

        Args:
            user_uid: User UID
            entity_uid: Entity UID
            mastery_level: New mastery level (0.0-1.0)

        Returns:
            Result[bool]: True if updated successfully
        """
        if not self._supports_user_progress:
            return Result.fail(
                Errors.business(
                    rule="user_progress_not_supported",
                    message=f"{self.config_lookup_label} domain does not support user progress tracking",
                )
            )

        if not user_uid or not entity_uid:
            return Result.fail(
                Errors.validation(
                    message="user_uid and entity_uid are required",
                    field="user_uid,entity_uid",
                )
            )

        if mastery_level < 0.0 or mastery_level > 1.0:
            return Result.fail(
                Errors.validation(
                    message="Mastery level must be between 0.0 and 1.0",
                    field="mastery_level",
                )
            )

        # Determine relationship type based on mastery level
        rel_type = "MASTERED" if mastery_level >= self._mastery_threshold else "STUDYING"

        result = await self.backend.update_user_mastery_rel(
            user_uid=user_uid,
            entity_uid=entity_uid,
            mastery_level=mastery_level,
            rel_type=rel_type,
        )

        if result.is_error:
            return Result.fail(result)

        self.logger.info(f"Updated mastery for {user_uid} on {entity_uid}: {mastery_level:.2f}")
        return Result.ok(True)

    @with_error_handling("get_user_curriculum", error_type="database")
    async def get_user_curriculum(
        self,
        user_uid: UserUID,
        include_completed: bool = False,
    ) -> Result[builtins.list[T]]:
        """
        Get entities the user is studying/has mastered.

        Requires: _supports_user_progress = True

        Uses: build_user_curriculum_query from cypher module (consolidation)

        Args:
            user_uid: User UID
            include_completed: Include completed/mastered entities

        Returns:
            Result[list[T]]: User's entities
        """
        if not self._supports_user_progress:
            return Result.fail(
                Errors.business(
                    rule="user_progress_not_supported",
                    message=f"{self.config_lookup_label} domain does not support user progress tracking",
                )
            )

        if not user_uid:
            return Result.fail(Errors.validation(message="user_uid is required", field="user_uid"))

        result = await self.backend.user_curriculum_raw(
            user_uid=user_uid,
            include_completed=include_completed,
        )
        if result.is_error:
            return Result.fail(result)

        entities = self._records_to_domain_models(result.value)
        self.logger.debug(
            f"Found {len(entities)} {self.config_lookup_label} entities for user {user_uid}"
        )
        return Result.ok(entities)


# ============================================================================
# PROTOCOL COMPLIANCE VERIFICATION (January 2026)
# ============================================================================
if TYPE_CHECKING:
    from core.ports.base_service_interface import UserProgressOperations

    _protocol_check: type[UserProgressOperations[Any]] = UserProgressMixin  # type: ignore[type-arg, type-abstract]
