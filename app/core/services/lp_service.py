"""
Learning Path Service - Facade
================================

THE single owner for all learning path management in SKUEL.

Delegates to specialized sub-services following the unified domain pattern.

Sub-Services:
- LpCoreService: CRUD operations + persistence (extends BaseService)
- LpSearchService: Search operations (extends BaseService)
- LpProgressService: Progress tracking (event-driven)
- UnifiedRelationshipService: Path-step associations (shared with other domains)
- LpIntelligenceService: Validation, adaptive learning, context
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.services.filtered_context import build_filtered_context
from core.services.lp.lp_ai_service import LpAIService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import make_attribute_sort_key

if TYPE_CHECKING:
    from core.models.pathways.learning_path import LearningPath
    from core.models.pathways.learning_step import LearningStep
    from core.ports import EventBusOperations
    from core.ports.query_types import ListContext
    from core.services.lesson_service import LessonService
    from core.services.ls_service import LsService
    from ui.ui_types import ActivePathData

logger = get_logger(__name__)


def _compute_lp_stats(all_paths: list[Any]) -> dict[str, int | float]:
    """Compute pre-filter stats from the full learning path set."""
    return {"total": len(all_paths)}


def _get_lp_title_lower(path: Any) -> str:
    """Sort key: path title lowercase (SKUEL012: named function, no lambda)."""
    return getattr(path, "title", "").lower()


def _get_lp_created_at(path: Any) -> str:
    """Sort key: path created_at (SKUEL012: named function, no lambda)."""
    return getattr(path, "created_at", "")


def _apply_lp_sort(paths: list[Any], sort_by: str = "title") -> list[Any]:
    """Sort learning paths by specified field."""
    if sort_by == "title":
        return sorted(paths, key=_get_lp_title_lower)
    elif sort_by == "created_at":
        return sorted(paths, key=_get_lp_created_at, reverse=True)
    return sorted(paths, key=_get_lp_title_lower)


def _difficulty_label(rating: float) -> str:
    """Convert 0.0-1.0 difficulty rating to human-readable label."""
    if rating <= 0.35:
        return "beginner"
    if rating <= 0.65:
        return "intermediate"
    return "advanced"


def _path_to_display_dict(path: Any) -> dict[str, Any]:
    """Convert a LearningPath domain model to a display dict for browser cards."""
    return {
        "uid": path.uid,
        "title": path.title or "Untitled Path",
        "description": path.description or "",
        "difficulty": _difficulty_label(path.difficulty_rating),
        "estimated_hours": int(path.estimated_hours or 0),
        "tags": list(path.tags) if path.tags else [],
    }


class LpService:
    """
    Facade for learning path management.

    **January 2026 - LP Consolidation (ADR-031):**
    Consolidated from 8 sub-services to 4:
    - Core: CRUD operations (non-standard: requires ls_service)
    - Search: Discovery operations
    - Relationships: Path-step associations (via UnifiedRelationshipService)
    - Intelligence: ALL validation/analysis/adaptive/context operations
    - Progress: Progress tracking (event-driven)

    Explicit Delegations:
    - Core: create_path_from_knowledge_units, create_path, get_learning_paths_batch,
            get_learning_path, list_user_paths, list_all_paths, get_path_steps,
            get_current_step, update_path, delete_path
    - Intelligence: validate_path_prerequisites, identify_path_blockers,
            get_optimal_path_recommendation, get_path_with_context,
            analyze_path_knowledge_scope,
            find_learning_sequence, get_next_adaptive_step, get_recommended_learning_steps

    Explicit Methods (custom logic):
    - Step operations: create_step, get_step, update_step, delete_step, list_steps (ls_service guard)
    - CRUD compatibility: create, get, update, delete, list (complex signatures)
    """

    def __init__(
        self,
        backend: Any,
        executor: Any,
        ls_service: LsService,
        ku_service: LessonService | None = None,
        progress_service: Any | None = None,
        graph_intelligence_service: Any | None = None,
        event_bus: EventBusOperations | None = None,
        progress_backend: Any | None = None,
        user_service: Any | None = None,
        ai_service: LpAIService | None = None,
    ) -> None:
        """
        Initialize facade with sub-services via factory.

        FAIL-FAST ARCHITECTURE (per CLAUDE.md):
        The backend, executor, ls_service, and graph_intelligence_service are REQUIRED.
        Services run at full capacity or fail immediately at startup.

        **January 2026 - Factory Pattern (Architecture Consistency Review):**
        Uses create_lp_sub_services() factory for consistent initialization.
        Factory handles cross-domain dependency: LpCoreService requires ls_service.

        Args:
            backend: BackendOperations for LP entities (REQUIRED — created by composition root)
            executor: QueryExecutor for raw Cypher (REQUIRED — created by composition root)
            ls_service: LsService for learning step operations - REQUIRED
            ku_service: Optional LessonService for prerequisite queries
            progress_service: Optional UserProgressService for progress tracking
            graph_intelligence_service: GraphIntelligenceService - REQUIRED for cross-domain queries
            event_bus: Event bus for publishing domain events (optional)
            progress_backend: UserProgress backend for learning state analysis (optional)
            user_service: UserService for UserContext access (optional)
            ai_service: Optional LpAIService for AI features (ADR-030 separation)
        """
        # FAIL-FAST: Required dependencies
        if not backend:
            raise ValueError(
                "LpService backend is REQUIRED. "
                "SKUEL follows fail-fast architecture - all required dependencies "
                "must be provided at initialization."
            )
        if not executor:
            raise ValueError(
                "LpService executor is REQUIRED. "
                "SKUEL follows fail-fast architecture - all required dependencies "
                "must be provided at initialization."
            )
        if not ls_service:
            raise ValueError(
                "LpService ls_service is REQUIRED. "
                "SKUEL follows fail-fast architecture - all required dependencies "
                "must be provided at initialization."
            )
        if not graph_intelligence_service:
            raise ValueError(
                "LpService graph_intelligence_service is REQUIRED. "
                "SKUEL follows fail-fast architecture - graph intelligence enables "
                "cross-domain queries for curriculum domains."
            )

        # Create all sub-services via factory (January 2026 - Architecture Consistency)
        from core.utils.curriculum_domain_config import create_lp_sub_services

        subs = create_lp_sub_services(
            backend=backend,
            executor=executor,
            ls_service=ls_service,
            graph_intelligence_service=graph_intelligence_service,
            event_bus=event_bus,
            progress_backend=progress_backend,
            user_service=user_service,
        )

        # Assign sub-services from factory result
        self.core = subs.core
        self.search = subs.search
        self.relationships = subs.relationships
        self.intelligence = subs.intelligence
        self.progress = subs.progress

        # Store dependencies
        self.ls_service = ls_service
        self.ku_service = ku_service
        self.graph_intel = graph_intelligence_service
        self.event_bus = event_bus
        self.ai: LpAIService | None = ai_service
        self.logger = logger

        logger.info(
            "LpService initialized via factory (5 sub-services, cross-domain dependency handled)"
        )

    # ============================================================================
    # CORE CRUD OPERATIONS - Delegated to LpCoreService
    # ============================================================================

    async def create_path_from_knowledge_units(self, *args: Any, **kwargs: Any) -> Result[Any]:
        """Create a learning path from knowledge units."""
        return await self.core.create_path_from_knowledge_units(*args, **kwargs)

    async def create_path(self, *args: Any, **kwargs: Any) -> Result[Any]:
        """Create a learning path."""
        return await self.core.create_path(*args, **kwargs)

    async def get_learning_paths_batch(self, uids: list[str]) -> Result[Any]:
        """Get multiple learning paths in one query."""
        return await self.core.get_learning_paths_batch(uids)

    async def get_learning_path(self, uid: str) -> Result[Any]:
        """Get a learning path by UID."""
        return await self.core.get_learning_path(uid)

    async def list_user_paths(self, user_uid: str, limit: int = 100) -> Result[Any]:
        """List learning paths for a user."""
        return await self.core.list_user_paths(user_uid, limit)

    async def list_all_paths(self, limit: int = 100) -> Result[Any]:
        """List all learning paths."""
        return await self.core.list_all_paths(limit=limit)

    async def get_path_steps(self, path_uid: str) -> Result[Any]:
        """Get steps in a learning path."""
        return await self.core.get_path_steps(path_uid)

    async def get_current_step(self, path_uid: str) -> Result[Any]:
        """Get current step for a user in a learning path."""
        return await self.core.get_current_step(path_uid)

    async def update_path(self, uid: str, updates: dict[str, Any]) -> Result[Any]:
        """Update a learning path."""
        return await self.core.update_path(uid, updates)

    async def delete_path(self, uid: str) -> Result[Any]:
        """Delete a learning path."""
        return await self.core.delete_path(uid)

    # ============================================================================
    # INTELLIGENCE OPERATIONS - Delegated to LpIntelligenceService
    # ============================================================================

    async def validate_path_prerequisites(self, *args: Any, **kwargs: Any) -> Result[Any]:
        """Validate prerequisites for a learning path."""
        return await self.intelligence.validate_path_prerequisites(*args, **kwargs)

    async def identify_path_blockers(self, *args: Any, **kwargs: Any) -> Result[Any]:
        """Identify blockers in a learning path."""
        return await self.intelligence.identify_path_blockers(*args, **kwargs)

    async def get_optimal_path_recommendation(self, *args: Any, **kwargs: Any) -> Result[Any]:
        """Get optimal path recommendation."""
        return await self.intelligence.get_optimal_path_recommendation(*args, **kwargs)

    async def get_path_with_context(self, *args: Any, **kwargs: Any) -> Result[Any]:
        """Get learning path with context."""
        return await self.intelligence.get_path_with_context(*args, **kwargs)

    async def analyze_path_knowledge_scope(self, *args: Any, **kwargs: Any) -> Result[Any]:
        """Analyze knowledge scope of a learning path."""
        return await self.intelligence.analyze_path_knowledge_scope(*args, **kwargs)

    async def find_learning_sequence(self, *args: Any, **kwargs: Any) -> Result[Any]:
        """Find learning sequence."""
        return await self.intelligence.find_learning_sequence(*args, **kwargs)

    async def get_next_adaptive_step(self, *args: Any, **kwargs: Any) -> Result[Any]:
        """Get next adaptive learning step."""
        return await self.intelligence.get_next_adaptive_step(*args, **kwargs)

    async def get_recommended_learning_steps(self, *args: Any, **kwargs: Any) -> Result[Any]:
        """Get recommended learning steps."""
        return await self.intelligence.get_recommended_learning_steps(*args, **kwargs)

    # ============================================================================
    # LEARNING STEP OPERATIONS - Delegated to LsService
    # ============================================================================
    # Note: These require ls_service guard, kept explicit.

    async def create_step(
        self, step: LearningStep, path_uid: str | None = None
    ) -> Result[LearningStep]:
        """Create a learning step. Delegates to LsService."""
        if not self.ls_service:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(message="LsService not available", operation="create_step")
            )
        return await self.ls_service.create_step(step, path_uid)

    async def get_step(self, step_uid: str) -> Result[LearningStep | None]:
        """Get a learning step by UID. Delegates to LsService."""
        if not self.ls_service:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(message="LsService not available", operation="get_step")
            )
        return await self.ls_service.get_step(step_uid)

    async def update_step(self, step_uid: str, updates: dict[str, Any]) -> Result[LearningStep]:
        """Update a learning step. Delegates to LsService."""
        if not self.ls_service:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(message="LsService not available", operation="update_step")
            )
        return await self.ls_service.update_step(step_uid, updates)

    async def delete_step(self, step_uid: str) -> Result[bool]:
        """Delete a learning step. Delegates to LsService."""
        if not self.ls_service:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(message="LsService not available", operation="delete_step")
            )
        return await self.ls_service.delete_step(step_uid)

    async def list_steps(
        self, path_uid: str | None = None, limit: int = 100
    ) -> Result[list[LearningStep]]:
        """List learning steps. Delegates to LsService."""
        if not self.ls_service:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(message="LsService not available", operation="list_steps")
            )
        return await self.ls_service.list_steps(path_uid, limit)

    # ============================================================================
    # AGGREGATION METHODS — extracted from pathways_ui.py route handlers
    # ============================================================================

    def calculate_path_progress(
        self,
        paths: list[Any],
    ) -> tuple[list[ActivePathData], float]:
        """Calculate progress data for a list of learning paths.

        Pure computation over already-fetched path objects.

        Returns:
            Tuple of (active_path_data_list, total_hours).
        """
        from ui.ui_types import ActivePathData

        active_paths: list[ActivePathData] = []
        total_hours = 0.0

        for path in paths:
            steps = path.metadata.get("steps", []) if path.metadata else []
            total_steps = len(steps)
            mastered_count = sum(1 for s in steps if s.is_mastered())
            progress = (mastered_count / total_steps * 100.0) if total_steps > 0 else 0.0

            current_step = "Complete"
            for s in steps:
                if not s.is_mastered():
                    current_step = s.title or "Next step"
                    break

            total_hours += path.estimated_hours or 0
            active_paths.append(
                ActivePathData(
                    uid=path.uid,
                    title=path.title or "Untitled Path",
                    progress=progress,
                    current_step=current_step,
                    estimated_completion=f"{int(path.estimated_hours or 0)}h total",
                    difficulty=_difficulty_label(path.difficulty_rating),
                    time_invested=f"{int(path.estimated_hours or 0)}h est.",
                )
            )

        return active_paths, total_hours

    async def get_dashboard_summary(
        self,
        user_uid: str,
        user_progress: Any | None = None,
    ) -> Result[dict[str, Any]]:
        """Build the full pathways dashboard summary for a user.

        Fetches user paths, calculates progress, and optionally fetches knowledge profile.
        """
        from ui.ui_types import LearningStatsData

        paths_result = await self.list_user_paths(user_uid)
        if paths_result.is_error:
            return Result.fail(paths_result.expect_error())

        paths = paths_result.value or []
        active_paths, total_hours = self.calculate_path_progress(paths)

        concepts_mastered = 0
        if user_progress:
            profile_result = await user_progress.build_user_knowledge_profile(user_uid)
            if not profile_result.is_error and profile_result.value:
                concepts_mastered = len(profile_result.value.mastered_knowledge)

        completion_rate = 0.0
        if active_paths:
            completed = sum(1 for p in active_paths if p.progress >= 100.0)
            completion_rate = completed / len(active_paths)

        stats = LearningStatsData(
            total_hours=total_hours,
            concepts_mastered=concepts_mastered,
            active_streak=0,
            completion_rate=completion_rate,
        )

        return Result.ok(
            {
                "active_paths": active_paths,
                "stats": stats,
            }
        )

    async def filter_paths(
        self,
        difficulty: str = "all",
        domain: str = "all",
        duration: str = "all",
        limit: int = 50,
    ) -> Result[list[dict[str, Any]]]:
        """Fetch and filter learning paths by difficulty, domain, and duration."""
        paths_result = await self.list_all_paths(limit=limit)
        if paths_result.is_error:
            return Result.fail(paths_result.expect_error())

        paths = [_path_to_display_dict(p) for p in (paths_result.value or [])]

        if difficulty and difficulty != "all":
            paths = [p for p in paths if p["difficulty"] == difficulty]
        if domain and domain != "all":
            paths = [p for p in paths if domain in p["tags"]]
        if duration and duration != "all":
            if duration == "short":
                paths = [p for p in paths if p["estimated_hours"] < 20]
            elif duration == "medium":
                paths = [p for p in paths if 20 <= p["estimated_hours"] <= 50]
            elif duration == "long":
                paths = [p for p in paths if p["estimated_hours"] > 50]

        return Result.ok(paths)

    async def get_path_detail_progress(
        self,
        path_uid: str,
        user_progress: Any | None,
        user_uid: str,
    ) -> Result[dict[str, Any]]:
        """Get a learning path with progress and mastery info for a user."""
        path_result = await self.get_learning_path(path_uid)
        if path_result.is_error or not path_result.value:
            return Result.fail(
                path_result.expect_error()
                if path_result.is_error
                else Errors.not_found(resource="LearningPath", identifier=path_uid)
            )

        path = path_result.value
        steps = path.metadata.get("steps", []) if path.metadata else []
        total_steps = len(steps)

        mastered_uids: set[str] = set()
        is_enrolled = False
        if user_progress:
            profile_result = await user_progress.build_user_knowledge_profile(user_uid)
            if not profile_result.is_error and profile_result.value:
                profile = profile_result.value
                mastered_uids = profile.mastered_uids
                is_enrolled = path_uid in profile.active_learning_paths

        mastered_steps = sum(1 for s in steps if s.uid in mastered_uids or s.is_mastered())
        progress = (mastered_steps / total_steps * 100.0) if total_steps > 0 else 0.0

        return Result.ok(
            {
                "path": path,
                "steps": steps,
                "progress": progress,
                "mastered_uids": mastered_uids,
                "is_enrolled": is_enrolled,
            }
        )

    async def get_learning_analytics(
        self,
        user_uid: str,
        user_progress: Any | None,
    ) -> Result[dict[str, Any]]:
        """Get learning analytics data from user's knowledge profile."""
        analytics: dict[str, Any] = {
            "concepts_mastered": 0,
            "in_progress": 0,
            "needs_review": 0,
            "struggling": 0,
            "active_paths_count": 0,
            "avg_retention": 0.0,
        }

        if user_progress:
            profile_result = await user_progress.build_user_knowledge_profile(user_uid)
            if not profile_result.is_error and profile_result.value:
                profile = profile_result.value
                analytics["concepts_mastered"] = len(profile.mastered_knowledge)
                analytics["in_progress"] = len(profile.in_progress_knowledge)
                analytics["needs_review"] = len(profile.needs_review_uids)
                analytics["struggling"] = len(profile.struggling_uids)
                analytics["active_paths_count"] = len(profile.active_learning_paths)
                if profile.mastered_knowledge:
                    analytics["avg_retention"] = sum(
                        m.retention_score for m in profile.mastered_knowledge
                    ) / len(profile.mastered_knowledge)

        return Result.ok(analytics)

    # ============================================================================
    # CRUD OPERATIONS PROTOCOL COMPATIBILITY
    # ============================================================================

    async def create(self, entity: LearningPath) -> Result[LearningPath]:
        """Create method for CRUDRouteFactory compatibility."""
        user_uid = getattr(entity, "user_uid", "demo_user")
        steps = entity.metadata.get("steps", []) if entity.metadata else []
        return await self.create_path(
            user_uid=user_uid,
            title=entity.title,
            description=entity.description,
            steps=steps,
            domain=entity.domain,
        )

    async def get(self, uid: str) -> Result[LearningPath | None]:
        """Get method for CRUDRouteFactory compatibility."""
        return await self.get_learning_path(uid)

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[LearningPath]:
        """Update method for CRUDRouteFactory compatibility."""
        return await self.update_path(uid, updates)

    async def delete(self, uid: str) -> Result[bool]:
        """Delete method for CRUDRouteFactory compatibility."""
        return await self.delete_path(uid)

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
        user_uid: str | None = None,
    ) -> Result[list[LearningPath]]:
        """
        List learning paths with pagination and sorting support.

        CRUDRouteFactory compatible method with full filtering/sorting.

        Args:
            limit: Maximum number of paths to return
            offset: Number of paths to skip (for pagination)
            order_by: Field to sort by (e.g., 'title', 'created_at')
            order_desc: Sort in descending order if True
            user_uid: Filter by user (if provided)
        """
        if user_uid:
            return await self.list_user_paths(user_uid, limit)

        # Service-layer filtering pattern: get more results to allow pagination
        backend_limit = limit + offset if offset > 0 else limit
        result = await self.list_all_paths(limit=backend_limit)

        if result.is_error:
            return result

        paths = result.value

        # Service-layer filtering: sorting
        if order_by:
            reverse = order_desc
            try:
                sort_key = make_attribute_sort_key(order_by)
                paths = sorted(paths, key=sort_key, reverse=reverse)
            except (AttributeError, TypeError):
                # If order_by field doesn't exist or can't be compared, skip sorting
                pass

        # Service-layer filtering: pagination (offset)
        if offset > 0:
            paths = paths[offset:]

        # Apply final limit
        paths = paths[:limit]

        return Result.ok(paths)

    # =========================================================================
    # QUERY LAYER (FilteredContextProvider)
    # =========================================================================

    async def get_filtered_context(
        self,
        user_uid: str,
        status_filter: str = "all",
        sort_by: str = "title",
    ) -> Result[ListContext]:
        """Get filtered and sorted learning paths with pre-filter stats."""

        async def fetch_all() -> Result[list[Any]]:
            return await self.list_all_paths(limit=500)

        def apply_filters(all_paths: list[Any]) -> list[Any]:
            return all_paths  # LP has no status filtering

        return await build_filtered_context(
            fetch_all=fetch_all,
            compute_stats=_compute_lp_stats,
            apply_filters=apply_filters,
            apply_sort=_apply_lp_sort,
            sort_by=sort_by,
        )
