"""
Habits Learning Service
========================

Handles habit-learning path integration and knowledge-aware operations.

Responsibilities:
- Learning-aligned habit creation
- Learning path habit suggestions
- Knowledge reinforcement tracking
- Learning impact assessment
- Habit-learning integration
"""

from typing import Any

from core.events import HabitCreated, publish_event
from core.models.enums import Domain, EntityStatus
from core.models.enums import RecurrencePattern as HabitFrequency
from core.models.enums.habit_enums import HabitCategory
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.models.habit.habit_request import HabitCreateRequest
from core.models.pathways.lp_position import LpPosition
from core.models.type_hints import EntityUID, UserUID
from core.ports.domain_protocols import HabitsOperations
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.infrastructure import LearningAlignmentBridge
from core.services.user import UserContext
from core.utils.dto_helpers import to_domain_model
from core.utils.result_simplified import Result


class HabitsLearningService(BaseService[HabitsOperations, Habit]):
    """
    Learning path integration service for habits.

    Handles:
    - Creating habits aligned with learning paths
    - Suggesting learning-supporting habits
    - Assessing learning impact of habits
    - Tracking knowledge reinforcement
    """

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=HabitDTO,
        model_class=Habit,
        entity_label="Entity",
        domain_name="habits",
        date_field="created_at",
        completed_statuses=(EntityStatus.ARCHIVED.value,),
    )

    def __init__(
        self, backend: HabitsOperations, event_bus=None, relationship_service=None
    ) -> None:
        """
        Initialize habits learning service.

        Args:
            backend: Protocol-based backend for habit operations,
            event_bus: Event bus for publishing domain events (optional)
            relationship_service: Relationship service (accepted for factory uniformity, not used)

        Note:
            Context invalidation now happens via event-driven architecture.
            HabitCreated events trigger user_service.invalidate_context() in bootstrap.
        """
        super().__init__(backend, "habits.learning")
        self.event_bus = event_bus

        # Initialize LearningAlignmentBridge for learning operations
        self.learning_helper = LearningAlignmentBridge[Habit, HabitDTO, HabitCreateRequest](
            service=self,
            backend_get=self.backend.get_habit,
            backend_get_user=self.backend.get_user_habits,
            backend_create=self.backend.create_habit,
            domain=Domain.HABITS,
            entity_name="habit",
        )

    # ========================================================================
    # LEARNING-AWARE HABIT OPERATIONS
    # ========================================================================

    async def get_learning_habits(self, user_context: UserContext) -> Result[list[Habit]]:
        """
        Get habits that support learning (reinforce knowledge).
        """
        learning_habits = []

        for habit_uid in user_context.active_habit_uids:
            habit_result = await self.backend.get_habit(habit_uid)
            if habit_result.is_ok:
                habit = to_domain_model(habit_result.value, HabitDTO, Habit)

                # GRAPH-NATIVE: Check if habit is learning-related
                # Category or PS link (LP reachable via PS->LP traversal).
                if (
                    habit.habit_category and habit.habit_category == HabitCategory.LEARNING
                ) or habit.source_path_step_uid is not None:
                    learning_habits.append(habit)

        return Result.ok(learning_habits)

    async def create_habit_from_learning_goal(  # skuel-lint: disable=SKUEL029 -- facade-delegated: habits_service awaits this via delegation (facade uniformity)
        self,
        knowledge_uid: str,
        user_context: UserContext,
        frequency: HabitFrequency = HabitFrequency.DAILY,
    ) -> Result[dict[str, Any]]:
        """
        Generate a habit suggestion to support learning a specific knowledge area.

        IMPORTANT - Caller Responsibility Pattern (Graph-Native):
        ====================================================
        This method returns a TEMPLATE dict, not a created Habit entity.
        Knowledge relationships are NOT included in the template because they
        must be created in the graph AFTER habit creation.

        To create a habit with knowledge links:
        1. Call HabitsService.create() with the returned template dict
        2. Call UnifiedRelationshipService.link_habit_to_knowledge(habit_uid, knowledge_uid)

        Example:
            # Step 1: Generate template
            template_result = await habits_learning_service.create_habit_from_learning_goal(
                knowledge_uid="ku.python_basics",
                user_context=context
            )
            habit_template = template_result.value

            # Step 2: Create habit
            habit_result = await habits_service.create(habit_template)
            habit_uid = habit_result.value.uid

            # Step 3: Link to knowledge (CALLER RESPONSIBILITY)
            await habits_relationship_service.link_habit_to_knowledge(
                habit_uid=habit_uid,
                knowledge_uid="ku.python_basics",
                skill_level="beginner",
                proficiency_gain_rate=0.1
            )

        Why this pattern?
        - GRAPH-NATIVE: Relationships stored in graph, not model fields
        - Template generation is separate from entity creation
        - Relationship creation requires both entities to exist first

        Args:
            knowledge_uid: UID of knowledge unit to practice,
            user_context: User's context for personalization,
            frequency: How often to practice (default: daily)

        Returns:
            Result[dict]: Habit template ready for HabitsService.create()
        """
        habit_template = {
            "name": f"Study {knowledge_uid}",
            "description": f"Regular practice to master {knowledge_uid}",
            "frequency": frequency,
            "duration_minutes": 30,
            # GRAPH-NATIVE: Knowledge relationships created via graph, not fields
            # Use UnifiedRelationshipService to link habit to knowledge after creation
            "category": "learning",  # Mark as learning habit
            "tags": ["learning", "study"],
        }

        # Check if user has related goals
        related_goals: list[str] = []
        for _goal_uid in user_context.active_goal_uids:
            # Would check if goal requires this knowledge
            pass

        if related_goals:
            habit_template["linked_goal_uids"] = related_goals

        return Result.ok(habit_template)

    # ========================================================================
    # LEARNING PATH ALIGNMENT
    # ========================================================================

    async def create_habit_with_learning_alignment(
        self, habit_request: HabitCreateRequest, learning_position: LpPosition | None = None
    ) -> Result[Habit]:
        """
        Create a habit aligned with user's learning path progression.

        This method applies knowledge-first thinking: How does the user's learning
        path position frame this habit creation?

        Args:
            habit_request: Habit creation request,
            learning_position: User's learning path position context

        Returns:
            Result containing created Habit with learning path alignment
        """
        # Use LearningAlignmentBridge (consolidation)
        result = await self.learning_helper.create_with_learning_alignment(
            request=habit_request, learning_position=learning_position
        )

        # Publish HabitCreated event
        if result.is_ok:
            habit = result.value
            event = HabitCreated(
                habit_uid=habit.uid,
                user_uid=habit.user_uid,
                title=habit.title,
                frequency=habit.recurrence_pattern or "daily",
                domain=None,  # Habit model doesn't have domain field
            )
            await publish_event(self.event_bus, event, self.logger)

            # Publish knowledge substance event: single-item for 1 KU, bulk for 2+
            if habit_request.linked_knowledge_uids:
                from core.events.knowledge_substance_events import (
                    KnowledgeBuiltIntoHabit,
                    KnowledgeBulkBuiltIntoHabit,
                )

                ku_uids = habit_request.linked_knowledge_uids
                if len(ku_uids) == 1:
                    knowledge_event: KnowledgeBuiltIntoHabit | KnowledgeBulkBuiltIntoHabit = (
                        KnowledgeBuiltIntoHabit(
                            knowledge_uid=ku_uids[0],
                            habit_uid=habit.uid,
                            user_uid=habit.user_uid,
                            habit_title=habit.title,
                            frequency=habit.recurrence_pattern,
                        )
                    )
                else:
                    knowledge_event = KnowledgeBulkBuiltIntoHabit(
                        knowledge_uids=tuple(ku_uids),
                        habit_uid=habit.uid,
                        user_uid=habit.user_uid,
                        habit_title=habit.title,
                        frequency=habit.recurrence_pattern,
                    )
                await publish_event(self.event_bus, knowledge_event, self.logger)

        return result

    async def suggest_learning_supporting_habits(
        self, learning_position: LpPosition, habit_category: str | None = None
    ) -> Result[list[dict[str, Any]]]:
        """
        Suggest habits that support current learning path progression.

        Args:
            learning_position: User's learning path position,
            habit_category: Optional category filter

        Returns:
            Result containing suggested habits with learning alignment
        """
        # Use LearningAlignmentBridge (consolidation)
        return await self.learning_helper.suggest_learning_aligned_entities(
            learning_position=learning_position, filter_param=habit_category, max_suggestions=12
        )

    async def get_learning_reinforcing_habits(
        self, user_uid: UserUID, learning_position: LpPosition
    ) -> Result[list[Habit]]:
        """
        Get existing habits that reinforce current learning paths.

        Args:
            user_uid: User identifier,
            learning_position: User's learning path position

        Returns:
            Result containing habits that support learning progression
        """
        # Use LearningAlignmentBridge (consolidation)
        return await self.learning_helper.get_learning_supporting_entities(
            user_uid=user_uid, learning_position=learning_position
        )

    async def assess_habit_learning_impact(
        self, habit_uid: str, learning_position: LpPosition
    ) -> Result[dict[str, Any]]:
        """
        Assess the learning impact of a specific habit.

        Args:
            habit_uid: Habit to assess,
            learning_position: User's learning path position

        Returns:
            Result containing learning impact assessment
        """
        # Use LearningAlignmentBridge (consolidation)
        return await self.learning_helper.assess_learning_alignment(
            entity_uid=EntityUID(habit_uid), learning_position=learning_position
        )
