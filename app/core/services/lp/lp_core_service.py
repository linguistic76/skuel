"""
Learning Path Core Service
===========================

Core CRUD operations for learning paths.

This sub-service handles:
- Path creation and persistence
- Path retrieval (single and batch)
- Path listing (by user, all paths)
- Path updates and deletion
- Path-to-steps relationship management

Part of LpService decomposition (October 24, 2025)
- Follows PsService decomposition pattern
- Clear separation of concerns
- Single responsibility: CRUD operations

**Architecture (January 2026 Unified):**
- Extends BaseService[BackendOperations[Lp], Lp] for unified infrastructure
- All Cypher queries delegated to LpBackend methods
- Class attributes match unified domain conventions
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.constants import MasteryLevel
from core.events import publish_event
from core.models.enums import Domain
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.learning_path_dto import LearningPathDTO
from core.models.pathways.path_step import PathStep
from core.models.type_hints import EntityUID, UserUID
from core.ports import HasUID, get_enum_value
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import BackendOperations

logger = get_logger(__name__)


class LpCoreService(BaseService["BackendOperations[LearningPath]", LearningPath]):
    """
    Core CRUD operations for learning paths.

    **Architecture (January 2026 Unified):**
    Extends BaseService[BackendOperations[Lp], Lp] for unified infrastructure.
    All Cypher queries delegated to typed LpBackend methods.

    This service owns:
    - Path creation and persistence to Neo4j
    - Path retrieval (single, batch, by user)
    - Path updates (name, goal, domain, hours)
    - Path deletion (cascade deletes steps)
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

    def __init__(
        self,
        backend: BackendOperations[LearningPath],
        ps_service: Any = None,
        event_bus: Any = None,
    ) -> None:
        """
        Initialize core path service.

        FAIL-FAST ARCHITECTURE (per CLAUDE.md):
        The backend is REQUIRED. Services run at full capacity or fail immediately.

        Args:
            backend: BackendOperations[Lp] for graph operations (REQUIRED)
            ps_service: PsService for step operations (optional for get_path_steps)
            event_bus: Event bus for domain events (optional)
        """
        super().__init__(backend, "lp_core")
        self.ps_service = ps_service
        self.event_bus = event_bus

    @staticmethod
    def _with_steps(path: LearningPath, steps: list[PathStep]) -> LearningPath:
        """Store a step list in ``path.metadata["steps"]`` (the composed shape
        this service returns; persisted reads get the same shape from the backend)."""
        metadata = path.metadata if path.metadata else {}
        metadata["steps"] = steps
        object.__setattr__(path, "metadata", metadata)
        return path

    @with_error_handling(
        "create_path_from_knowledge_units", error_type="database", uid_param="user_uid"
    )
    async def create_path_from_knowledge_units(
        self,
        user_uid: UserUID,
        knowledge_units: list[Any],
        title: str | None = None,
        description: str | None = None,
    ) -> Result[LearningPath]:
        """Create a learning path from a list of knowledge units."""
        path_uid = EntityUID(f"path_{user_uid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

        steps = []
        total_estimated_hours = 0

        for i, unit in enumerate(knowledge_units):
            step_uid = EntityUID(f"{path_uid}_step_{i + 1}")
            estimated_hours = 2

            step = PathStep(
                uid=step_uid,
                title=f"Step {i + 1}",
                intent="Complete this path step",
                knowledge_uids=tuple([unit.uid if isinstance(unit, HasUID) else str(unit)]),
                sequence=i,
                estimated_hours=estimated_hours,
                mastery_threshold=MasteryLevel.PROFICIENT,
            )
            steps.append(step)
            total_estimated_hours += estimated_hours

        path = LearningPath(
            uid=path_uid,
            title=title or f"Learning Path for {user_uid}",
            description=description or "Complete knowledge units in sequence",
            domain=Domain.LEARNING,
            estimated_hours=total_estimated_hours,
        )

        if self.backend:
            persist_result = await self._persist_path(path, steps, user_uid)
            if persist_result.is_error:
                logger.warning(f"Failed to persist path: {persist_result.error}")

        # Store steps in metadata for return value
        path_with_steps = self._with_steps(path, steps)

        logger.info(f"✅ Created learning path {path_uid} with {len(steps)} steps")
        return Result.ok(path_with_steps)

    @with_error_handling("create_path", error_type="database", uid_param="user_uid")
    async def create_path(
        self,
        user_uid: UserUID,
        title: str,
        description: str,
        steps: list[PathStep],
        domain: Domain = Domain.LEARNING,
    ) -> Result[LearningPath]:
        """
        Create and persist a learning path.

        This is THE method for creating paths programmatically.
        """
        path_uid = EntityUID(f"path_{user_uid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

        path = LearningPath(
            uid=path_uid,
            title=title,
            description=description,
            domain=domain,
            estimated_hours=sum(s.estimated_hours for s in steps if s.estimated_hours),
        )

        if self.backend:
            persist_result = await self._persist_path(path, steps, user_uid)
            if persist_result.is_error:
                return Result.fail(persist_result)

        # Publish LearningPathStarted event
        from core.events import LearningPathStarted

        event = LearningPathStarted(
            path_uid=path_uid,
            user_uid=user_uid,
            path_title=title,
            estimated_duration_hours=int(path.estimated_hours) if path.estimated_hours else None,
            total_kus=len(steps),
        )
        await publish_event(self.event_bus, event, self.logger)

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        from core.events.embedding_publisher import publish_embedding_requested
        from core.models.enums.entity_enums import EntityType

        await publish_embedding_requested(
            self.event_bus, EntityType.LEARNING_PATH, path, self.logger
        )

        logger.info(f"✅ Created path {path_uid}: {title}")
        return Result.ok(path)

    @with_error_handling("get_learning_paths_batch", error_type="database")
    async def get_learning_paths_batch(self, uids: list[str]) -> Result[list[LearningPath | None]]:
        """
        Get multiple learning paths in one batched query.

        Critical for GraphQL DataLoader batching to prevent N+1 queries.
        """
        if not uids:
            return Result.ok([])

        query_result = await self.backend.get_paths_batch_with_steps(uids)  # type: ignore[attr-defined]

        if query_result.is_error:
            return Result.fail(query_result)

        paths_map: dict[str, LearningPath] = {path.uid: path for path in query_result.value}

        # Return in same order as input UIDs
        result_list = [paths_map.get(uid) for uid in uids]
        return Result.ok(result_list)

    @with_error_handling("get_learning_path", error_type="database", uid_param="path_uid")
    async def get_learning_path(self, path_uid: str) -> Result[LearningPath | None]:
        """Get a single learning path by UID (returns None if not found)."""
        query_result = await self.backend.get_path_with_steps(path_uid)  # type: ignore[attr-defined]

        if query_result.is_error:
            return Result.fail(query_result)

        return Result.ok(query_result.value)

    @with_error_handling("list_user_paths", error_type="database", uid_param="user_uid")
    async def list_user_paths(
        self, user_uid: UserUID, limit: int | None = None
    ) -> Result[list[LearningPath]]:
        """List all learning paths for a specific user."""
        query_result = await self.backend.list_user_paths_with_steps(user_uid, limit)  # type: ignore[attr-defined]

        if query_result.is_error:
            return Result.fail(query_result)

        return Result.ok(query_result.value)

    @with_error_handling("list_all_paths", error_type="database")
    async def list_all_paths(
        self,
        limit: int | None = None,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[list[LearningPath]]:
        """
        List all learning paths in the system with pagination and sorting.

        Args:
            limit: Maximum number of paths to return
            offset: Number of paths to skip (for pagination)
            order_by: Field to sort by (e.g., 'uid', 'created_at', 'title')
            order_desc: Sort in descending order if True
        """
        query_result = await self.backend.list_all_paths_with_steps(  # type: ignore[attr-defined]
            limit=limit, offset=offset, order_by=order_by, order_desc=order_desc
        )

        if query_result.is_error:
            return Result.fail(query_result)

        return Result.ok(query_result.value or [])

    async def get_path_steps(self, path_uid: str) -> Result[list[PathStep]]:
        """
        Get steps for a learning path.

        Used by GraphQL types to resolve nested steps field.
        """
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

    @with_error_handling("update_path", error_type="database", uid_param="path_uid")
    async def update_path(self, path_uid: str, updates: dict[str, Any]) -> Result[LearningPath]:
        """
        Update an existing learning path.

        Supports updating: title, description, domain, estimated_hours, etc.
        """
        # First verify path exists
        get_result = await self.get_learning_path(path_uid)
        if get_result.is_error:
            return Result.fail(get_result)

        if not get_result.value:
            return Result.fail(Errors.not_found(resource="learning_path", identifier=path_uid))

        # Build SET clause dynamically
        set_clauses = []
        params: dict[str, Any] = {"uid": path_uid}

        allowed_fields = {
            "title",
            "description",
            "domain",
            "estimated_hours",
            "path_type",
            "step_difficulty",
            "outcomes",
            "checkpoint_week_intervals",
        }
        for key, value in updates.items():
            if key in allowed_fields:
                set_clauses.append(f"p.{key} = ${key}")
                if key in ("domain", "path_type", "step_difficulty"):
                    params[key] = get_enum_value(value)
                elif key in ("outcomes", "checkpoint_week_intervals"):
                    params[key] = list(value) if value else []
                else:
                    params[key] = value

        if not set_clauses:
            return Result.fail(
                Errors.validation(message="No valid fields to update", field="updates")
            )

        set_clauses.append("p.updated_at = $updated_at")
        params["updated_at"] = datetime.now().isoformat()

        query_result = await self.backend.update_path_properties(set_clauses, params)  # type: ignore[attr-defined]

        if query_result.is_error:
            return Result.fail(query_result)

        updated_path = query_result.value
        if updated_path is None:
            return Result.fail(
                Errors.database(
                    operation="update_path", message=f"Failed to update path {path_uid}"
                )
            )

        # Post-persist embedding refresh (ADR-074) — only when a text field changed
        from core.events.embedding_publisher import publish_embedding_requested
        from core.models.enums.entity_enums import EntityType

        await publish_embedding_requested(
            self.event_bus,
            EntityType.LEARNING_PATH,
            updated_path,
            self.logger,
            changed_fields=updates.keys(),
        )

        logger.info(f"✅ Updated learning path {path_uid}")
        return Result.ok(updated_path)

    @with_error_handling("delete_path", error_type="database", uid_param="path_uid")
    async def delete_path(self, path_uid: str) -> Result[bool]:
        """
        Delete a learning path and its associated steps.

        Cascade deletes step Entity nodes to prevent orphaned data.
        """
        # First verify path exists
        get_result = await self.get_learning_path(path_uid)
        if get_result.is_error:
            return Result.fail(get_result)

        if not get_result.value:
            return Result.fail(Errors.not_found(resource="learning_path", identifier=path_uid))

        query_result = await self.backend.delete_path_cascade(path_uid)  # type: ignore[attr-defined]

        if query_result.is_error:
            return Result.fail(query_result)

        deleted_count = query_result.value[0]["deleted_count"] if query_result.value else 0

        if deleted_count == 0:
            return Result.fail(
                Errors.database(
                    operation="delete_path", message=f"Failed to delete path {path_uid}"
                )
            )

        logger.info(f"✅ Deleted learning path {path_uid}")
        return Result.ok(True)

    # ============================================================================
    # STEP MANAGEMENT (2026-01-30 - Universal Hierarchical Pattern)
    # Delegated to LpBackend (2026-03-24)
    # ============================================================================

    @with_error_handling("get_steps", error_type="database", uid_param="path_uid")
    async def get_steps(self, path_uid: str, depth: int = 1) -> Result[list[PathStep]]:
        """Get all steps in a learning path ordered by sequence."""
        result = await self.backend.get_steps_raw(path_uid, depth)  # type: ignore[attr-defined]
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value)

    @with_error_handling("get_parent_path", error_type="database", uid_param="step_uid")
    async def get_parent_path(self, step_uid: str) -> Result[LearningPath | None]:
        """Get the learning path containing this step (first match)."""
        result = await self.backend.get_parent_path_raw(step_uid)  # type: ignore[attr-defined]
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value)

    @with_error_handling("add_step_to_path", error_type="database")
    async def add_step_to_path(
        self, path_uid: str, step_uid: str, sequence: int, order: int = 0
    ) -> Result[bool]:
        """Add a path step to a path with sequence ordering."""
        # Validate path exists
        path_result = await self.backend.get(path_uid)
        if path_result.is_error:
            return Result.fail(Errors.not_found(f"Learning path not found: {path_uid}"))

        # Validate step exists
        step_check = await self.backend.entity_exists(step_uid)  # type: ignore[attr-defined]
        if step_check.is_error:
            return Result.fail(step_check)
        if not step_check.value:
            return Result.fail(Errors.not_found(f"Path step not found: {step_uid}"))

        return await self.backend.add_step_to_path(path_uid, step_uid, sequence, order)  # type: ignore[attr-defined]

    @with_error_handling("remove_step_from_path", error_type="database")
    async def remove_step_from_path(self, path_uid: str, step_uid: str) -> Result[bool]:
        """Remove a step from a path and reorder remaining steps."""
        return await self.backend.remove_step_from_path(path_uid, step_uid)  # type: ignore[attr-defined]

    @with_error_handling("reorder_steps", error_type="database")
    async def reorder_steps(self, path_uid: str, step_uids: list[str]) -> Result[bool]:
        """Batch reorder all steps in a learning path."""
        return await self.backend.reorder_steps(path_uid, step_uids)  # type: ignore[attr-defined]

    # ============================================================================
    # PRIVATE HELPERS
    # ============================================================================

    @with_error_handling("_persist_path", error_type="database", uid_param="user_uid")
    async def _persist_path(
        self, path: LearningPath, steps: list[PathStep], user_uid: UserUID
    ) -> Result[bool]:
        """Persist a learning path to Neo4j graph."""
        path_params = {
            "uid": path.uid,
            "title": path.title,
            "description": path.description,
            "domain": get_enum_value(path.domain),
            "path_type": get_enum_value(path.path_type),
            "step_difficulty": get_enum_value(getattr(path, "step_difficulty", None)),
            "created_by": path.created_by,
            "estimated_hours": path.estimated_hours,
            "outcomes": list(path.outcomes),
            "checkpoint_week_intervals": list(path.checkpoint_week_intervals),
        }

        steps_params = [
            {
                "path_uid": path.uid,
                "uid": step.uid,
                "title": step.title,
                "intent": step.intent,
                "description": step.description,
                "learning_path_uid": step.learning_path_uid,
                "sequence": step.sequence,
                "mastery_threshold": step.mastery_threshold,
                "current_mastery": step.current_mastery,
                "estimated_hours": step.estimated_hours,
                "step_difficulty": get_enum_value(step.step_difficulty),
                "status": get_enum_value(step.status),
                "domain": get_enum_value(step.domain),
            }
            for step in steps
        ]

        result = await self.backend.persist_path_with_steps(user_uid, path_params, steps_params)  # type: ignore[attr-defined]
        if result.is_error:
            return Result.fail(result)

        logger.debug(f"✅ Persisted path {path.uid} with {len(steps)} steps")
        return Result.ok(True)
