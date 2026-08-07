"""
Orchestration Mixin — HabitsService
=====================================

Cross-domain graph relationship creation and multi-step orchestration.

Part of habits_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.habit.habit import Habit
    from core.models.habit.habit_request import HabitCreateRequest
    from core.services.user import UserContext


class _OrchestrationMixin:
    """
    Cross-domain graph relationship creation and multi-step orchestration for HabitsService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by HabitsService.__init__ / BaseService
    backend: Any
    core: Any
    completions: Any
    learning: Any
    relationships: Any
    goals_service: Any
    logger: Any

    # ========================================================================
    # ORCHESTRATION METHODS (cross-domain coordination)
    # ========================================================================

    async def complete_with_goal_impacts(
        self,
        habit_uid: str,
        user_uid: UserUID,
    ) -> Result[dict[str, Any]]:
        """
        Complete a habit and calculate goal impacts.

        Delegates streak/identity logic to HabitsCompletionService.record_completion()
        (no duplication). Then estimates goal strength deltas if goals_service is available.

        Returns Result with dict: {"habit": Habit, "goal_impacts": list[dict]}.
        """
        # 1. Ownership verification
        ownership_result = await self.core.verify_ownership(habit_uid, user_uid)
        if ownership_result.is_error:
            return Result.fail(ownership_result)

        # 2. Record completion — handles ALL streak/identity logic
        completion_result = await self.completions.record_completion(habit_uid, user_uid)
        if completion_result.is_error:
            return Result.fail(completion_result)

        # 3. Get updated habit
        habit_result = await self.core.get_habit(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result)
        updated_habit = habit_result.value

        # 4. Calculate goal impacts
        goal_impacts: list[dict[str, Any]] = []
        if self.goals_service:
            linked_goal_uids: list[str] = getattr(updated_habit, "linked_goal_uids", [])
            for goal_uid in linked_goal_uids:
                try:
                    goal_result = await self.goals_service.get_goal(goal_uid)
                    if goal_result.is_error:
                        continue
                    goal = goal_result.value
                    if goal is None:
                        continue

                    old_strength = goal.calculate_system_strength()
                    new_strength = goal.calculate_system_strength()
                    strength_delta = (new_strength - old_strength) * 100

                    goal_impacts.append(
                        {
                            "title": goal.title,
                            "system_strength_delta": round(strength_delta, 1),
                            "velocity_delta": 1,
                        }
                    )
                except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
                    self.logger.warning(f"Failed to calculate impact for goal {goal_uid}: {e}")

        return Result.ok({"habit": updated_habit, "goal_impacts": goal_impacts})

    async def create_with_goal_links(
        self,
        create_request: HabitCreateRequest,
        user_uid: UserUID,
        goal_essentiality: dict[str, str] | None = None,
    ) -> Result[Habit]:
        """
        Create a habit and optionally link it to goals with essentiality.

        Form parsing stays in the route handler; this method handles
        creation + cross-domain goal linking orchestration.
        """
        # 1. Create the habit
        result = await self.core.create_habit(create_request, user_uid)
        if result.is_error:
            return result

        habit = result.value

        # 2. Link to goals with essentiality
        if self.goals_service and goal_essentiality:
            for goal_uid, essentiality in goal_essentiality.items():
                try:
                    await self.goals_service.link_goal_to_habit(
                        goal_uid=goal_uid,
                        habit_uid=habit.uid,
                        essentiality=essentiality,
                    )
                except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
                    self.logger.warning(f"Failed to link habit to goal {goal_uid}: {e}")

        return Result.ok(habit)

    # ========================================================================
    # GRAPH RELATIONSHIPS - Delegate to UnifiedRelationshipService
    # ========================================================================

    async def create_user_habit_relationship(
        self, user_uid: UserUID, habit_uid: str, commitment_level: str = "active"
    ) -> Result[bool]:
        """Create User→Habit relationship in graph."""
        properties = (
            {"commitment_level": commitment_level} if commitment_level != "active" else None
        )
        return await self.relationships.create_user_relationship(user_uid, habit_uid, properties)

    async def link_habit_to_knowledge(
        self,
        habit_uid: str,
        knowledge_uid: str,
        skill_level: str = "beginner",
        proficiency_gain_rate: float = 0.1,
    ) -> Result[bool]:
        """Link habit to knowledge/skill it develops (``REINFORCES_KNOWLEDGE``)."""
        return await self.relationships.create_relationship(
            "knowledge",
            habit_uid,
            knowledge_uid,
            {"skill_level": skill_level, "proficiency_gain_rate": proficiency_gain_rate},
        )

    async def link_habit_to_principle(
        self, habit_uid: str, principle_uid: str, embodiment_strength: float = 1.0
    ) -> Result[bool]:
        """Link habit to principle/value it embodies (``EMBODIES_PRINCIPLE``)."""
        return await self.relationships.create_relationship(
            "principles",
            habit_uid,
            principle_uid,
            {"embodiment_strength": embodiment_strength},
        )

    async def get_skills_developed_by_habits(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """Get all skills/knowledge developed through user's habits."""
        # Get all user habits
        habits_result = await self.backend.list_by_user(user_uid=user_uid, limit=100)
        if habits_result.is_error:
            return Result.fail(habits_result)

        habits = habits_result.value
        if not habits:
            return Result.ok(
                {
                    "user_uid": user_uid,
                    "habit_count": 0,
                    "knowledge_uids": [],
                    "skills_count": 0,
                }
            )

        # Batch query: get all knowledge UIDs for all habits in ONE query
        habit_uids = [h.uid for h in habits]
        batch_result = await self.relationships.batch_get_related_uids("knowledge", habit_uids)

        # Collect all unique knowledge UIDs
        all_knowledge_uids: set[str] = set()
        if batch_result.is_ok:
            for uids in batch_result.value.values():
                all_knowledge_uids.update(uids)

        return Result.ok(
            {
                "user_uid": user_uid,
                "habit_count": len(habits),
                "knowledge_uids": list(all_knowledge_uids),
                "skills_count": len(all_knowledge_uids),
            }
        )

    async def create_semantic_skill_relationship(
        self,
        habit_uid: str,
        knowledge_uid: str,
        semantic_type: SemanticRelationshipType,
        confidence: float = 0.9,
        notes: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Create semantic relationship between habit and knowledge/skill."""
        return await self.relationships.create_semantic_relationship(
            habit_uid, knowledge_uid, semantic_type, confidence, notes
        )

    async def find_habits_developing_knowledge(
        self, knowledge_uid: str, min_confidence: float = 0.8
    ) -> Result[list[Habit]]:
        """Find habits that develop or reinforce specific knowledge/skill."""
        return await self.relationships.find_by_semantic_filter(
            target_uid=knowledge_uid,
            min_confidence=min_confidence,
            direction="incoming",
        )

    async def create_habit_with_context(
        self, habit_data: HabitCreateRequest, user_context: UserContext
    ) -> Result[Habit]:
        """
        Create a habit with full context awareness (orchestration method).

        This method orchestrates multiple checks:
        1. Validates knowledge prerequisites
        2. Links to supporting goals
        3. Sets up event scheduling
        4. Updates context after creation
        """
        # Check if habit supports any active goals
        supporting_goals = [
            goal_uid
            for goal_uid in user_context.active_goal_uids
            if habit_data.linked_goal_uids and goal_uid in habit_data.linked_goal_uids
        ]

        # Gates hold — the core primitive does everything else: builds the frozen
        # Habit, writes the request's link edges through the admission guard, and
        # publishes HabitCreated after they exist. (This step used to run through the
        # learning bridge's dict-based create, which persisted a corrupt uid-less
        # node and then errored — deleted 2026-08-06.)
        result = await self.core.create_habit(habit_data, user_context.user_uid)
        if result.is_error:
            return result

        # Note: User context invalidation now happens via event-driven architecture
        # HabitCreated event → invalidate_context_on_habit_event() → user_service.invalidate_context()

        habit = result.value
        # Get knowledge count from request data
        knowledge_count = (
            len(habit_data.linked_knowledge_uids) if habit_data.linked_knowledge_uids else 0
        )
        self.logger.info(
            "Created habit %s supporting %d goals, reinforcing %d knowledge items",
            habit.uid,
            len(supporting_goals),
            knowledge_count,
        )

        return Result.ok(habit)
