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

from core.models.type_hints import UserUID
from core.ports.query_types import (
    LpBlockerAnalysis,
    LpPathRecommendation,
    LpPrerequisiteValidation,
    LpRecommendedStep,
)
from core.services.filtered_context import build_filtered_context
from core.services.lp.lp_ai_service import LpAIService
from core.utils.list_helpers import SortConfig, apply_entity_sort
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_created_at_attr, get_title_lower, make_attribute_sort_key

if TYPE_CHECKING:
    from core.models.enums.entity_enums import Domain
    from core.models.pathways.learning_path import LearningPath
    from core.models.pathways.path_step import PathStep
    from core.ports import EventBusOperations
    from core.ports.query_types import ListContext
    from core.services.ps_service import PsService
    from ui.ui_types import ActivePathData

logger = get_logger(__name__)


def _compute_lp_stats(all_paths: list[Any]) -> dict[str, int | float]:
    """Compute pre-filter stats from the full learning path set."""
    total = len(all_paths)
    return {"total": total, "active": total}


_LP_SORT_CONFIG: SortConfig = {
    "title": (get_title_lower, False),
    "created_at": (get_created_at_attr, True),
}


def _apply_lp_sort(paths: list[Any], sort_by: str) -> list[Any]:
    """Sort learning paths using declarative config."""
    return apply_entity_sort(paths, sort_by, _LP_SORT_CONFIG, "title")


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
    - Core: CRUD operations (non-standard: requires ps_service)
    - Search: Discovery operations
    - Relationships: Path-step associations (via UnifiedRelationshipService)
    - Intelligence: ALL validation/analysis/adaptive/context operations
    - Progress: Progress tracking (event-driven)

    Explicit Delegations:
    - Core: create_path_from_knowledge_units, create_path, get_learning_paths_batch,
            get_learning_path, list_user_paths, list_all_paths, get_path_steps,
            get_current_step, update_path, delete_path
    - Intelligence: validate_path_prerequisites, identify_path_blockers,
            get_optimal_path_recommendation, analyze_path_knowledge_scope,
            find_learning_sequence, get_next_adaptive_step, get_recommended_path_steps

    Explicit Methods (custom logic):
    - Step operations: create_step, get_step, update_step, delete_step, list_steps (ps_service guard)
    - CRUD compatibility: create, get, update, delete, list (complex signatures)
    """

    def __init__(
        self,
        backend: Any,
        ps_service: PsService,
        ku_service: PsService | None = None,
        progress_service: Any | None = None,
        graph_intel: Any | None = None,
        event_bus: EventBusOperations | None = None,
        progress_backend: Any | None = None,
        user_service: Any | None = None,
        ai_service: LpAIService | None = None,
    ) -> None:
        """
        Initialize facade with sub-services via factory.

        FAIL-FAST ARCHITECTURE (per CLAUDE.md):
        The backend, ps_service, and graph_intel are REQUIRED.
        Services run at full capacity or fail immediately at startup.

        **January 2026 - Factory Pattern (Architecture Consistency Review):**
        Uses create_lp_sub_services() factory for consistent initialization.
        Factory handles cross-domain dependency: LpCoreService requires ps_service.

        Args:
            backend: BackendOperations for LP entities (REQUIRED — created by composition root)
            ps_service: PsService for path step operations - REQUIRED
            ku_service: Optional PsService for prerequisite queries
            progress_service: Optional UserProgressService for progress tracking
            graph_intel: GraphIntelligenceService - REQUIRED for cross-domain queries
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
        if not ps_service:
            raise ValueError(
                "LpService ps_service is REQUIRED. "
                "SKUEL follows fail-fast architecture - all required dependencies "
                "must be provided at initialization."
            )
        if not graph_intel:
            raise ValueError(
                "LpService graph_intel is REQUIRED. "
                "SKUEL follows fail-fast architecture - graph intelligence enables "
                "cross-domain queries for curriculum domains."
            )

        # Create all sub-services via factory (January 2026 - Architecture Consistency)
        from core.services.curriculum_domain_config import create_lp_sub_services

        subs = create_lp_sub_services(
            backend=backend,
            ps_service=ps_service,
            graph_intel=graph_intel,
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
        self.ps_service = ps_service
        self.ku_service = ku_service
        self.graph_intel = graph_intel
        self.event_bus = event_bus
        self.ai: LpAIService | None = ai_service
        self.logger = logger

        logger.info(
            "LpService initialized via factory (5 sub-services, cross-domain dependency handled)"
        )

    # ============================================================================
    # CORE CRUD OPERATIONS - Delegated to LpCoreService
    # ============================================================================

    async def create_path_from_knowledge_units(
        self,
        user_uid: UserUID,
        knowledge_units: list[Any],
        title: str | None = None,
        description: str | None = None,
    ) -> Result[LearningPath]:
        """Create a learning path from knowledge units."""
        return await self.core.create_path_from_knowledge_units(
            user_uid, knowledge_units, title, description
        )

    async def create_path(
        self,
        user_uid: UserUID,
        title: str,
        description: str,
        steps: list[PathStep],
        domain: Domain | None = None,
    ) -> Result[LearningPath]:
        """Create a learning path."""
        if domain is None:
            from core.models.enums import Domain

            domain = Domain.LEARNING
        return await self.core.create_path(
            user_uid=user_uid,
            title=title,
            description=description,
            steps=steps,
            domain=domain,
        )

    async def get_learning_paths_batch(self, uids: list[str]) -> Result[list[LearningPath | None]]:
        """Get multiple learning paths in one query."""
        return await self.core.get_learning_paths_batch(uids)

    async def get_learning_path(self, uid: str) -> Result[LearningPath | None]:
        """Get a learning path by UID."""
        return await self.core.get_learning_path(uid)

    async def list_user_paths(
        self, user_uid: UserUID, limit: int = 100
    ) -> Result[list[LearningPath]]:
        """List learning paths for a user."""
        return await self.core.list_user_paths(user_uid, limit)

    async def list_all_paths(self, limit: int = 100) -> Result[list[LearningPath]]:
        """List all learning paths."""
        return await self.core.list_all_paths(limit=limit)

    async def get_path_steps(self, path_uid: str) -> Result[list[PathStep]]:
        """Get steps in a learning path."""
        return await self.core.get_path_steps(path_uid)

    async def get_exercises_for_lp(self, lp_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all Exercises reachable from an LP via its PathSteps.

        Backend: LpBackend.get_exercises_for_lp — HAS_STEP → HAS_EXERCISE traversal.
        Returns distinct exercises with path_step_uid/title for grouping, ordered
        by step sequence then exercise title.
        """
        return await self.core.backend.get_exercises_for_lp(lp_uid)  # type: ignore[attr-defined]

    async def get_current_step(self, path_uid: str) -> Result[PathStep | None]:
        """Get current step for a user in a learning path."""
        return await self.core.get_current_step(path_uid)

    async def update_path(self, uid: str, updates: dict[str, Any]) -> Result[LearningPath]:
        """Update a learning path."""
        return await self.core.update_path(uid, updates)

    async def delete_path(self, uid: str) -> Result[bool]:
        """Delete a learning path."""
        return await self.core.delete_path(uid)

    # ============================================================================
    # INTELLIGENCE OPERATIONS - Delegated to LpIntelligenceService
    # ============================================================================

    async def validate_path_prerequisites(self, path_uid: str) -> Result[LpPrerequisiteValidation]:
        """Validate prerequisites for a learning path."""
        return await self.intelligence.validate_path_prerequisites(path_uid)

    async def identify_path_blockers(
        self, path_uid: str, user_uid: UserUID
    ) -> Result[LpBlockerAnalysis]:
        """Identify blockers in a learning path."""
        return await self.intelligence.identify_path_blockers(path_uid, user_uid)

    async def get_optimal_path_recommendation(
        self, user_uid: UserUID, goal_domain: str | None = None
    ) -> Result[LpPathRecommendation]:
        """Get optimal path recommendation."""
        return await self.intelligence.get_optimal_path_recommendation(user_uid, goal_domain)

    async def analyze_path_knowledge_scope(self, path_uid: str) -> Result[dict[str, Any]]:
        """Analyze knowledge scope of a learning path."""
        return await self.intelligence.analyze_path_knowledge_scope(path_uid)

    async def find_learning_sequence(
        self, start_uid: str, goal_uid: str, _user_uid: UserUID | None = None
    ) -> Result[list[str]]:
        """Find learning sequence."""
        return await self.intelligence.find_learning_sequence(start_uid, goal_uid, _user_uid)

    async def get_next_adaptive_step(
        self,
        current_step_uid: str,
        user_uid: UserUID,
        _user_performance: dict[str, float] | None = None,
    ) -> Result[str | None]:
        """Get next adaptive path step."""
        return await self.intelligence.get_next_adaptive_step(
            current_step_uid, user_uid, _user_performance
        )

    async def get_recommended_path_steps(
        self, user_uid: UserUID, max_difficulty: float = 0.5, limit: int = 5
    ) -> Result[list[LpRecommendedStep]]:
        """Get recommended path steps."""
        return await self.intelligence.get_recommended_path_steps(user_uid, max_difficulty, limit)

    # ============================================================================
    # LEARNING STEP OPERATIONS - Delegated to PsService
    # ============================================================================
    # Note: These require ps_service guard, kept explicit.

    async def create_step(self, step: PathStep, path_uid: str | None = None) -> Result[PathStep]:
        """Create a path step. Delegates to PsService."""
        if not self.ps_service:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(message="PsService not available", operation="create_step")
            )
        return await self.ps_service.create_step(step, path_uid)

    async def get_step(self, step_uid: str) -> Result[PathStep | None]:
        """Get a path step by UID. Delegates to PsService."""
        if not self.ps_service:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(message="PsService not available", operation="get_step")
            )
        return await self.ps_service.get_step(step_uid)

    async def update_step(self, step_uid: str, updates: dict[str, Any]) -> Result[PathStep]:
        """Update a path step. Delegates to PsService."""
        if not self.ps_service:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(message="PsService not available", operation="update_step")
            )
        return await self.ps_service.update_step(step_uid, updates)

    async def delete_step(self, step_uid: str) -> Result[bool]:
        """Delete a path step. Delegates to PsService."""
        if not self.ps_service:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(message="PsService not available", operation="delete_step")
            )
        return await self.ps_service.delete_step(step_uid)

    async def list_steps(
        self, path_uid: str | None = None, limit: int = 100
    ) -> Result[list[PathStep]]:
        """List path steps. Delegates to PsService."""
        if not self.ps_service:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(message="PsService not available", operation="list_steps")
            )
        return await self.ps_service.list_steps(path_uid, limit)

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
        user_uid: UserUID,
        user_progress: Any | None = None,
    ) -> Result[dict[str, Any]]:
        """Build the full pathways dashboard summary for a user.

        Fetches user paths, calculates progress, and optionally fetches knowledge profile.
        """
        from ui.ui_types import LearningStatsData

        paths_result = await self.list_user_paths(user_uid)
        if paths_result.is_error:
            return Result.fail(paths_result)

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
            return Result.fail(paths_result)

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
        user_uid: UserUID,
    ) -> Result[dict[str, Any]]:
        """Get a learning path with progress and mastery info for a user."""
        path_result = await self.get_learning_path(path_uid)
        if path_result.is_error:
            return Result.fail(path_result)
        if not path_result.value:
            return Result.fail(Errors.not_found(resource="LearningPath", identifier=path_uid))

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
        user_uid: UserUID,
        user_progress: Any | None,
    ) -> Result[dict[str, Any]]:
        """Get learning analytics data from user's knowledge profile."""
        # NOTE: "needs_review" / "struggling" keys removed (SKUEL030 tranche 3) —
        # they counted UserKnowledgeProfile sets fed by writer-less
        # :NEEDS_REVIEW / :STRUGGLING_WITH edge reads, so both were always 0.
        analytics: dict[str, Any] = {
            "concepts_mastered": 0,
            "in_progress": 0,
            "active_paths_count": 0,
            "avg_retention": 0.0,
        }

        if user_progress:
            profile_result = await user_progress.build_user_knowledge_profile(user_uid)
            if not profile_result.is_error and profile_result.value:
                profile = profile_result.value
                analytics["concepts_mastered"] = len(profile.mastered_knowledge)
                analytics["in_progress"] = len(profile.in_progress_knowledge)
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
        user_uid = UserUID(str(getattr(entity, "user_uid", "demo_user")))
        steps = entity.metadata.get("steps", []) if entity.metadata else []
        return await self.create_path(
            user_uid=user_uid,
            title=entity.title,
            description=entity.description or "",
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
        user_uid: UserUID | None = None,
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
            except (AttributeError, TypeError):  # fmt: skip
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
        user_uid: UserUID,
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
