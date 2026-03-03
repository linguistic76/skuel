"""
Enhanced Goals Service - Facade Pattern
========================================

Goals service facade that delegates to specialized sub-services.

Sub-Services:
- GoalsCoreService: CRUD operations
- GoalsSearchService: Search and discovery (DomainSearchOperations[Goal] protocol)
- GoalsProgressService: Progress tracking and milestones
- GoalsLearningService: Learning path integration
- GoalsSchedulingService: Capacity management and schedule optimization (January 2026)
- UnifiedRelationshipService (GOALS_CONFIG): Graph relationships and cross-domain links
- GoalsIntelligenceService: pure Cypher analytics
- GoalsRecommendationService: Intelligent goal recommendations
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, Any

from core.models.enums import EntityStatus, Priority
from core.models.goal.goal import Goal
from core.models.goal.goal_dto import GoalDTO
from core.ports.domain_protocols import GoalsOperations
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config

# Import sub-services
from core.services.goals import (
    GoalsIntelligenceService,
    GoalsLearningService,
    GoalsProgressService,
    GoalsRecommendationService,
    GoalsSchedulingService,
)
from core.services.goals.goal_relationships import GoalRelationships
from core.services.goals.goals_ai_service import GoalsAIService
from core.services.goals_types import GoalFeasibilityAssessment
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService

# Unified relationship service (replaces GoalsRelationshipService)
from core.services.relationships import UnifiedRelationshipService
from core.utils.activity_domain_config import create_common_sub_services
from core.utils.dto_helpers import to_domain_model
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import (
    get_created_at_attr,
    get_current_value,
    make_priority_string_getter,
)

if TYPE_CHECKING:
    from core.ports.query_types import ListContext
    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.goal.goal_request import GoalCreateRequest
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.search_protocols import GoalsSearchOperations
    from core.services.user import UserContext


def _get_goal_status_str(goal: Any) -> str:
    """Extract status as lowercase string, handling both enum and string."""
    status = getattr(goal, "status", "active")
    if isinstance(status, Enum):
        return str(status.value).lower()
    return str(status).lower()


def _get_goal_priority_str(goal: Any) -> str:
    """Extract priority as lowercase string, handling both enum and string."""
    priority = getattr(goal, "priority", "medium")
    if isinstance(priority, Enum):
        return str(priority.value).lower()
    return str(priority).lower()


def _get_goal_target_date(goal: Any) -> date:
    """Extract target_date as date object, handling both date and string."""
    target = getattr(goal, "target_date", None)
    if target is None:
        return date.max
    if isinstance(target, date):
        return target
    if isinstance(target, str):
        try:
            return date.fromisoformat(target)
        except ValueError:
            pass
    return date.max




_GOAL_PRIORITY_ORDER: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _apply_goal_sort(goals: list[Any], sort_by: str = "target_date") -> list[Any]:
    """Sort goals by specified field."""
    if sort_by == "target_date":
        return sorted(goals, key=_get_goal_target_date)
    elif sort_by == "priority":
        sort_key = make_priority_string_getter(_GOAL_PRIORITY_ORDER, _get_goal_priority_str)
        return sorted(goals, key=sort_key)
    elif sort_by == "progress":
        return sorted(goals, key=get_current_value, reverse=True)
    elif sort_by == "created_at":
        return sorted(goals, key=get_created_at_attr, reverse=True)
    return sorted(goals, key=_get_goal_target_date)


class GoalsService(BaseService[GoalsOperations, Goal]):
    """
    Goals service facade with specialized sub-services.

    This facade:
    1. Delegates to 8 specialized sub-services for core operations
    2. Uses explicit delegation methods (~40 methods) for sub-service access
    3. Retains explicit methods for complex orchestration operations
    4. Provides clean separation of concerns

    Delegations (explicit methods):
    - Core: get_goal, get_user_goals, get_user_items_in_range, activate/pause/complete/archive
    - Progress: calculate_goal_progress_with_context, complete_milestone, etc.
    - Learning: create_goal_with_learning_integration, assess_goal_learning_alignment, etc.
    - Search: search_goals, get_goals_by_status, get_prioritized_goals, etc.
    - Intelligence: get_goal_with_context, get_goal_progress_dashboard, etc.
    - Scheduling: check_goal_capacity, suggest_goal_timeline, assess_goal_achievability, etc.

    Explicit Methods (custom logic):
    - Relationship linking: link_goal_to_habit, link_goal_to_knowledge, link_goal_to_principle
    - Orchestration: create_goal_with_context, generate_tasks_for_goal, assess_goal_feasibility

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - Uses explicit delegation methods (February 2026)
    - No APOC calls (uses pure Cypher)
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    # ========================================================================
    # DOMAIN CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================
    # Facade services use same config as core/search sub-services
    _config = create_activity_domain_config(
        dto_class=GoalDTO,
        model_class=Goal,
        domain_name="goals",
        entity_label="Entity",
        date_field="target_date",
        completed_statuses=(EntityStatus.COMPLETED.value, EntityStatus.CANCELLED.value),
        category_field="domain",  # Goals use 'domain' field for categorization
    )

    # ========================================================================
    # DELEGATION METHODS
    # ========================================================================

    # Core CRUD delegations
    async def get_goal(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.get_goal(*args, **kwargs)

    async def get_user_goals(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.get_user_goals(*args, **kwargs)

    async def get_user_items_in_range(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.get_user_items_in_range(*args, **kwargs)

    async def activate_goal(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.activate_goal(*args, **kwargs)

    async def pause_goal(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.pause_goal(*args, **kwargs)

    async def complete_goal(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.complete_goal(*args, **kwargs)

    async def archive_goal(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.archive_goal(*args, **kwargs)

    async def create_goal(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.create_goal(*args, **kwargs)

    # Progress delegations
    async def calculate_goal_progress_with_context(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.progress.calculate_goal_progress_with_context(*args, **kwargs)

    async def complete_milestone(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.progress.complete_milestone(*args, **kwargs)

    async def update_goal_from_habit_progress(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.progress.update_goal_from_habit_progress(*args, **kwargs)

    async def update_goal_progress(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.progress.update_goal_progress(*args, **kwargs)

    async def get_goal_progress(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.progress.get_goal_progress(*args, **kwargs)

    async def create_goal_milestone(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.progress.create_goal_milestone(*args, **kwargs)

    async def get_goal_milestones(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.progress.get_goal_milestones(*args, **kwargs)

    # Learning delegations
    async def create_goal_with_learning_integration(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.learning.create_goal_with_learning_integration(*args, **kwargs)

    async def assess_goal_learning_alignment(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.learning.assess_goal_learning_alignment(*args, **kwargs)

    async def suggest_learning_aligned_goals(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.learning.suggest_learning_aligned_goals(*args, **kwargs)

    async def get_learning_supporting_goals(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.learning.get_learning_supporting_goals(*args, **kwargs)

    async def track_goal_learning_progress(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.learning.track_goal_learning_progress(*args, **kwargs)

    async def get_goals_needing_habits(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.learning.get_goals_needing_habits(*args, **kwargs)

    async def get_goals_blocked_by_knowledge(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.learning.get_goals_blocked_by_knowledge(*args, **kwargs)

    # Relationship delegations
    async def get_goal_cross_domain_context(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.relationships.get_cross_domain_context(*args, **kwargs)

    async def get_goal_with_semantic_context(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.relationships.get_with_semantic_context(*args, **kwargs)

    # Intelligence delegations
    async def get_goal_with_context(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.get_goal_with_context(*args, **kwargs)

    async def get_goal_progress_dashboard(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.get_goal_progress_dashboard(*args, **kwargs)

    async def get_goal_completion_forecast(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.get_goal_completion_forecast(*args, **kwargs)

    async def get_goal_learning_requirements(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.get_goal_learning_requirements(*args, **kwargs)

    # Search delegations
    async def list_goal_categories(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.list_user_categories(*args, **kwargs)

    async def list_all_goal_categories(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.list_all_categories(*args, **kwargs)

    async def get_goals_by_category(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_by_category(*args, **kwargs)

    async def get_goals_by_status(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_by_status(*args, **kwargs)

    async def search_goals(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.search(*args, **kwargs)

    async def get_goals_due_soon(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_due_soon(*args, **kwargs)

    async def get_overdue_goals(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_overdue(*args, **kwargs)

    async def get_goals_by_domain(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_by_domain(*args, **kwargs)

    async def get_prioritized_goals(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_prioritized(*args, **kwargs)

    # Scheduling delegations
    async def check_goal_capacity(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.scheduling.check_goal_capacity(*args, **kwargs)

    async def suggest_goal_timeline(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.scheduling.suggest_goal_timeline(*args, **kwargs)

    async def assess_goal_achievability(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.scheduling.assess_goal_achievability(*args, **kwargs)

    async def get_schedule_aware_next_goal(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.scheduling.get_schedule_aware_next_goal(*args, **kwargs)

    async def optimize_goal_sequencing(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.scheduling.optimize_goal_sequencing(*args, **kwargs)

    async def get_goal_load_by_timeframe(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.scheduling.get_goal_load_by_timeframe(*args, **kwargs)

    async def create_goal_with_scheduling_context(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.scheduling.create_goal_with_context(*args, **kwargs)

    async def create_goal_with_learning_scheduling(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.scheduling.create_goal_with_learning_context(*args, **kwargs)

    def __init__(
        self,
        backend: GoalsOperations,
        graph_intelligence_service: GraphIntelligenceService,
        event_bus: EventBusOperations | None = None,
        ai_service: GoalsAIService | None = None,
    ) -> None:
        """
        Initialize enhanced goals service with specialized sub-services.

        Args:
            backend: Protocol-based backend for goal operations
            graph_intelligence_service: GraphIntelligenceService for pure Cypher analytics (REQUIRED)
            event_bus: Event bus for publishing domain events (optional)
            ai_service: Optional AI service for LLM/embeddings features (January 2026)

        Note:
            Context invalidation now happens via event-driven architecture.
            Goal events trigger user_service.invalidate_context() in bootstrap.

        Migration Note (v3.2.0 - December 2025):
            Made graph_intelligence_service REQUIRED - relationship service needs it.
            Fail-fast at construction, not at method call.

        AI Service Note (January 2026):
            ai_service is OPTIONAL - the app works without it. When provided,
            enables AI-powered features like semantic similarity and insights.
        """
        super().__init__(backend, "goals")

        # AI service (optional - app works without it)
        self.ai: GoalsAIService | None = ai_service

        self.graph_intel = graph_intelligence_service
        self.logger = get_logger("skuel.services.goals")

        # Initialize 3 common sub-services via factory (core, search, relationships)
        # Note: intelligence is created separately because it needs progress_service
        common = create_common_sub_services(
            domain="goals",
            backend=backend,
            graph_intel=graph_intelligence_service,
            event_bus=event_bus,
        )
        self.core = common.core
        self.search: GoalsSearchOperations = common.search
        self.relationships: UnifiedRelationshipService = common.relationships

        # Domain-specific sub-services that need relationships
        self.progress = GoalsProgressService(
            backend=backend,
            event_bus=event_bus,
            relationships_service=self.relationships,
        )

        self.learning = GoalsLearningService(
            backend=backend,
            event_bus=event_bus,
            relationships_service=self.relationships,
        )

        # Intelligence requires progress_service - override factory's version
        self.intelligence: GoalsIntelligenceService = GoalsIntelligenceService(
            backend=backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=self.relationships,
            progress_service=self.progress,
        )

        # Event-driven recommendation service
        self.recommendations = GoalsRecommendationService(
            backend=backend,
            event_bus=event_bus,
        )

        # January 2026: Scheduling service for capacity and timeline management
        self.scheduling = GoalsSchedulingService(
            backend=backend,
            progress_service=self.progress,
            event_bus=event_bus,
        )

        self.logger.info(
            "GoalsService facade initialized with 8 sub-services: "
            "core, search, progress, learning, scheduling, relationships, intelligence, recommendations"
        )

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Goal entities."""
        return "Entity"

    # Note: Backend access uses inherited BaseService._backend property
    # Custom backend property removed November 2025 - was unnecessary indirection

    # ========================================================================
    # GRAPH RELATIONSHIPS - Delegate to UnifiedRelationshipService
    # ========================================================================
    # Note: Simple delegations (Core CRUD, Progress, Learning) auto-generated
    # delegated via explicit method below.

    async def create_user_goal_relationship(
        self, user_uid: str, goal_uid: str, role: str = "owner"
    ) -> Result[bool]:
        """Create User→Goal relationship in graph."""
        properties = {"role": role} if role != "owner" else None
        return await self.relationships.create_user_relationship(user_uid, goal_uid, properties)

    async def link_goal_to_habit(
        self,
        goal_uid: str,
        habit_uid: str,
        weight: float = 1.0,
        contribution_type: str = "consistency",
    ) -> Result[bool]:
        """Link goal to supporting habit with weighted contribution."""
        properties = {"weight": weight, "contribution_type": contribution_type}
        return await self.relationships.create_relationship(
            "supporting_habits", goal_uid, habit_uid, properties
        )

    async def get_goal_habits(self, uid: str) -> Result[list[str]]:
        """Get habits linked to a goal. Delegates to UnifiedRelationshipService."""
        return await self.relationships.get_related_uids("supporting_habits", uid)

    async def unlink_goal_from_habit(self, uid: str, habit_uid: str) -> Result[bool]:
        """Unlink a habit from a goal. Delegates to UnifiedRelationshipService."""
        return await self.relationships.delete_relationship("supporting_habits", uid, habit_uid)

    async def link_goal_to_knowledge(
        self,
        goal_uid: str,
        knowledge_uid: str,
        proficiency_required: str = "intermediate",
        priority: int = 1,
    ) -> Result[bool]:
        """Link goal to required knowledge/skill."""
        return await self.relationships.link_to_knowledge(
            goal_uid,
            knowledge_uid,
            proficiency_required=proficiency_required,
            priority=priority,
        )

    async def link_goal_to_principle(
        self, goal_uid: str, principle_uid: str, alignment_strength: float = 1.0
    ) -> Result[bool]:
        """Link goal to guiding principle/value."""
        return await self.relationships.link_to_principle(
            goal_uid, principle_uid, alignment_strength=alignment_strength
        )

    # Note: get_goal_cross_domain_context, get_goal_with_semantic_context auto-generated
    # delegated via explicit method below.

    async def create_semantic_goal_relationship(
        self,
        goal_uid: str,
        knowledge_uid: str,
        semantic_type: SemanticRelationshipType,
        confidence: float = 0.9,
        notes: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Create semantic relationship between goal and knowledge."""
        return await self.relationships.create_semantic_relationship(
            goal_uid, knowledge_uid, semantic_type, confidence, notes
        )

    async def find_goals_requiring_knowledge(
        self, knowledge_uid: str, min_confidence: float = 0.8
    ) -> Result[list[Goal]]:
        """Find goals that require specific knowledge."""
        return await self.relationships.find_by_semantic_filter(
            target_uid=knowledge_uid, min_confidence=min_confidence, direction="incoming"
        )

    # ========================================================================
    # ORCHESTRATION METHODS - Remain in Facade
    # ========================================================================
    # Note: Intelligence delegations (get_goal_with_context, get_goal_progress_dashboard,
    # get_goal_completion_forecast, get_goal_learning_requirements) auto-generated
    # delegated via explicit method below.

    async def create_goal_with_context(
        self, goal_data: GoalCreateRequest, user_context: UserContext
    ) -> Result[Goal]:
        """
        Create a goal with full context awareness (orchestration method).

        This method orchestrates multiple checks:
        1. Knowledge prerequisites validation
        2. Habit availability validation
        3. Goal creation via learning service
        4. Context invalidation
        """
        # Check knowledge prerequisites
        if goal_data.required_knowledge_uids:
            missing_prereqs = (
                set(goal_data.required_knowledge_uids) - user_context.mastered_knowledge_uids
            )
            if missing_prereqs:
                return Result.fail(
                    Errors.validation(
                        message="Cannot create goal without required knowledge prerequisites",
                        field="required_knowledge_uids",
                        value=list(missing_prereqs),
                        user_message=f"Please master these knowledge areas first: {', '.join(missing_prereqs)}",
                    )
                )

        # Validate habit availability
        if goal_data.supporting_habit_uids:
            inactive_habits = [
                habit_uid
                for habit_uid in goal_data.supporting_habit_uids
                if habit_uid not in user_context.active_habit_uids
            ]
            if inactive_habits:
                return Result.fail(
                    Errors.validation(
                        message="Cannot create goal with inactive supporting habits",
                        field="supporting_habit_uids",
                        value=inactive_habits,
                        user_message=f"Please activate these habits first: {', '.join(inactive_habits)}",
                    )
                )

        # Create goal through learning service (handles DTO creation)
        result = await self.learning.create_goal_with_learning_integration(goal_data, None)
        if result.is_error:
            return result

        # Note: User context invalidation now happens via event-driven architecture
        # GoalCreated event → invalidate_context_on_goal_event() → user_service.invalidate_context()

        goal = result.value
        # GRAPH-NATIVE: Get counts from goal_data (input) since relationships stored in graph
        habit_count = len(goal_data.supporting_habit_uids) if goal_data.supporting_habit_uids else 0
        knowledge_count = (
            len(goal_data.required_knowledge_uids) if goal_data.required_knowledge_uids else 0
        )
        self.logger.info(
            "Created goal %s with %d habits, %d knowledge requirements",
            goal.uid,
            habit_count,
            knowledge_count,
        )

        return Result.ok(goal)

    async def generate_tasks_for_goal(
        self, goal_uid: str, user_context: UserContext
    ) -> Result[list[dict[str, Any]]]:
        """
        Generate task suggestions for achieving a goal (orchestration method).

        This combines goal data with user context to generate:
        - Milestone tasks
        - Knowledge acquisition tasks
        - Habit reinforcement tasks
        """
        goal_result = await self.backend.get_goal(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        goal = to_domain_model(goal_result.value, GoalDTO, Goal)

        # GRAPH-NATIVE: Fetch relationships from graph
        rels = await GoalRelationships.fetch(goal_uid, self.relationships)

        task_suggestions = []

        # Generate milestone tasks
        if goal.milestones:
            for i, milestone in enumerate(goal.milestones):
                if not milestone.is_completed:
                    task = {
                        "title": f"Complete: {milestone.title}",
                        "description": milestone.description or "",
                        "fulfills_goal_uid": goal_uid,
                        "goal_progress_contribution": 100.0 / len(goal.milestones),
                        "priority": Priority.HIGH
                        if goal.days_remaining() < 30
                        else Priority.MEDIUM,
                        "tags": ["goal", f"milestone-{i + 1}"],
                    }
                    task_suggestions.append(task)

        # Generate knowledge acquisition tasks
        if rels.required_knowledge_uids:
            for knowledge_uid in rels.required_knowledge_uids:
                if knowledge_uid not in user_context.mastered_knowledge_uids:
                    task = {
                        "title": f"Learn: {knowledge_uid}",
                        "fulfills_goal_uid": goal_uid,
                        "applies_knowledge_uids": [knowledge_uid],
                        "knowledge_mastery_check": True,
                        "priority": Priority.HIGH,
                        "tags": ["learning", "goal"],
                    }
                    task_suggestions.append(task)

        # Generate habit reinforcement tasks
        if rels.supporting_habit_uids:
            for habit_uid in rels.supporting_habit_uids:
                if user_context.habit_streaks.get(habit_uid, 0) < 7:
                    task = {
                        "title": f"Strengthen habit: {habit_uid}",
                        "reinforces_habit_uid": habit_uid,
                        "fulfills_goal_uid": goal_uid,
                        "habit_streak_maintainer": True,
                        "priority": Priority.MEDIUM,
                        "recurring": True,
                        "tags": ["habit", "goal"],
                    }
                    task_suggestions.append(task)

        self.logger.info(
            "Generated %d task suggestions for goal %s", len(task_suggestions), goal_uid
        )

        return Result.ok(task_suggestions)

    async def assess_goal_feasibility(
        self, goal: Goal, user_context: UserContext
    ) -> Result[GoalFeasibilityAssessment]:
        """
        Assess if a goal is feasible given user's context (orchestration method).

        Combines checks across:
        - Knowledge prerequisites
        - Habit support
        - Current workload
        """
        # GRAPH-NATIVE: Fetch goal relationships from graph
        rels = await GoalRelationships.fetch(goal.uid, self.relationships)

        # Mutable accumulation variables
        is_feasible_flag = True
        confidence_score = 0.8
        blockers_list: list[str] = []
        enablers_list: list[str] = []
        estimated_date = None

        # Check knowledge prerequisites (from graph relationships)
        if rels.required_knowledge_uids:
            missing = set(rels.required_knowledge_uids) - user_context.mastered_knowledge_uids
            if missing:
                blockers_list.append(f"Missing {len(missing)} knowledge prerequisites")
                is_feasible_flag = False
                confidence_score *= 0.5

        # Check habit support (from graph relationships)
        if rels.supporting_habit_uids:
            active_habits = [
                h for h in rels.supporting_habit_uids if h in user_context.active_habit_uids
            ]
            if len(active_habits) < len(rels.supporting_habit_uids) / 2:
                blockers_list.append("Insufficient habit support")
                confidence_score *= 0.7
            else:
                enablers_list.append(f"{len(active_habits)} supporting habits active")

        # Check workload
        current_workload = user_context.current_workload_score
        if current_workload > 0.8:
            blockers_list.append("Current workload too high")
            is_feasible_flag = False

        # Estimate completion
        if is_feasible_flag and goal.target_date:
            estimated_date = goal.target_date

        # Build immutable result using frozen dataclass
        assessment = GoalFeasibilityAssessment(
            is_feasible=is_feasible_flag,
            confidence=confidence_score,
            blockers=blockers_list,
            enablers=enablers_list,
            estimated_completion_date=estimated_date,
        )

        return Result.ok(assessment)

    # ========================================================================
    # QUERY LAYER
    # ========================================================================

    async def get_filtered_context(
        self,
        user_uid: str,
        status_filter: str = "active",
        sort_by: str = "target_date",
    ) -> "Result[ListContext]":
        """Get filtered and sorted goals with pre-filter stats.

        Stats via Cypher COUNT (no entity deserialization).
        Status filter pushed to Cypher WHERE (not Python post-filter).
        """
        import asyncio

        stats_result, entities_result = await asyncio.gather(
            self.core.get_stats_for_user(user_uid),
            self.core.get_for_user_filtered(user_uid, status_filter),
        )
        if stats_result.is_error:
            return stats_result
        if entities_result.is_error:
            return entities_result
        sorted_goals = _apply_goal_sort(entities_result.value, sort_by)
        return Result.ok({"entities": sorted_goals, "stats": stats_result.value})

    # Note: Status operations (activate_goal, pause_goal, complete_goal, archive_goal)
    # and Search operations (list_goal_categories, get_goals_by_status, search_goals, etc.)
    # delegated via explicit method below.
