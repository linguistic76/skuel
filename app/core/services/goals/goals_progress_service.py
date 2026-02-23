"""
Goals Progress Service
=======================

Handles goal progress tracking, milestones, and forecasting.

Responsibilities:
- Progress calculation with context awareness
- Milestone management and completion
- Habit-based progress updates
- Velocity metrics and forecasting
- Risk analysis and acceleration opportunities
"""

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.events import GoalAchieved, GoalMilestoneReached, GoalProgressUpdated, publish_event
from core.events.task_events import TaskCompleted
from core.models.enums import Domain, EntityStatus
from core.models.enums.ku_enums import MeasurementType
from core.models.graph_context import GraphContext
from core.models.goal.goal import Goal
from core.models.goal.goal_dto import GoalDTO
from core.ports.domain_protocols import GoalsOperations
from core.ports.query_types import GoalUpdatePayload
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.goals.goal_relationships import GoalRelationships
from core.services.infrastructure import ProgressCalculationHelper
from core.services.user import UserContext
from core.utils.dto_helpers import to_domain_model
from core.utils.result_simplified import Errors, Result

# Type alias for rich goal data from UserContext
RichGoalData = dict[str, Any]

if TYPE_CHECKING:
    from core.events.habit_events import HabitCompleted
    from core.services.relationships import UnifiedRelationshipService


