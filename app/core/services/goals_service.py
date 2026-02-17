"""
Enhanced Goals Service - Facade Pattern
========================================

Goals service facade that delegates to specialized sub-services.
This service provides a unified interface while maintaining clean separation of concerns.

Version: 7.0.0
- v7.0.0: Added GoalsSchedulingService for capacity and schedule management (January 19, 2026)
- v6.1.0: Added GoalsSearchService for search/discovery (November 28, 2025)
- v6.0.0: Facade pattern implementation with 5 specialized sub-services (October 13, 2025)
- v5.0.0: Phase 1-4 integration with pure Cypher graph intelligence (October 3, 2025)
- v4.0.0: Enhanced with learning integration and UserContext awareness
- v3.0.0: Base implementation with protocol interfaces

Sub-Services:
- GoalsCoreService: CRUD operations
- GoalsSearchService: Search and discovery (DomainSearchOperations[Goal] protocol)
- GoalsProgressService: Progress tracking and milestones
- GoalsLearningService: Learning path integration
- GoalsSchedulingService: Capacity management and schedule optimization (January 2026)
- UnifiedRelationshipService (GOALS_CONFIG): Graph relationships and cross-domain links
- GoalsIntelligenceService: pure Cypher analytics
- GoalsRecommendationService: Intelligent goal recommendations (Phase 4 event-driven)

Architecture: Zero breaking changes - all existing code continues to work unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums import KuStatus, Priority
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
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
from core.services.mixins import (
    FacadeDelegationMixin,
    create_relationship_delegations,
    merge_delegations,
)
from core.services.protocols.domain_protocols import GoalsOperations

# Unified relationship service (replaces GoalsRelationshipService)
from core.services.relationships import UnifiedRelationshipService
from core.utils.activity_domain_config import create_common_sub_services
from core.utils.dto_helpers import to_domain_model
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.goal.goal_request import GoalCreateRequest
    from core.services.protocols.infrastructure_protocols import EventBusOperations
    from core.services.protocols.search_protocols import GoalsSearchOperations
    from core.services.user import UserContext


class GoalsService(FacadeDelegationMixin, BaseService[GoalsOperations, Ku]):
    """
    Goals service facade with specialized sub-services.

    This facade:
    1. Delegates to 8 specialized sub-services for core operations
    2. Uses FacadeDelegationMixin for ~40 auto-generated delegation methods
    3. Retains explicit methods for complex orchestration operations
    4. Provides clean separation of concerns

    Auto-Generated Delegations (via FacadeDelegationMixin):
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
    - Uses FacadeDelegationMixin for delegation (January 2026 Phase 3)
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    # ========================================================================
    # DOMAIN CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================
    # Facade services use same config as core/search sub-services
    _config = create_activity_domain_config(
        dto_class=KuDTO,
        model_class=Ku,
        domain_name="goals",
        date_field="target_date",
        completed_statuses=(KuStatus.COMPLETED.value, KuStatus.CANCELLED.value),
        category_field="domain",  # Goals use 'domain' field for categorization
    )

    # ========================================================================
    # DELEGATION SPECIFICATION (FacadeDelegationMixin)
    # ========================================================================
    _delegations = merge_delegations(
        # Core CRUD delegations
        {
            "get_goal": ("core", "get_goal"),
            "get_user_goals": ("core", "get_user_goals"),
            "get_user_items_in_range": ("core", "get_user_items_in_range"),
            "activate_goal": ("core", "activate_goal"),
            "pause_goal": ("core", "pause_goal"),
            "complete_goal": ("core", "complete_goal"),
            "archive_goal": ("core", "archive_goal"),
            "create_goal": ("core", "create_goal"),
        },
        # Progress delegations
        {
            "calculate_goal_progress_with_context": (
                "progress",
                "calculate_goal_progress_with_context",
            ),
            "complete_milestone": ("progress", "complete_milestone"),
            "update_goal_from_habit_progress": ("progress", "update_goal_from_habit_progress"),
            "update_goal_progress": ("progress", "update_goal_progress"),
            "get_goal_progress": ("progress", "get_goal_progress"),
            "create_goal_milestone": ("progress", "create_goal_milestone"),
            "get_goal_milestones": ("progress", "get_goal_milestones"),
        },
        # Learning delegations
        {
            "create_goal_with_learning_integration": (
                "learning",
                "create_goal_with_learning_integration",
            ),
            "assess_goal_learning_alignment": ("learning", "assess_goal_learning_alignment"),
            "suggest_learning_aligned_goals": ("learning", "suggest_learning_aligned_goals"),
            "get_learning_supporting_goals": ("learning", "get_learning_supporting_goals"),
            "track_goal_learning_progress": ("learning", "track_goal_learning_progress"),
            "get_goals_needing_habits": ("learning", "get_goals_needing_habits"),
            "get_goals_blocked_by_knowledge": ("learning", "get_goals_blocked_by_knowledge"),
        },
        # Relationship delegations (factory-generated)
        create_relationship_delegations("goal"),
        # Intelligence delegations
        {
            "get_goal_with_context": ("intelligence", "get_goal_with_context"),
            "get_goal_progress_dashboard": ("intelligence", "get_goal_progress_dashboard"),
            "get_goal_completion_forecast": ("intelligence", "get_goal_completion_forecast"),
            "get_goal_learning_requirements": ("intelligence", "get_goal_learning_requirements"),
        },
        # Search delegations
        {
            "list_goal_categories": ("search", "list_user_categories"),
            "list_all_goal_categories": ("search", "list_all_categories"),
            "get_goals_by_category": ("search", "get_by_category"),
            "get_goals_by_status": ("search", "get_by_status"),
            "search_goals": ("search", "search"),
            "get_goals_due_soon": ("search", "get_due_soon"),
            "get_overdue_goals": ("search", "get_overdue"),
            "get_goals_by_domain": ("search", "get_by_domain"),
            "get_prioritized_goals": ("search", "get_prioritized"),
        },
        # Scheduling delegations (January 2026)
        {
            "check_goal_capacity": ("scheduling", "check_goal_capacity"),
            "suggest_goal_timeline": ("scheduling", "suggest_goal_timeline"),
            "assess_goal_achievability": ("scheduling", "assess_goal_achievability"),
            "get_schedule_aware_next_goal": ("scheduling", "get_schedule_aware_next_goal"),
            "optimize_goal_sequencing": ("scheduling", "optimize_goal_sequencing"),
            "get_goal_load_by_timeframe": ("scheduling", "get_goal_load_by_timeframe"),
            "create_goal_with_scheduling_context": ("scheduling", "create_goal_with_context"),
            "create_goal_with_learning_scheduling": (
                "scheduling",
                "create_goal_with_learning_context",
            ),
        },
    )

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

        # Phase 4: Event-driven recommendation service
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
        return "Ku"

    # Note: Backend access uses inherited BaseService._backend property
    # Custom backend property removed November 2025 - was unnecessary indirection

    # ========================================================================
    # GRAPH RELATIONSHIPS - Delegate to UnifiedRelationshipService
    # ========================================================================
    # Note: Simple delegations (Core CRUD, Progress, Learning) auto-generated
    # by FacadeDelegationMixin via _delegations dict above.

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
    # by FacadeDelegationMixin via _delegations dict above.

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
    ) -> Result[list[Ku]]:
        """Find goals that require specific knowledge."""
        return await self.relationships.find_by_semantic_filter(
            target_uid=knowledge_uid, min_confidence=min_confidence, direction="incoming"
        )

    # ========================================================================
    # ORCHESTRATION METHODS - Remain in Facade
    # ========================================================================
    # Note: Intelligence delegations (get_goal_with_context, get_goal_progress_dashboard,
    # get_goal_completion_forecast, get_goal_learning_requirements) auto-generated
    # by FacadeDelegationMixin via _delegations dict above.

    async def create_goal_with_context(
        self, goal_data: GoalCreateRequest, user_context: UserContext
    ) -> Result[Ku]:
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

        goal = to_domain_model(goal_result.value, KuDTO, Ku)

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

    async def get_recommended_next_goals(
        self, _user_context: UserContext, _limit: int = 3
    ) -> Result[list[Ku]]:
        """
        Get recommended next goals based on user's context (orchestration method).

        This would integrate with a recommendation engine.
        For now, return empty list (placeholder for future implementation).
        """
        # This would integrate with a recommendation engine
        # For now, return empty list
        return Result.ok([])

    async def assess_goal_feasibility(
        self, goal: Ku, user_context: UserContext
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

    # Note: Status operations (activate_goal, pause_goal, complete_goal, archive_goal)
    # and Search operations (list_goal_categories, get_goals_by_status, search_goals, etc.)
    # auto-generated by FacadeDelegationMixin via _delegations dict above.
