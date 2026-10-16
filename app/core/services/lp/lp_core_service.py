"""
Learning Path Core Service
===========================

Core reads for learning paths.

This sub-service handles:
- Path retrieval (single and batch)
- Path listing (by user, all paths)
- A path's steps and the learner's current step

A learning path is authored only in the content vault (ADR-091); nothing here
creates, updates or deletes one.

Part of LpService decomposition (October 24, 2025)
- Follows PsService decomposition pattern
- Clear separation of concerns
- Single responsibility: learning path reads

**Architecture (January 2026 Unified):**
- Extends BaseService[LpOperations, Lp] for unified infrastructure
- All Cypher queries delegated to LpBackend methods (typed via LpOperations)
- Class attributes match unified domain conventions
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.pathways.learning_path import LearningPath
from core.models.pathways.learning_path_dto import LearningPathDTO
from core.models.pathways.path_step import PathStep
from core.models.type_hints import UserUID
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import LpOperations

logger = get_logger(__name__)


class LpCoreService(BaseService["LpOperations", LearningPath]):
    """
    Core reads for learning paths.

    **Architecture (January 2026 Unified):**
    Extends BaseService[LpOperations, LearningPath] for unified infrastructure.
    All Cypher queries delegated to typed LpBackend methods (via LpOperations).

    This service owns path retrieval (single, batch, by user) and step reads.
    """

    # =========================================================================
    # DomainConfig consolidation (January 2026)
    # =========================================================================
    # All configuration in one place, using centralized relationship registry
    # See: /docs/migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md
    _config = create_curriculum_domain_config(
        dto_class=LearningPathDTO,
        model_class=LearningPath,
        entity_label="Entity",
        domain_name="lp",
        search_fields=("title", "description"),  # LP: name→title, goal→description
        search_order_by="updated_at",
        content_field="description",  # LP goal mapped to Entity description
    )

    def __init__(self, backend: LpOperations) -> None:
        """
        Initialize core path service.

        FAIL-FAST ARCHITECTURE (per CLAUDE.md):
        The backend is REQUIRED. Services run at full capacity or fail immediately.

        Args:
            backend: LpOperations backend for graph operations (REQUIRED)
        """
        super().__init__(backend, "lp_core")

    @with_error_handling("get_learning_path", error_type="database", uid_param="path_uid")
    async def get_learning_path(self, path_uid: str) -> Result[LearningPath | None]:
        """Get a single learning path by UID (returns None if not found)."""
        query_result = await self.backend.get_path_with_steps(path_uid)

        if query_result.is_error:
            return Result.fail(query_result)

        return Result.ok(query_result.value)

    @with_error_handling("list_user_paths", error_type="database", uid_param="user_uid")
    async def list_user_paths(
        self, user_uid: UserUID, limit: int | None = None
    ) -> Result[list[LearningPath]]:
        """List all learning paths for a specific user."""
        query_result = await self.backend.list_user_paths_with_steps(user_uid, limit)

        if query_result.is_error:
            return Result.fail(query_result)

        return Result.ok(query_result.value)

    @with_error_handling("list_all_paths", error_type="database")
    async def list_all_paths(
        self,
        limit: int | None = None,
        offset: int = 0,
    ) -> Result[list[LearningPath]]:
        """
        List all learning paths in the system, uid-ordered, with pagination.

        Args:
            limit: Maximum number of paths to return
            offset: Number of paths to skip (for pagination)
        """
        query_result = await self.backend.list_all_paths_with_steps(limit=limit, offset=offset)

        if query_result.is_error:
            return Result.fail(query_result)

        return Result.ok(query_result.value or [])

    async def get_path_steps(self, path_uid: str) -> Result[list[PathStep]]:
        """Get the ordered steps for a learning path."""
        path_result = await self.get_learning_path(path_uid)
        if path_result.is_error:
            return Result.fail(path_result)

        if not path_result.value:
            return Result.fail(Errors.not_found(resource="learning_path", identifier=path_uid))

        path = path_result.value
        steps = path.metadata.get("steps", []) if path.metadata else []
        return Result.ok(list(steps))

    async def get_current_step(self, path_uid: str) -> Result[PathStep | None]:
        """
        Get the current (first incomplete) step in a learning path.

        Returns the first step that is not yet completed, or None if all steps
        are completed or path has no steps.

        Args:
            path_uid: Learning path UID

        Returns:
            Result containing the current step, or None if all steps completed
        """
        steps_result = await self.get_path_steps(path_uid)
        if steps_result.is_error:
            return Result.fail(steps_result)

        steps = steps_result.value
        if not steps:
            return Result.ok(None)

        # Find first incomplete step (Entity uses is_completed property)
        for step in steps:
            if not step.is_completed:
                return Result.ok(step)

        # All steps completed - return None
        return Result.ok(None)

    # ============================================================================
    # STEP MANAGEMENT
    # ============================================================================

    # ============================================================================
    # PRIVATE HELPERS
    # ============================================================================