class GoalsProgressService(BaseService[GoalsOperations, Goal]):
    """
    Goal progress tracking and milestone management service.

    Handles:
    - Progress calculation with multiple contribution factors
    - Milestone completion and tracking
    - Habit-based progress updates
    - Velocity metrics and completion forecasting


    Source Tag: "goals_progress_service_explicit"
    - Format: "goals_progress_service_explicit" for user-created relationships
    - Format: "goals_progress_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from goals_progress metadata
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
        dto_class=GoalDTO,
        model_class=Goal,
        domain_name="goals",
        date_field="target_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
        entity_label="Entity",
    )

    # Service name for hierarchical logging
    _service_name = "goals.progress"

    @property
    def entity_label(self) -> str:
        """Return the graph label for Ku entities."""
        return "Entity"

    def __init__(
        self,
        backend: GoalsOperations,
        event_bus=None,
        relationships_service: "UnifiedRelationshipService | None" = None,
    ) -> None:
        """
        Initialize goals progress service.

        Args:
            backend: Protocol-based backend for goal operations,
            event_bus: Event bus for publishing domain events (optional)
            relationships_service: Service for fetching goal relationships

        Note:
            Context invalidation now happens via event-driven architecture.
            Goal events trigger user_service.invalidate_context() in bootstrap.
        """
        super().__init__(backend)  # Uses _service_name class attribute
        self.event_bus = event_bus
        self.relationships = relationships_service  # GRAPH-NATIVE: For fetching goal relationships

    # ========================================================================
    # CONTEXT-FIRST PATTERN HELPERS (November 26, 2025)
    # ========================================================================
    #
    # These methods implement the Context-First Pattern:
    # - UserContext is THE source of truth for user state
    # - Services CONSUME context, they don't rebuild it
    # - Only query what context doesn't have
    #
    # Benefits:
    # - 2 queries → 1 query per progress calculation (when rich context available)
    # - Single source of truth (no race conditions)
    # - Architectural consistency
    #
    # ========================================================================

    def _get_goal_from_rich_context(self, goal_uid: str, user_context: UserContext) -> Goal | None:
        """
        Try to get Goal entity from UserContext rich data.

        Context-First Pattern: Use context data when available to avoid
        unnecessary Neo4j queries.

        Args:
            goal_uid: Goal identifier
            user_context: User's context (may contain rich goal data)

        Returns:
            Goal if found in rich context, None otherwise
        """
        if not user_context.active_goals_rich:
            return None

        for goal_data in user_context.active_goals_rich:
            goal_dict = goal_data.get("goal", {})
            if goal_dict.get("uid") == goal_uid:
                # Convert dict to Goal domain model
                return self._dict_to_goal(goal_dict)

        return None

    def _get_relationships_from_rich_context(
        self, goal_uid: str, user_context: UserContext
    ) -> GoalRelationships | None:
        """
        Try to get GoalRelationships from UserContext rich data.

        Context-First Pattern: Graph neighborhoods are often included in
        rich context from MEGA-QUERY.

        Args:
            goal_uid: Goal identifier
            user_context: User's context with potential graph neighborhoods

        Returns:
            GoalRelationships if found in rich context, None otherwise
        """
        if not user_context.active_goals_rich:
            return None

        for goal_data in user_context.active_goals_rich:
            goal_dict = goal_data.get("goal", {})
            if goal_dict.get("uid") == goal_uid:
                graph_ctx = goal_data.get("graph_context", {})
                if graph_ctx:
                    return GoalRelationships(
                        supporting_habit_uids=[
                            h.get("uid")
                            for h in graph_ctx.get("supporting_habits", [])
                            if h and h.get("uid")
                        ],
                        required_knowledge_uids=[
                            k.get("uid")
                            for k in graph_ctx.get("required_knowledge", [])
                            if k and k.get("uid")
                        ],
                        sub_goal_uids=[
                            g.get("uid")
                            for g in graph_ctx.get("sub_goals", [])
                            if g and g.get("uid")
                        ],
                        aligned_learning_path_uids=[
                            lp.get("uid")
                            for lp in graph_ctx.get("aligned_paths", [])
                            if lp and lp.get("uid")
                        ],
                        guiding_principle_uids=[
                            p.get("uid")
                            for p in graph_ctx.get("guiding_principles", [])
                            if p and p.get("uid")
                        ],
                    )
        return None

    def _dict_to_goal(self, goal_dict: dict[str, Any]) -> Goal:
        """
        Convert a goal dictionary from MEGA-QUERY to Goal domain model.

        Args:
            goal_dict: Dict with goal properties from Neo4j

        Returns:
            Goal domain model
        """
        # Parse date fields
        target_date = goal_dict.get("target_date")
        if target_date and isinstance(target_date, str):
            target_date = date.fromisoformat(target_date)
        elif target_date and not isinstance(target_date, date):
            target_date = (
                date(target_date.year, target_date.month, target_date.day) if target_date else None
            )

        completion_date = goal_dict.get("completion_date")
        if completion_date and isinstance(completion_date, str):
            completion_date = date.fromisoformat(completion_date)
        elif completion_date and not isinstance(completion_date, date):
            completion_date = (
                date(completion_date.year, completion_date.month, completion_date.day)
                if completion_date
                else None
            )

        # Parse datetime fields
        created_at = goal_dict.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = goal_dict.get("updated_at")
        if updated_at and isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        # Parse enums
        status_val = goal_dict.get("status", "active")
        status = EntityStatus(status_val) if isinstance(status_val, str) else status_val

        domain_val = goal_dict.get("domain")
        domain = Domain(domain_val) if domain_val and isinstance(domain_val, str) else domain_val

        measurement_val = goal_dict.get("measurement_type", "milestone")
        measurement_type = (
            MeasurementType(measurement_val)
            if isinstance(measurement_val, str)
            else measurement_val
        )

        # Convert milestones list to tuple for frozen dataclass
        milestones_list = goal_dict.get("milestones", [])
        milestones_tuple = (
            tuple(milestones_list) if isinstance(milestones_list, list) else milestones_list
        )

        return Goal(
            uid=goal_dict.get("uid", ""),
            user_uid=goal_dict.get("user_uid", ""),
            title=goal_dict.get("title", ""),
            description=goal_dict.get("description"),
            status=status,
            domain=domain,
            measurement_type=measurement_type,
            target_date=target_date,
            # NOTE: Goal uses 'achieved_date' not 'completion_date'
            achieved_date=goal_dict.get("achieved_date", goal_dict.get("completion_date")),
            progress_percentage=goal_dict.get("progress_percentage", 0.0),
            current_value=goal_dict.get("current_value", 0.0),
            target_value=goal_dict.get("target_value", 100.0),
            milestones=milestones_tuple,
            fulfills_goal_uid=goal_dict.get("parent_goal_uid"),
            created_at=created_at,
            updated_at=updated_at,
        )

    # ========================================================================
    # PROGRESS CALCULATION
    # ========================================================================

    async def calculate_goal_progress_with_context(
        self, goal_uid: str, user_context: UserContext
    ) -> Result[dict[str, Any]]:
        """
        Calculate goal progress using full context awareness.

        Returns dict with:
        - progress_percentage: Overall progress
        - task_contribution: Progress from tasks
        - habit_contribution: Progress from habits
        - knowledge_completion: Ku prerequisites met
        - milestone_completion: Milestones completed

        **CONTEXT-FIRST PATTERN (November 26, 2025):**
        This method now uses the Context-First Pattern:
        - First tries to get goal from user_context.active_goals_rich
        - First tries to get relationships from rich context graph_context
        - Only falls back to Neo4j queries if not in context
        - Reduces from 2 queries to 0 when context is available

        Args:
            goal_uid: Goal identifier,
            user_context: User's unified context

        Returns:
            Result containing progress breakdown dictionary
        """
        # CONTEXT-FIRST: Try to get goal from rich context before querying Neo4j
        goal = self._get_goal_from_rich_context(goal_uid, user_context)
        context_hit = goal is not None

        if goal is None:
            # Fallback: Query Neo4j directly
            goal_result = await self.backend.get_goal(goal_uid)
            if goal_result.is_error:
                return Result.fail(goal_result.expect_error())
            goal = to_domain_model(goal_result.value, GoalDTO, Goal)
            self.logger.debug(f"Goal {goal_uid} fetched from Neo4j (not in rich context)")
        else:
            self.logger.debug(f"Goal {goal_uid} found in rich context (no Neo4j query needed)")

        # CONTEXT-FIRST: Try to get relationships from rich context
        rels = self._get_relationships_from_rich_context(goal_uid, user_context)
        if rels is not None:
            self.logger.debug(
                f"Goal relationships from rich context: {len(rels.supporting_habit_uids)} habits"
            )
        else:
            # Fallback: Fetch relationships from graph
            if self.relationships:
                rels = await GoalRelationships.fetch(goal_uid, self.relationships)
                self.logger.debug("Goal relationships from Neo4j")

        # Log context efficiency
        if context_hit:
            self.logger.info(
                f"Context-first: Goal {goal_uid} progress calculation used rich context (saved queries)"
            )

        # Get goal tasks from context
        goal_tasks = list(user_context.tasks_by_goal.get(goal_uid, []))

        # Get supporting habit UIDs from relationships
        supporting_habit_uids = list(rels.supporting_habit_uids) if rels else []

        # Get required knowledge UIDs from relationships
        required_knowledge_uids = list(rels.required_knowledge_uids) if rels else []

        # Use ProgressCalculationHelper for unified calculation
        progress = ProgressCalculationHelper.calculate_full_progress(
            goal_tasks=goal_tasks,
            completed_task_uids=user_context.completed_task_uids,
            supporting_habit_uids=supporting_habit_uids,
            habit_streaks=user_context.habit_streaks,
            required_knowledge_uids=required_knowledge_uids,
            mastered_knowledge_uids=user_context.mastered_knowledge_uids,
            current_value=goal.current_value,
            target_value=goal.target_value,
            measurement_type=goal.measurement_type or "mixed",
            expected_progress=goal.expected_progress_percentage(),
        )

        return Result.ok(
            {
                "progress_percentage": progress.combined_progress,
                "task_contribution": progress.task_contribution,
                "habit_contribution": progress.habit_contribution,
                "knowledge_completion": progress.knowledge_completion,
                "milestone_completion": progress.milestone_completion,
                "is_on_track": progress.is_on_track,
                "days_remaining": goal.days_remaining(),
            }
        )

    # ========================================================================
    # MILESTONE MANAGEMENT
    # ========================================================================

    async def complete_milestone(
        self, goal_uid: str, milestone_index: int, user_context: UserContext
    ) -> Result[Goal]:
        """
        Mark a milestone as complete and update goal progress.

        Args:
            goal_uid: Goal identifier,
            milestone_index: Index of milestone to complete,
            user_context: User's unified context

        Returns:
            Result containing updated Goal
        """
        goal_result = await self.backend.get_goal(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        goal = to_domain_model(goal_result.value, GoalDTO, Goal)

        if not goal.milestones or milestone_index >= len(goal.milestones):
            return Result.fail(
                Errors.validation(
                    message=f"Milestone index {milestone_index} is out of range",
                    field="milestone_index",
                    value=milestone_index,
                    user_message=f"Please provide a valid milestone index (0-{len(goal.milestones) - 1 if goal.milestones else 0})",
                )
            )

        # Update milestone (Milestone is a frozen dataclass)
        from dataclasses import replace

        updated_milestones = list(goal.milestones)
        updated_milestones[milestone_index] = replace(
            updated_milestones[milestone_index], is_completed=True, achieved_date=date.today()
        )

        # Calculate new progress
        completed_count = sum(1 for m in updated_milestones if m.is_completed)
        new_progress = (completed_count / len(updated_milestones)) * 100

        # Update goal
        updates: GoalUpdatePayload = {
            "milestones": updated_milestones,
            "progress_percentage": new_progress,
            "current_value": completed_count,
        }

        # Check if goal is complete
        if completed_count == len(updated_milestones):
            updates["status"] = EntityStatus.COMPLETED
            updates["completion_date"] = date.today()

        update_result = await self.backend.update_goal(goal_uid, updates)
        if update_result.is_error:
            return Result.fail(update_result.expect_error())

        # Context invalidation happens via GoalMilestoneReached/GoalAchieved events (event-driven architecture)
        # Event handlers in bootstrap will call user_service.invalidate_context()

        updated_goal = to_domain_model(update_result.value, GoalDTO, Goal)

        self.logger.info(f"Completed milestone {milestone_index} for goal {goal_uid}")

        # Publish GoalMilestoneReached event
        # Calculate milestone percentage (e.g., milestone 0 of 4 = 0.25, milestone 2 of 4 = 0.75)
        milestone_percentage = (milestone_index + 1) / len(updated_milestones)
        milestone_event = GoalMilestoneReached(
            goal_uid=goal_uid,
            user_uid=user_context.user_uid,
            milestone_percentage=milestone_percentage,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, milestone_event, self.logger)

        # Publish GoalAchieved event if goal is complete
        if completed_count == len(updated_milestones):
            achieved_event = GoalAchieved(
                goal_uid=goal_uid,
                user_uid=user_context.user_uid,
                occurred_at=datetime.now(),
                actual_duration_days=(date.today() - goal.created_at.date()).days
                if goal.created_at
                else None,
                completed_ahead_of_schedule=goal.target_date and date.today() < goal.target_date
                if goal.target_date
                else False,
            )
            await publish_event(self.event_bus, achieved_event, self.logger)

        return Result.ok(updated_goal)

    # ========================================================================
    # HABIT INTEGRATION
    # ========================================================================

    async def update_goal_from_habit_progress(
        self, goal_uid: str, habit_uid: str, new_streak: int
    ) -> Result[Goal]:
        """
        Update goal progress based on habit streak changes.

        Args:
            goal_uid: Goal identifier,
            habit_uid: Habit that was updated,
            new_streak: New streak count for the habit

        Returns:
            Result containing updated Goal (or unchanged if not habit-based)
        """
        goal_result = await self.backend.get_goal(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        goal = to_domain_model(goal_result.value, GoalDTO, Goal)

        # GRAPH-NATIVE: Fetch relationships from graph
        rels = None
        if self.relationships:
            from core.services.goals.goal_relationships import GoalRelationships

            rels = await GoalRelationships.fetch(goal_uid, self.relationships)

        # Only update if this is a habit-based goal
        if (
            not rels
            or goal.measurement_type != "habit_based"
            or habit_uid not in rels.supporting_habit_uids
        ):
            return Result.ok(goal)

        # Build habit streaks dict (use new_streak for the updated habit)
        habit_streaks = {
            h_uid: new_streak if h_uid == habit_uid else 0 for h_uid in rels.supporting_habit_uids
        }

        # Use ProgressCalculationHelper for habit contribution
        habit_result = ProgressCalculationHelper.calculate_habit_contribution(
            habit_uids=list(rels.supporting_habit_uids),
            habit_streaks=habit_streaks,
        )

        if habit_result.habit_count > 0:
            new_progress = habit_result.contribution * 100

            updates: GoalUpdatePayload = {
                "progress_percentage": new_progress,
                "current_value": new_progress,
            }

            # Check if goal is achieved
            if new_progress >= 100:
                updates["status"] = EntityStatus.COMPLETED
                updates["completion_date"] = date.today()

            update_result = await self.backend.update_goal(goal_uid, updates)
            if update_result.is_error:
                return Result.fail(update_result.expect_error())

            updated_goal = to_domain_model(update_result.value, GoalDTO, Goal)

            self.logger.info(
                f"Updated goal {goal_uid} progress from habit {habit_uid} to {new_progress:.1f}%"
            )

            # Publish GoalProgressUpdated event
            progress_event = GoalProgressUpdated(
                goal_uid=goal_uid,
                user_uid=goal.user_uid,
                occurred_at=datetime.now(),
                old_progress=goal.progress_percentage,
                new_progress=new_progress,
            )
            await publish_event(self.event_bus, progress_event, self.logger)

            # Publish GoalAchieved event if goal reached 100%
            if new_progress >= 100:
                achieved_event = GoalAchieved(
                    goal_uid=goal_uid,
                    user_uid=goal.user_uid,
                    occurred_at=datetime.now(),
                    actual_duration_days=(date.today() - goal.created_at.date()).days
                    if goal.created_at
                    else None,
                    completed_ahead_of_schedule=goal.target_date and date.today() < goal.target_date
                    if goal.target_date
                    else False,
                )
                await publish_event(self.event_bus, achieved_event, self.logger)

            return Result.ok(updated_goal)

        return Result.ok(goal)

    # ========================================================================
    # VELOCITY & FORECASTING HELPERS
    # ========================================================================

    def calculate_velocity_metrics(self, context: GraphContext, goal: Goal) -> dict[str, float]:
        """
        Calculate velocity metrics from graph context.

        Args:
            context: Graph context with supporting activities,
            goal: Goal object for progress calculation

        Returns:
            Dict containing:
            - total_tasks: Total task count
            - completed_tasks: Completed task count
            - task_completion_velocity: Tasks per week estimate
            - habit_consistency_score: 0-1 consistency score
            - current_progress_rate: Progress % per week estimate
        """
        # Extract data for velocity calculation
        supporting_tasks = context.get_nodes_by_domain(Domain.TASKS)
        supporting_habits = context.get_nodes_by_domain(Domain.HABITS)

        # Calculate velocity metrics (simple heuristics)
        total_tasks = len(supporting_tasks)
        completed_tasks = sum(
            1 for t in supporting_tasks if t.properties.get("status") in ["completed", "done"]
        )
        task_completion_velocity = (
            completed_tasks / 4.0 if completed_tasks > 0 else 0
        )  # per week estimate

        # Habit consistency
        habit_consistency_score = (
            sum(h.properties.get("consistency_score", 0.5) for h in supporting_habits)
            / len(supporting_habits)
            if supporting_habits
            else 0.5
        )

        # Progress rate (% per week estimate)
        current_progress_rate = (
            goal.progress_percentage / 4.0 if goal.progress_percentage > 0 else 0
        )

        return {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "task_completion_velocity": task_completion_velocity,
            "habit_consistency_score": habit_consistency_score,
            "current_progress_rate": current_progress_rate,
        }

    def generate_forecast(self, goal: Goal, current_progress_rate: float) -> dict[str, Any]:
        """
        Generate completion forecast based on current progress rate.

        Args:
            goal: Goal object with progress and target date,
            current_progress_rate: Current progress % per week

        Returns:
            Dict containing:
            - estimated_completion_date: Projected completion date
            - days_ahead_or_behind: Days ahead (positive) or behind (negative) schedule
            - completion_probability: Probability of completion (0-1)
        """
        estimated_completion_date = None
        days_ahead_or_behind = 0
        completion_probability = 0.5

        if goal.target_date and current_progress_rate > 0:
            remaining_progress = 100 - goal.progress_percentage
            weeks_to_complete = (
                remaining_progress / current_progress_rate if current_progress_rate > 0 else 999
            )
            days_to_complete = int(weeks_to_complete * 7)
            estimated_completion_date = date.today() + timedelta(days=days_to_complete)
            days_ahead_or_behind = (goal.target_date - estimated_completion_date).days

            # Completion probability based on current pace
            if days_ahead_or_behind > 0:
                completion_probability = min(0.95, 0.7 + (days_ahead_or_behind / 30.0) * 0.25)
            else:
                completion_probability = max(0.3, 0.7 - (abs(days_ahead_or_behind) / 30.0) * 0.4)

        return {
            "estimated_completion_date": estimated_completion_date,
            "days_ahead_or_behind": days_ahead_or_behind,
            "completion_probability": completion_probability,
        }

    def calculate_timeline_analysis(
        self, goal: Goal, velocity_metrics: dict[str, float], days_ahead_or_behind: int
    ) -> dict[str, Any]:
        """
        Calculate timeline analysis including required velocity and current pace.

        Args:
            goal: Goal object with target date,
            velocity_metrics: Velocity metrics from calculate_velocity_metrics(),
            days_ahead_or_behind: Days ahead (positive) or behind (negative)

        Returns:
            Dict containing:
            - target_date: Goal's target date
            - days_remaining: Days until target date
            - required_velocity: Tasks per week needed to complete on time
            - current_pace: "ahead", "on_track", or "behind"
            - confidence_level: Confidence in forecast (0-1)
        """
        total_tasks = velocity_metrics["total_tasks"]
        completed_tasks = velocity_metrics["completed_tasks"]
        habit_consistency_score = velocity_metrics["habit_consistency_score"]

        # Timeline analysis
        days_remaining = None
        required_velocity = 0
        if goal.target_date:
            days_remaining = (goal.target_date - date.today()).days
            if days_remaining > 0:
                remaining_tasks = total_tasks - completed_tasks
                required_velocity = (remaining_tasks / days_remaining) * 7  # tasks per week

        # Determine pace
        current_pace = "unknown"
        if days_ahead_or_behind > 7:
            current_pace = "ahead"
        elif days_ahead_or_behind >= -7:
            current_pace = "on_track"
        else:
            current_pace = "behind"

        # Confidence level
        confidence_level = habit_consistency_score * 0.6 + (0.4 if total_tasks > 3 else 0.2)

        return {
            "target_date": goal.target_date,
            "days_remaining": days_remaining,
            "required_velocity": required_velocity,
            "current_pace": current_pace,
            "confidence_level": confidence_level,
        }

    def identify_risk_factors(
        self, velocity_metrics: dict[str, float], context: GraphContext
    ) -> list[str]:
        """
        Identify risk factors that may prevent goal completion.

        Args:
            velocity_metrics: Velocity metrics from calculate_velocity_metrics(),
            context: Graph context with supporting activities

        Returns:
            List of risk factor descriptions
        """
        total_tasks = velocity_metrics["total_tasks"]
        habit_consistency_score = velocity_metrics["habit_consistency_score"]
        current_progress_rate = velocity_metrics["current_progress_rate"]

        supporting_habits = context.get_nodes_by_domain(Domain.HABITS)

        risk_factors = []
        if total_tasks < 3:
            risk_factors.append("Too few tasks defined - goal may lack concrete action plan")
        if habit_consistency_score < 0.5:
            risk_factors.append("Low habit consistency - supporting routines are inconsistent")
        if current_progress_rate < 2.0:
            risk_factors.append("Slow progress rate - may not complete on time")
        if len(supporting_habits) == 0:
            risk_factors.append("No supporting habits - progress relies entirely on ad-hoc tasks")

        return risk_factors

    def identify_acceleration_opportunities(
        self, velocity_metrics: dict[str, float], context: GraphContext, required_velocity: float
    ) -> list[str]:
        """
        Identify opportunities to accelerate goal progress.

        Args:
            velocity_metrics: Velocity metrics from calculate_velocity_metrics(),
            context: Graph context with supporting activities,
            required_velocity: Required tasks per week from timeline analysis

        Returns:
            List of acceleration opportunity descriptions
        """
        velocity_metrics["total_tasks"]
        completed_tasks = velocity_metrics["completed_tasks"]
        task_completion_velocity = velocity_metrics["task_completion_velocity"]

        supporting_habits = context.get_nodes_by_domain(Domain.HABITS)

        acceleration_opportunities = []
        if len(supporting_habits) < 2:
            acceleration_opportunities.append("Create daily/weekly habits to build momentum")
        if task_completion_velocity < required_velocity:
            acceleration_opportunities.append("Increase task completion rate to meet timeline")
        if completed_tasks == 0:
            acceleration_opportunities.append(
                "Start completing tasks to establish velocity baseline"
            )

        return acceleration_opportunities

    # ========================================================================
    # API SUPPORT METHODS (Phase 5: P5 Missing Methods)
    # ========================================================================

    async def update_goal_progress(
        self, uid: str, progress_value: float, notes: str = "", update_date: str | None = None
    ) -> Result[dict[str, Any]]:
        """
        Update goal progress manually.

        Args:
            uid: Goal UID
            progress_value: New progress value (0-100)
            notes: Optional progress notes
            update_date: Optional update date (ISO format)

        Returns:
            Result containing progress update confirmation with old/new values
        """
        # Get current goal
        goal_result = await self.backend.get_goal(uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        goal_dto = goal_result.value
        if not goal_dto:
            return Result.fail(Errors.not_found(resource="Goal", identifier=uid))

        goal = to_domain_model(goal_dto, GoalDTO, Goal)
        old_progress = goal.progress_percentage or 0.0

        # Update progress
        updates: GoalUpdatePayload = {
            "progress_percentage": progress_value,
            "current_value": progress_value,
        }

        if notes:
            # Append notes to metadata (access via DTO)
            metadata: dict[str, Any] = goal_dto.metadata or {}
            progress_notes = metadata.get("progress_notes", [])
            progress_notes.append(
                {"date": update_date or datetime.now().isoformat(), "notes": notes}
            )
            metadata["progress_notes"] = progress_notes
            updates["metadata"] = metadata

        update_result = await self.backend.update_goal(uid, updates)
        if update_result.is_error:
            return Result.fail(update_result.expect_error())

        # Publish GoalProgressUpdated event
        event = GoalProgressUpdated(
            goal_uid=uid,
            user_uid=goal.user_uid,
            occurred_at=datetime.now(),
            old_progress=old_progress,
            new_progress=progress_value,
            triggered_by_manual_update=True,
        )
        await publish_event(self.event_bus, event, self.logger)

        return Result.ok(
            {
                "goal_uid": uid,
                "old_progress": old_progress,
                "new_progress": progress_value,
                "notes": notes,
                "update_date": update_date or datetime.now().isoformat(),
            }
        )

    async def get_goal_progress(self, uid: str, period: str = "month") -> Result[dict[str, Any]]:
        """
        Get goal progress history for a period.

        Args:
            uid: Goal UID
            period: Time period ("week", "month", "quarter", "year", "all")

        Returns:
            Result containing progress history data
        """
        # Get goal (as DTO to access metadata)
        goal_result = await self.backend.get_goal(uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        goal_dto = goal_result.value
        if not goal_dto:
            return Result.fail(Errors.not_found(resource="Goal", identifier=uid))

        goal = to_domain_model(goal_dto, GoalDTO, Goal)

        # Extract progress notes from DTO metadata
        metadata: dict[str, Any] = goal_dto.metadata or {}
        progress_notes = metadata.get("progress_notes", [])

        # Calculate period filter
        cutoff_date = None
        if period == "week":
            cutoff_date = datetime.now() - timedelta(days=7)
        elif period == "month":
            cutoff_date = datetime.now() - timedelta(days=30)
        elif period == "quarter":
            cutoff_date = datetime.now() - timedelta(days=90)
        elif period == "year":
            cutoff_date = datetime.now() - timedelta(days=365)

        # Filter notes by period
        if cutoff_date and progress_notes:
            progress_notes = [
                note
                for note in progress_notes
                if datetime.fromisoformat(note["date"]) >= cutoff_date
            ]

        return Result.ok(
            {
                "goal_uid": uid,
                "current_progress": goal.progress_percentage,
                "target_value": goal.target_value,
                "period": period,
                "progress_history": progress_notes,
                "days_remaining": goal.days_remaining(),
                "is_on_track": goal.progress_percentage >= goal.expected_progress_percentage()
                if goal.target_date
                else None,
            }
        )

    async def create_goal_milestone(
        self, uid: str, milestone_title: str, target_date: str, description: str = ""
    ) -> Result[bool]:
        """
        Create a new milestone for a goal.

        Args:
            uid: Goal UID
            milestone_title: Milestone title
            target_date: Target completion date (ISO format)
            description: Optional milestone description

        Returns:
            Result containing True if milestone was created
        """
        from core.models.goal.milestone import Milestone

        # Get current goal
        goal_result = await self.backend.get_goal(uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        goal = to_domain_model(goal_result.value, GoalDTO, Goal)

        # Create new milestone with UID
        import uuid

        new_milestone = Milestone(
            uid=str(uuid.uuid4()),
            title=milestone_title,
            description=description or "",
            target_date=date.fromisoformat(target_date),
            is_completed=False,
        )

        # Add to milestones list
        milestones = list(goal.milestones) if goal.milestones else []
        milestones.append(new_milestone)

        # Update goal
        updates: GoalUpdatePayload = {"milestones": milestones}
        update_result = await self.backend.update_goal(uid, updates)

        if update_result.is_error:
            return Result.fail(update_result.expect_error())

        self.logger.info(f"Created milestone '{milestone_title}' for goal {uid}")
        return Result.ok(True)

    async def get_goal_milestones(self, uid: str) -> Result[list[dict[str, Any]]]:
        """
        Get all milestones for a goal.

        Args:
            uid: Goal UID

        Returns:
            Result containing list of milestone dictionaries
        """
        # Get goal
        goal_result = await self.backend.get_goal(uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        goal = to_domain_model(goal_result.value, GoalDTO, Goal)

        # Convert milestones to dicts
        milestones = []
        if goal.milestones:
            for milestone in goal.milestones:
                milestones.append(
                    {
                        "title": milestone.title,
                        "description": milestone.description,
                        "target_date": (
                            milestone.target_date.isoformat() if milestone.target_date else None
                        ),
                        "is_completed": milestone.is_completed,
                        "achieved_date": (
                            milestone.achieved_date.isoformat() if milestone.achieved_date else None
                        ),
                    }
                )

        return Result.ok(milestones)

    # ========================================================================
    # EVENT HANDLERS (Phase 4: Event-Driven Architecture)
    # ========================================================================

    async def handle_task_completed(self, event: TaskCompleted) -> None:
        """
        Update goal progress when a task is completed.

        This handler implements event-driven goal progress updates,
        eliminating direct dependency between TasksService and GoalsService.

        When a task is completed:
        1. Find all goals linked to this task
        2. For task-based or mixed goals, recalculate progress
        3. Update goal progress in database
        4. Publish GoalProgressUpdated event if progress changed

        Args:
            event: TaskCompleted event containing task_uid and user_uid

        Note:
            Errors are logged but not raised - progress updates are best-effort
            to prevent task completion from failing if goal update fails.
        """
        try:
            # Query Neo4j to find goals linked to this task
            # Pattern: (Goal)-[:SUPPORTS_GOAL]->(Task)
            self.logger.debug(
                f"Querying for goals linked to task {event.task_uid}, user {event.user_uid}"
            )

            query = """
            MATCH (goal:Entity {ku_type: 'goal'})-[:SUPPORTS_GOAL]->(task:Entity {uid: $task_uid, ku_type: 'task'})
            WHERE goal.user_uid = $user_uid
            RETURN goal.uid as goal_uid
            """

            result = await self.backend.execute_query(
                query, {"task_uid": event.task_uid, "user_uid": event.user_uid}
            )
            if result.is_error:
                self.logger.error(
                    f"Failed to query goals for task {event.task_uid}: {result.error}"
                )
                return

            records = result.value or []
            self.logger.debug(f"Found {len(records)} linked goals: {records}")
            goal_uids = [record["goal_uid"] for record in records]

            if not goal_uids:
                self.logger.debug(f"Task {event.task_uid} is not linked to any goals")
                return

            self.logger.info(
                f"Task {event.task_uid} completed - updating {len(goal_uids)} linked goals"
            )

            # Update progress for each linked goal
            for goal_uid in goal_uids:
                try:
                    await self._update_goal_from_task_completion(goal_uid, event.user_uid)
                except Exception as e:
                    self.logger.error(f"Failed to update goal {goal_uid} progress: {e}")
                    # Continue with other goals even if one fails

        except Exception as e:
            self.logger.error(f"Error handling task_completed event for task {event.task_uid}: {e}")

    async def _update_goal_from_task_completion(self, goal_uid: str, user_uid: str) -> None:
        """
        Internal helper to update a single goal's progress from task completion.

        Args:
            goal_uid: Goal to update
            user_uid: User who completed the task
        """
        # Get goal
        goal_result = await self.backend.get(goal_uid)
        if goal_result.is_error:
            self.logger.error(f"Failed to get goal {goal_uid}: {goal_result.error}")
            return

        if not goal_result.value:
            self.logger.error(f"Goal {goal_uid} not found")
            return

        goal = goal_result.value  # Already a Goal domain model from UniversalNeo4jBackend

        # Only update task-based or mixed goals
        if goal.measurement_type not in [MeasurementType.TASK_BASED, MeasurementType.MIXED]:
            self.logger.debug(
                f"Goal {goal_uid} is {goal.measurement_type}, skipping task-based progress update"
            )
            return

        # Query all tasks linked to this goal and count completed
        query = """
        MATCH (goal:Entity {uid: $goal_uid, ku_type: 'goal'})-[:SUPPORTS_GOAL]->(task:Entity {ku_type: 'task'})
        WHERE task.user_uid = $user_uid
        WITH count(task) as total_tasks
        MATCH (goal:Entity {uid: $goal_uid, ku_type: 'goal'})-[:SUPPORTS_GOAL]->(completed:Entity {ku_type: 'task'})
        WHERE completed.user_uid = $user_uid
          AND completed.status = 'completed'
        RETURN total_tasks, count(completed) as completed_tasks
        """

        result = await self.backend.execute_query(
            query, {"goal_uid": goal_uid, "user_uid": user_uid}
        )
        if result.is_error:
            self.logger.error(f"Failed to query tasks for goal {goal_uid}: {result.error}")
            return

        if not result.value:
            self.logger.warning(f"No task data found for goal {goal_uid}")
            return

        record = result.value[0]
        total_tasks = record.get("total_tasks", 0)
        completed_tasks = record.get("completed_tasks", 0)

        if total_tasks == 0:
            self.logger.debug(f"Goal {goal_uid} has no linked tasks")
            return

        # Calculate new progress percentage
        task_contribution = completed_tasks / total_tasks
        old_progress = goal.progress_percentage or 0.0

        # For task-based goals, progress is 100% task contribution
        # For mixed goals, task contribution is 30% of total progress
        if goal.measurement_type == MeasurementType.TASK_BASED:
            new_progress = task_contribution * 100
        else:  # mixed
            # Preserve non-task contributions and update task portion
            # This is simplified - ideally we'd recalculate all factors
            new_progress = (old_progress * 0.7) + (task_contribution * 30)

        # Only update if progress changed significantly (>0.1%)
        if abs(new_progress - old_progress) < 0.1:
            self.logger.debug(f"Goal {goal_uid} progress unchanged ({new_progress:.1f}%)")
            return

        # Update goal progress
        updates: dict[str, Any] = {
            "progress_percentage": new_progress,
            "current_value": new_progress,
        }

        # Check if goal is achieved
        if new_progress >= 100:
            updates["status"] = EntityStatus.COMPLETED.value
            updates["completion_date"] = date.today()

        update_result = await self.backend.update(goal_uid, updates)
        if update_result.is_error:
            self.logger.error(f"Failed to update goal {goal_uid}: {update_result.error}")
            return

        self.logger.info(
            f"Updated goal {goal_uid} progress: {old_progress:.1f}% → {new_progress:.1f}% "
            f"({completed_tasks}/{total_tasks} tasks)"
        )

        # Publish GoalProgressUpdated event
        progress_event = GoalProgressUpdated(
            goal_uid=goal_uid,
            user_uid=user_uid,
            occurred_at=datetime.now(),
            old_progress=old_progress,
            new_progress=new_progress,
            triggered_by_manual_update=False,  # Triggered by task completion
        )
        await publish_event(self.event_bus, progress_event, self.logger)

        # If goal was achieved, publish GoalAchieved event
        if new_progress >= 100 and old_progress < 100:
            achieved_event = GoalAchieved(
                goal_uid=goal_uid,
                user_uid=user_uid,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, achieved_event, self.logger)
            self.logger.info(f"🎉 Goal {goal_uid} achieved!")

    async def handle_habit_completed(self, event: "HabitCompleted") -> None:
        """
        Update goal progress when a habit is completed.

        This handler implements event-driven goal progress updates from habit completions,
        eliminating direct dependency between HabitsService and GoalsService.

        When a habit is completed:
        1. Find all goals linked to this habit via SUPPORTS_GOAL relationship
        2. For habit-based or mixed goals, recalculate progress based on streak
        3. Update goal progress in database
        4. Publish GoalProgressUpdated event if progress changed

        Args:
            event: HabitCompleted event containing habit_uid, user_uid, and current_streak

        Note:
            Errors are logged but not raised - progress updates are best-effort
            to prevent habit completion from failing if goal update fails.
        """
        try:
            # Query Neo4j to find goals linked to this habit
            # Pattern: (Goal)-[:SUPPORTS_GOAL]->(Habit)
            self.logger.debug(
                f"Querying for goals linked to habit {event.habit_uid}, user {event.user_uid}"
            )

            query = """
            MATCH (goal:Entity {ku_type: 'goal'})-[:SUPPORTS_GOAL]->(habit:Entity {uid: $habit_uid, ku_type: 'habit'})
            WHERE goal.user_uid = $user_uid
            RETURN goal.uid as goal_uid
            """

            result = await self.backend.execute_query(
                query, {"habit_uid": event.habit_uid, "user_uid": event.user_uid}
            )
            if result.is_error:
                self.logger.error(
                    f"Failed to query goals for habit {event.habit_uid}: {result.error}"
                )
                return

            records = result.value or []
            self.logger.debug(f"Found {len(records)} linked goals: {records}")
            goal_uids = [record["goal_uid"] for record in records]

            if not goal_uids:
                self.logger.debug(f"No goals linked to habit {event.habit_uid}")
                return

            # Update each linked goal
            for goal_uid in goal_uids:
                try:
                    await self._update_goal_from_habit_completion(
                        goal_uid=goal_uid,
                        user_uid=event.user_uid,
                        current_streak=event.current_streak,
                    )
                except Exception as e:
                    # Best-effort: Don't let one goal failure block others
                    self.logger.error(
                        f"Failed to update goal {goal_uid} from habit completion: {e}"
                    )

        except Exception as e:
            # Best-effort: Log error but don't raise (prevent habit completion failure)
            self.logger.error(f"Error handling habit_completed event: {e}")

    # FUTURE-IMPL: FUTURE-IMPL-008 - See docs/reference/DEFERRED_IMPLEMENTATIONS.md
    async def _update_goal_from_habit_completion(
        self, goal_uid: str, user_uid: str, current_streak: int
    ) -> None:
        """
        Internal helper to update a single goal's progress from habit completion.

        For habit-based goals, progress is calculated as:
        - Habit-based: (average_streak / target_value) * 100
        - Mixed: 30% habit contribution + 70% preserved existing progress

        Args:
            goal_uid: Goal to update
            user_uid: User owning the goal
            current_streak: Current streak length of the completed habit
        """
        # Get goal
        goal_result = await self.backend.get(goal_uid)
        if goal_result.is_error or not goal_result.value:
            self.logger.debug(f"Goal {goal_uid} not found, skipping update")
            return

        goal = goal_result.value

        # Only update habit-based or mixed goals
        if goal.measurement_type not in [MeasurementType.HABIT_BASED, MeasurementType.MIXED]:
            self.logger.debug(
                f"Goal {goal_uid} is {goal.measurement_type.value if goal.measurement_type else 'unknown'}, not habit-based/mixed - skipping"
            )
            return

        # Query all habits linked to this goal and their average streak
        query = """
        MATCH (goal:Entity {uid: $goal_uid, ku_type: 'goal'})-[:SUPPORTS_GOAL]->(habit:Entity {ku_type: 'habit'})
        WHERE habit.user_uid = $user_uid
        WITH count(habit) as total_habits
        MATCH (goal:Entity {uid: $goal_uid, ku_type: 'goal'})-[:SUPPORTS_GOAL]->(habit:Entity {ku_type: 'habit'})
        WHERE habit.user_uid = $user_uid
        RETURN total_habits, avg(COALESCE(habit.current_streak, 0)) as avg_streak
        """

        result = await self.backend.execute_query(
            query, {"goal_uid": goal_uid, "user_uid": user_uid}
        )
        if result.is_error:
            self.logger.error(f"Failed to query habits for goal {goal_uid}: {result.error}")
            return

        if not result.value or result.value[0].get("total_habits", 0) == 0:
            self.logger.debug(f"No habits found for goal {goal_uid}")
            return

        total_habits = result.value[0].get("total_habits", 0)
        avg_streak = result.value[0].get("avg_streak", 0)

        # Calculate progress based on goal type
        old_progress = goal.progress_percentage or 0.0
        target_value = goal.target_value or 100.0

        if goal.measurement_type == MeasurementType.HABIT_BASED:
            # For habit-based goals, progress = (avg_streak / target_value) * 100
            # Target value represents desired streak length
            habit_contribution = (avg_streak / target_value) if target_value > 0 else 0
            new_progress = min(habit_contribution * 100, 100.0)
        else:  # MeasurementType.MIXED
            # For mixed goals, habits contribute 30% to total progress
            habit_contribution = (avg_streak / target_value) if target_value > 0 else 0
            new_progress = (old_progress * 0.7) + (habit_contribution * 30)
            new_progress = min(new_progress, 100.0)

        # Skip update if progress unchanged
        if abs(new_progress - old_progress) < 0.01:
            self.logger.debug(
                f"Goal {goal_uid} progress unchanged ({old_progress:.1f}%), skipping update"
            )
            return

        # Update goal progress
        updates: dict[str, Any] = {
            "progress_percentage": new_progress,
            "current_value": new_progress,
        }

        # Check if goal is achieved
        if new_progress >= 100:
            updates["status"] = EntityStatus.COMPLETED.value
            updates["completion_date"] = date.today()

        update_result = await self.backend.update(goal_uid, updates)
        if update_result.is_error:
            self.logger.error(f"Failed to update goal {goal_uid}: {update_result.error}")
            return

        self.logger.info(
            f"Updated goal {goal_uid} progress: {old_progress:.1f}% → {new_progress:.1f}% "
            f"(avg_streak={avg_streak:.1f}, {total_habits} habits)"
        )

        # Publish GoalProgressUpdated event
        progress_event = GoalProgressUpdated(
            goal_uid=goal_uid,
            user_uid=user_uid,
            occurred_at=datetime.now(),
            old_progress=old_progress,
            new_progress=new_progress,
            triggered_by_habit_completion=True,  # Triggered by habit completion
            triggered_by_manual_update=False,
        )
        await publish_event(self.event_bus, progress_event, self.logger)

        # If goal was achieved, publish GoalAchieved event
        if new_progress >= 100 and old_progress < 100:
            achieved_event = GoalAchieved(
                goal_uid=goal_uid,
                user_uid=user_uid,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, achieved_event, self.logger)
            self.logger.info(f"🎉 Goal {goal_uid} achieved!")
