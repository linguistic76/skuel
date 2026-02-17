"""
Goals Learning Service
======================

Handles goal-learning path integration and knowledge-aware operations.

Responsibilities:
- Create goals with learning integration
- Assess learning alignment
- Suggest learning-aligned goals
- Track learning contributions to goals
- Identify goals needing habits or blocked by knowledge
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.events import GoalCreated, publish_event
from core.models.enums import Domain, KuStatus
from core.models.goal.goal_request import GoalCreateRequest
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.ku.lp_position import LpPosition
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.goals_types import GoalLearningProgress, PathProgressData
from core.services.infrastructure import LearningAlignmentHelper
from core.services.protocols.domain_protocols import GoalsOperations
from core.services.user import UserContext
from core.utils.dto_helpers import to_domain_model
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.relationships import UnifiedRelationshipService


class GoalsLearningService(BaseService[GoalsOperations, Ku]):
    """
    Learning path integration service for goals.

    Handles:
    - Creating goals with learning context
    - Assessing learning alignment
    - Suggesting learning-aligned goals
    - Tracking learning contributions
    - Context-aware habit and knowledge checks


    Source Tag: "goals_learning_service_explicit"
    - Format: "goals_learning_service_explicit" for user-created relationships
    - Format: "goals_learning_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from goals_learning metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=KuDTO,
        model_class=Ku,
        domain_name="goals",
        date_field="target_date",
        completed_statuses=(KuStatus.COMPLETED.value,),
    )

    def __init__(
        self,
        backend: GoalsOperations,
        event_bus=None,
        relationships_service: "UnifiedRelationshipService | None" = None,
    ) -> None:
        """
        Initialize goals learning service.

        Args:
            backend: Protocol-based backend for goal operations,
            event_bus: Event bus for publishing domain events (optional)
            relationships_service: Service for fetching goal relationships

        Note:
            Context invalidation now happens via event-driven architecture.
            GoalCreated events trigger user_service.invalidate_context() in bootstrap.
        """
        super().__init__(backend, "goals.learning")
        self.event_bus = event_bus
        self.relationships = relationships_service  # GRAPH-NATIVE: For fetching goal relationships

        # Initialize LearningAlignmentHelper for learning operations (Phase 4)
        self.learning_helper = LearningAlignmentHelper[Ku, KuDTO, GoalCreateRequest](
            service=self,
            backend_get_method="get_goal",
            backend_get_user_method="get_user_goals",
            backend_create_method="create_goal",
            dto_class=KuDTO,
            model_class=Ku,
            domain=Domain.GOALS,
            entity_name="goal",
        )

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Goal entities."""
        return "Ku"

    # ========================================================================
    # LEARNING-AWARE GOAL CREATION
    # ========================================================================

    async def create_goal_with_learning_integration(
        self, goal_request: GoalCreateRequest, learning_position: LpPosition | None = None
    ) -> Result[Ku]:
        """
        Create a goal integrated with user's learning path progression.

        This method applies knowledge-first thinking: How does the user's learning
        path position frame this goal creation?

        Args:
            goal_request: Goal creation request,
            learning_position: User's learning path position context

        Returns:
            Result containing created Goal with learning path integration
        """
        # Use LearningAlignmentHelper (Phase 4 consolidation)
        result = await self.learning_helper.create_with_learning_alignment(
            request=goal_request, learning_position=learning_position
        )

        # Publish GoalCreated event
        if result.is_ok:
            goal = result.value
            event = GoalCreated(
                goal_uid=goal.uid,
                user_uid=goal.user_uid,
                title=goal.title,
                domain=goal.domain.value,
                target_date=goal.target_date,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    # ========================================================================
    # LEARNING ALIGNMENT ASSESSMENT
    # ========================================================================

    async def assess_goal_learning_alignment(
        self, goal_uid: str, learning_position: LpPosition
    ) -> Result[dict[str, Any]]:
        """
        Assess how well a goal aligns with current learning path progression.

        Args:
            goal_uid: Goal to assess,
            learning_position: User's learning path position

        Returns:
            Result containing learning alignment assessment
        """
        # Use LearningAlignmentHelper (Phase 4 consolidation)
        return await self.learning_helper.assess_learning_alignment(
            entity_uid=goal_uid, learning_position=learning_position
        )

    # ========================================================================
    # LEARNING-ALIGNED GOAL SUGGESTIONS
    # ========================================================================

    async def suggest_learning_aligned_goals(
        self, learning_position: LpPosition, goal_domain: Domain | None = None
    ) -> Result[list[dict[str, Any]]]:
        """
        Suggest goals that align with current learning path progression.

        Args:
            learning_position: User's learning path position,
            goal_domain: Optional domain filter

        Returns:
            Result containing suggested goals with learning alignment
        """
        # Use LearningAlignmentHelper (Phase 4 consolidation)
        return await self.learning_helper.suggest_learning_aligned_entities(
            learning_position=learning_position, filter_param=goal_domain, max_suggestions=8
        )

    # ========================================================================
    # LEARNING-SUPPORTING GOALS
    # ========================================================================

    async def get_learning_supporting_goals(
        self, user_uid: str, learning_position: LpPosition
    ) -> Result[list[Ku]]:
        """
        Get existing goals that support current learning path progression.

        Args:
            user_uid: User identifier,
            learning_position: User's learning path position

        Returns:
            Result containing goals that support learning progression
        """
        # Use LearningAlignmentHelper (Phase 4 consolidation)
        return await self.learning_helper.get_learning_supporting_entities(
            user_uid=user_uid, learning_position=learning_position
        )

    # ========================================================================
    # LEARNING PROGRESS TRACKING
    # ========================================================================

    async def track_goal_learning_progress(
        self, goal_uid: str, learning_position: LpPosition
    ) -> Result[GoalLearningProgress]:
        """
        Track how goal progress relates to learning path advancement.

        Args:
            goal_uid: Goal to track,
            learning_position: User's learning path position

        Returns:
            Result containing learning progress tracking
        """
        # Get the goal
        goal_result = await self.backend.get_goal(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        goal = to_domain_model(goal_result.value, KuDTO, Ku)

        # Mutable accumulation variables
        supporting_paths_list: list[PathProgressData] = []
        next_actions_list: list[str] = []
        total_learning_alignment = 0.0
        path_count = 0

        # Assess learning contribution to goal progress
        for path in learning_position.active_paths:
            # Check if this path supports the goal
            path_support = 0.0
            goal_text = f"{goal.title} {goal.description}".lower()

            if path.name.lower() in goal_text:
                path_support += 0.5

            # NOTE: Knowledge alignment check removed - goal.linked_knowledge_uids
            # field doesn't exist (moved to graph relationships, graph-native migration)

            if path_support > 0.3:
                path_count += 1
                total_learning_alignment += path_support

                # Track path progress
                completed_steps = len(
                    [s for s in path.steps if s.uid in learning_position.completed_step_uids]
                )
                total_steps = len(path.steps)
                path_progress = completed_steps / total_steps if total_steps > 0 else 0.0

                # Build PathProgressData frozen dataclass
                path_data = PathProgressData(
                    path=path.name,
                    support_score=path_support,
                    progress=path_progress,
                    completed_steps=completed_steps,
                    total_steps=total_steps,
                )
                supporting_paths_list.append(path_data)

        # Calculate learning contribution
        learning_contribution_score = (
            total_learning_alignment / path_count if path_count > 0 else 0.0
        )

        # Generate next learning actions
        if learning_contribution_score > 0.5:
            next_actions_list.append("Continue current learning paths to advance goal")
        else:
            next_actions_list.append("Consider aligning goal with active learning paths")

        # Build immutable result using frozen dataclass
        progress = GoalLearningProgress(
            goal_uid=goal.uid,
            goal_title=goal.title,
            goal_progress=goal.progress_percentage,
            learning_contribution=learning_contribution_score,
            supporting_paths_progress=supporting_paths_list,
            knowledge_advancement=[],
            learning_milestones_achieved=[],
            next_learning_actions=next_actions_list,
        )

        return Result.ok(progress)

    # ========================================================================
    # CONTEXT-AWARE CHECKS
    # ========================================================================

    async def get_goals_needing_habits(self, user_context: UserContext) -> Result[list[Ku]]:
        """
        Get goals that need habit reinforcement based on context.

        Args:
            user_context: User's unified context

        Returns:
            Result containing goals needing habit support
        """
        goals_result = await self.backend.find_by(user_uid=user_context.user_uid)
        if goals_result.is_error:
            return goals_result

        # Convert to Goal domain models
        goals = []
        for goal_data in goals_result.value:
            goal = to_domain_model(goal_data, KuDTO, Ku)
            goals.append(goal)

        # GRAPH-NATIVE: Check each goal's supporting habits from relationships
        needing_habits = []
        if self.relationships:
            from core.services.goals.goal_relationships import GoalRelationships

            for goal in goals:
                rels = await GoalRelationships.fetch(goal.uid, self.relationships)
                # Check if has supporting habits AND any have weak streaks (< 7 days)
                if rels.supporting_habit_uids and any(
                    user_context.habit_streaks.get(habit_uid, 0) < 7
                    for habit_uid in rels.supporting_habit_uids
                ):
                    needing_habits.append(goal)

        return Result.ok(needing_habits)

    async def get_goals_blocked_by_knowledge(self, user_context: UserContext) -> Result[list[Ku]]:
        """
        Get goals blocked by missing knowledge prerequisites.

        Args:
            user_context: User's unified context

        Returns:
            Result containing goals blocked by knowledge gaps
        """
        goals_result = await self.backend.find_by(user_uid=user_context.user_uid)
        if goals_result.is_error:
            return goals_result

        # Convert to Goal domain models
        goals = []
        for goal_data in goals_result.value:
            goal = to_domain_model(goal_data, KuDTO, Ku)
            goals.append(goal)

        # GRAPH-NATIVE: Check each goal's required knowledge from relationships
        blocked_goals = []
        if self.relationships:
            from core.services.goals.goal_relationships import GoalRelationships

            for goal in goals:
                rels = await GoalRelationships.fetch(goal.uid, self.relationships)
                if rels.required_knowledge_uids:
                    missing = (
                        set(rels.required_knowledge_uids) - user_context.mastered_knowledge_uids
                    )
                    if missing:
                        blocked_goals.append(goal)

        return Result.ok(blocked_goals)
