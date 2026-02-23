"""
Goals Scheduling Service - Goal Capacity and Schedule Management
================================================================

Extracted following TasksSchedulingService and HabitsSchedulingService patterns (January 2026).

**Purpose:** Smart goal scheduling, capacity management, timeline optimization,
and learning path integration for goal creation.

**Pattern Source:** HabitsSchedulingService (capacity) + TasksSchedulingService (context-aware)

**Key Differences from Other Domains:**
- Tasks: Time-bound, single-action focus
- Habits: Recurring, capacity measured in daily effort
- Events: Calendar-based, conflict detection
- Goals: Strategic, capacity measured in active goal count + complexity

**Responsibilities:**
- Goal capacity checking (can user handle another goal?)
- Context-validated goal creation
- Timeline suggestions based on velocity
- Goal sequencing optimization
- Schedule-aware recommendations
- Learning path integration

**Methods:**
- check_goal_capacity(): Can user handle another active goal?
- create_goal_with_context(): Context-validated goal creation
- create_goal_with_learning_context(): Create with learning alignment
- suggest_goal_timeline(): Recommend target date based on complexity
- adjust_target_date_from_velocity(): Recalibrate based on progress
- get_schedule_aware_next_goal(): Best goal to focus on now
- assess_goal_achievability(): Can goal be achieved by target date?
- get_goal_load_by_timeframe(): Distribution across timeframes
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.events import GoalCreated, publish_event
from core.models.enums import Domain, EntityStatus, Priority
from core.models.enums.ku_enums import GoalTimeframe, GoalType
from core.models.goal.goal_request import GoalCreateRequest
from core.models.goal.goal import Goal
from core.models.goal.goal_dto import GoalDTO
from core.ports.domain_protocols import GoalsOperations
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.infrastructure import LearningAlignmentHelper
from core.utils.decorators import with_error_handling
from core.utils.dto_helpers import to_domain_model
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import make_dict_value_getter

if TYPE_CHECKING:
    from core.models.curriculum.lp_position import LpPosition
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.services.goals.goals_progress_service import GoalsProgressService
    from core.services.user.unified_user_context import UserContext


# ============================================================================
# CONSTANTS
# ============================================================================

# Maximum recommended active goals by priority level
DEFAULT_MAX_ACTIVE_GOALS = 5  # Total active goals limit
DEFAULT_MAX_CRITICAL_GOALS = 1  # Only 1 CRITICAL goal at a time
DEFAULT_MAX_HIGH_GOALS = 2  # Up to 2 HIGH priority goals

# Complexity scoring by goal type
COMPLEXITY_BY_TYPE = {
    GoalType.OUTCOME: 3,  # Result-focused, moderate complexity
    GoalType.PROCESS: 2,  # Activity-focused, lower complexity
    GoalType.LEARNING: 3,  # Knowledge acquisition, moderate
    GoalType.PROJECT: 4,  # Complete project, higher complexity
    GoalType.MILESTONE: 2,  # Single checkpoint, lower complexity
    GoalType.MASTERY: 5,  # Master a skill, highest complexity
}

# Complexity scoring by timeframe
COMPLEXITY_BY_TIMEFRAME = {
    GoalTimeframe.DAILY: 1,  # Micro-goals
    GoalTimeframe.WEEKLY: 2,  # Short-term
    GoalTimeframe.MONTHLY: 3,  # Near-term
    GoalTimeframe.QUARTERLY: 4,  # Medium-term
    GoalTimeframe.YEARLY: 5,  # Long-term
    GoalTimeframe.MULTI_YEAR: 6,  # Strategic
}

# Days to suggest by timeframe (default durations)
DEFAULT_DAYS_BY_TIMEFRAME = {
    GoalTimeframe.DAILY: 1,
    GoalTimeframe.WEEKLY: 7,
    GoalTimeframe.MONTHLY: 30,
    GoalTimeframe.QUARTERLY: 90,
    GoalTimeframe.YEARLY: 365,
    GoalTimeframe.MULTI_YEAR: 730,
}


# ============================================================================
# RESULT DATACLASSES
# ============================================================================


@dataclass(frozen=True)
class GoalCapacityResult:
    """Result of goal capacity check."""

    user_uid: str
    current_goal_count: int
    active_goal_count: int
    max_active_goals: int
    remaining_capacity: int
    can_add_goal: bool
    current_complexity_load: float
    proposed_complexity: float
    load_percentage: float
    recommendations: tuple[str, ...]
    timeframe_distribution: dict[str, int]
    priority_distribution: dict[str, int]


@dataclass(frozen=True)
class TimelineSuggestion:
    """Suggested timeline for a goal."""

    suggested_target_date: date
    confidence: float  # 0.0-1.0
    rationale: str
    factors: tuple[str, ...]
    alternative_dates: tuple[date, ...]


@dataclass(frozen=True)
class AchievabilityResult:
    """Result of goal achievability assessment."""

    goal_uid: str
    is_achievable: bool
    confidence: float  # 0.0-1.0
    current_velocity: float  # Progress per day
    required_velocity: float  # Progress per day needed
    estimated_completion_date: date | None
    days_behind_or_ahead: int
    risk_factors: tuple[str, ...]
    recommendations: tuple[str, ...]


@dataclass(frozen=True)
class GoalSequenceItem:
    """A goal with its sequence position and reasoning."""

    goal_uid: str
    title: str
    suggested_order: int
    reasoning: str
    blocking_goals: tuple[str, ...]
    enabled_by: tuple[str, ...]


class GoalsSchedulingService(BaseService[GoalsOperations, Goal]):
    """
    Smart goal scheduling and capacity management service.

    **Unlike HabitsSchedulingService** which checks daily effort load,
    this service checks **goal complexity capacity** - can the user take on
    another goal without becoming overwhelmed?

    **Goal Load Capacity:**
    - Each goal has a complexity score based on type + timeframe
    - Users have a maximum number of active goals
    - Priority distribution matters (not too many CRITICAL/HIGH)
    - Formula: complexity = type_score * timeframe_multiplier

    **Timeline Intelligence:**
    - Suggests realistic target dates based on user history
    - Adjusts dates based on actual progress velocity
    - Sequences goals for optimal achievement

    SKUEL Architecture:
    - Uses BaseService for DTO conversion
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
        entity_label="Ku",
    )

    # Configure BaseService

    def __init__(
        self,
        backend: GoalsOperations,
        progress_service: GoalsProgressService | None = None,
        event_bus: EventBusOperations | None = None,
    ) -> None:
        """
        Initialize scheduling service.

        Args:
            backend: Protocol-based backend for goal operations
            progress_service: For analyzing velocity/progress (optional)
            event_bus: Event bus for publishing domain events (optional)
        """
        super().__init__(backend, "goals.scheduling")
        self.progress = progress_service
        self.event_bus = event_bus

        # Initialize LearningAlignmentHelper for curriculum integration
        self.learning_helper = LearningAlignmentHelper[Goal, GoalDTO, GoalCreateRequest](
            service=self,
            backend_get_method="get",
            backend_get_user_method="get_user_goals",
            backend_create_method="create_goal",
            dto_class=GoalDTO,
            model_class=Goal,
            domain=Domain.KNOWLEDGE,  # Default domain for goals
            entity_name="goal",
        )

    @property
    def entity_label(self) -> str:
        """Return the graph label for Ku entities."""
        return "Ku"

    # ========================================================================
    # CAPACITY MANAGEMENT
    # ========================================================================

    @with_error_handling("check_goal_capacity", error_type="database", uid_param="user_uid")
    async def check_goal_capacity(
        self,
        user_uid: str,
        proposed_type: GoalType = GoalType.OUTCOME,
        proposed_timeframe: GoalTimeframe = GoalTimeframe.QUARTERLY,
        proposed_priority: Priority = Priority.MEDIUM,
        max_active_goals: int = DEFAULT_MAX_ACTIVE_GOALS,
    ) -> Result[GoalCapacityResult]:
        """
        Check if user has capacity for another goal.

        Unlike habits which check daily effort load, goals check
        **complexity capacity** - can the user manage another goal
        without becoming overwhelmed?

        **Capacity Criteria:**
        - Total active goals count
        - Priority distribution (don't overload on CRITICAL/HIGH)
        - Complexity score (type * timeframe)

        Args:
            user_uid: User identifier
            proposed_type: Type of proposed new goal
            proposed_timeframe: Timeframe of proposed goal
            proposed_priority: Priority of proposed goal
            max_active_goals: Maximum active goals (default 5)

        Returns:
            Result containing capacity analysis
        """
        # Get user's goals
        result = await self.backend.find_by(user_uid=user_uid)
        if result.is_error:
            return Result.fail(result.expect_error())

        goals = result.value or []
        active_goals = [g for g in goals if g.status == EntityStatus.ACTIVE]

        # Calculate current complexity load
        current_load = sum(self._calculate_goal_complexity(g) for g in active_goals)

        # Calculate proposed goal complexity
        proposed_complexity = (
            COMPLEXITY_BY_TYPE.get(proposed_type, 3)
            * COMPLEXITY_BY_TIMEFRAME.get(proposed_timeframe, 3)
            / 10.0  # Normalize to 0-3 range
        )

        # Analyze priority distribution
        priority_distribution = self._analyze_priority_distribution(active_goals)

        # Calculate remaining capacity
        remaining_capacity = max_active_goals - len(active_goals)
        can_add = remaining_capacity > 0

        # Check priority constraints
        recommendations = []

        if proposed_priority == Priority.CRITICAL:
            critical_count = priority_distribution.get("critical", 0)
            if critical_count >= DEFAULT_MAX_CRITICAL_GOALS:
                can_add = False
                recommendations.append(
                    f"Already have {critical_count} CRITICAL goal(s). "
                    "Complete one before adding another CRITICAL goal."
                )

        if proposed_priority == Priority.HIGH:
            high_count = priority_distribution.get("high", 0)
            if high_count >= DEFAULT_MAX_HIGH_GOALS:
                recommendations.append(
                    f"Already have {high_count} HIGH priority goals. "
                    "Consider using MEDIUM priority or completing existing high-priority goals."
                )

        if not can_add:
            if remaining_capacity <= 0:
                recommendations.append(
                    f"Active goal limit reached ({len(active_goals)}/{max_active_goals}). "
                    "Complete or archive a goal before adding another."
                )

            # Suggest goals to complete/archive
            low_progress_goals = [g for g in active_goals if g.progress_percentage < 10]
            if low_progress_goals:
                stalled_names = [g.title[:30] for g in low_progress_goals[:3]]
                recommendations.append(
                    f"Consider archiving stalled goals: {', '.join(stalled_names)}"
                )
        else:
            headroom = remaining_capacity - 1
            if headroom < 2:
                recommendations.append(
                    f"Near capacity ({headroom} slot(s) remaining after addition). "
                    "Focus on completing existing goals."
                )
            else:
                recommendations.append("Good capacity for new goal.")

        # Analyze timeframe distribution
        timeframe_distribution = self._analyze_timeframe_distribution(active_goals)

        # Calculate load percentage
        max_complexity = max_active_goals * 3.0  # Max complexity per goal ~3
        load_percentage = round((current_load / max_complexity) * 100, 1) if max_complexity else 0

        return Result.ok(
            GoalCapacityResult(
                user_uid=user_uid,
                current_goal_count=len(goals),
                active_goal_count=len(active_goals),
                max_active_goals=max_active_goals,
                remaining_capacity=remaining_capacity,
                can_add_goal=can_add,
                current_complexity_load=round(current_load, 2),
                proposed_complexity=round(proposed_complexity, 2),
                load_percentage=load_percentage,
                recommendations=tuple(recommendations),
                timeframe_distribution=timeframe_distribution,
                priority_distribution=priority_distribution,
            )
        )

    def _calculate_goal_complexity(self, goal: Goal) -> float:
        """Calculate complexity score for a goal."""
        type_score = COMPLEXITY_BY_TYPE.get(goal.goal_type, 3)
        timeframe_score = COMPLEXITY_BY_TIMEFRAME.get(goal.timeframe, 3)
        return (type_score * timeframe_score) / 10.0  # Normalize

    def _analyze_priority_distribution(self, goals: list[Goal]) -> dict[str, int]:
        """Analyze how goals are distributed across priorities."""
        distribution = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for goal in goals:
            priority_key = goal.priority.lower() if goal.priority else "medium"
            if priority_key in distribution:
                distribution[priority_key] += 1
            else:
                distribution["medium"] += 1

        return distribution

    def _analyze_timeframe_distribution(self, goals: list[Goal]) -> dict[str, int]:
        """Analyze how goals are distributed across timeframes."""
        distribution = {tf.value: 0 for tf in GoalTimeframe}

        for goal in goals:
            timeframe_key = goal.timeframe.value if goal.timeframe else "quarterly"
            if timeframe_key in distribution:
                distribution[timeframe_key] += 1

        return distribution

    # ========================================================================
    # CONTEXT-AWARE CREATION
    # ========================================================================

    @with_error_handling("create_goal_with_context", error_type="database")
    async def create_goal_with_context(
        self,
        goal_data: GoalCreateRequest,
        user_context: UserContext,
        check_capacity: bool = True,
    ) -> Result[Goal]:
        """
        Create a goal with context validation and capacity checking.

        This method:
        1. Checks goal capacity (if enabled)
        2. Validates knowledge prerequisites
        3. Validates supporting habits
        4. Creates the goal
        5. Publishes GoalCreated event

        Args:
            goal_data: Goal creation request
            user_context: User context for validation
            check_capacity: Whether to enforce capacity limits

        Returns:
            Result containing created goal or error
        """
        # Step 1: Check capacity
        if check_capacity:
            capacity_result = await self.check_goal_capacity(
                user_uid=user_context.user_uid,
                proposed_type=goal_data.goal_type,
                proposed_timeframe=goal_data.timeframe,
                proposed_priority=goal_data.priority,
            )
            if capacity_result.is_error:
                return Result.fail(capacity_result.expect_error())

            capacity = capacity_result.value
            if not capacity.can_add_goal:
                return Result.fail(
                    Errors.validation(
                        message=(
                            f"Goal capacity exceeded. Active: {capacity.active_goal_count}, "
                            f"Max: {capacity.max_active_goals}. "
                            f"{capacity.recommendations[0] if capacity.recommendations else ''}"
                        ),
                        field="capacity",
                        value=str(capacity.load_percentage),
                    )
                )

        # Step 2: Validate knowledge prerequisites
        if goal_data.required_knowledge_uids:
            missing_prereqs = (
                set(goal_data.required_knowledge_uids) - user_context.mastered_knowledge_uids
            )
            if missing_prereqs:
                # Warning, not blocking - goals can have aspirational knowledge requirements
                self.logger.info(
                    f"Goal requires {len(missing_prereqs)} knowledge units user hasn't mastered yet"
                )

        # Step 3: Validate supporting habits (warning only)
        if goal_data.supporting_habit_uids:
            inactive_habits = [
                habit_uid
                for habit_uid in goal_data.supporting_habit_uids
                if habit_uid not in user_context.active_habit_uids
            ]
            if inactive_habits:
                self.logger.info(
                    f"Goal has {len(inactive_habits)} supporting habits that aren't active"
                )

        # Step 4: Create goal via backend
        request_dict = goal_data.model_dump()
        request_dict["user_uid"] = user_context.user_uid

        # Set default target date if not provided
        if not request_dict.get("target_date"):
            default_days = DEFAULT_DAYS_BY_TIMEFRAME.get(goal_data.timeframe, 90)
            request_dict["target_date"] = date.today() + timedelta(days=default_days)

        create_result = await self.backend.create_goal(request_dict)
        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        goal = self._to_domain_model(create_result.value, GoalDTO, Goal)

        # Step 5: Publish event
        event = GoalCreated(
            goal_uid=goal.uid,
            user_uid=goal.user_uid,
            title=goal.title,
            domain=goal.domain.value if goal.domain else None,
            target_date=datetime.combine(goal.target_date, datetime.min.time())
            if goal.target_date
            else None,
            occurred_at=datetime.now(),
            is_milestone=goal.goal_type == GoalType.MILESTONE,
            parent_goal_uid=goal.parent_goal_uid,
        )
        await publish_event(self.event_bus, event, self.logger)

        self.logger.info(
            f"Created goal '{goal.title}' for user {user_context.user_uid} "
            f"(type={goal.goal_type.value if goal.goal_type else 'unknown'}, timeframe={goal.timeframe.value if goal.timeframe else 'unknown'})"
        )

        return Result.ok(goal)

    @with_error_handling("create_goal_with_learning_context", error_type="database")
    async def create_goal_with_learning_context(
        self,
        goal_data: GoalCreateRequest,
        learning_position: LpPosition | None,
        user_context: UserContext,
    ) -> Result[Goal]:
        """
        Create a goal aligned with learning path.

        Combines capacity checking with learning alignment assessment.

        Args:
            goal_data: Goal creation request
            learning_position: User's learning path position
            user_context: User context for validation

        Returns:
            Result containing created goal with learning alignment
        """
        # Check capacity first
        capacity_result = await self.check_goal_capacity(
            user_uid=user_context.user_uid,
            proposed_type=goal_data.goal_type,
            proposed_timeframe=goal_data.timeframe,
            proposed_priority=goal_data.priority,
        )
        if capacity_result.is_error:
            return Result.fail(capacity_result.expect_error())

        if not capacity_result.value.can_add_goal:
            return Result.fail(
                Errors.validation(
                    message="Goal capacity exceeded. Archive or complete some goals first.",
                    field="capacity",
                )
            )

        # Use LearningAlignmentHelper for creation
        custom_fields = {"user_uid": user_context.user_uid}

        result = await self.learning_helper.create_with_learning_alignment(
            request=goal_data,
            learning_position=learning_position,
            context=user_context,
            custom_fields=custom_fields,
        )

        if result.is_ok:
            goal = result.value
            # Publish event
            event = GoalCreated(
                goal_uid=goal.uid,
                user_uid=goal.user_uid,
                title=goal.title,
                domain=goal.domain.value if goal.domain else None,
                target_date=datetime.combine(goal.target_date, datetime.min.time())
                if goal.target_date
                else None,
                occurred_at=datetime.now(),
                is_milestone=goal.goal_type == GoalType.MILESTONE,
                parent_goal_uid=goal.parent_goal_uid,
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    # ========================================================================
    # TIMELINE INTELLIGENCE
    # ========================================================================

    @with_error_handling("suggest_goal_timeline", error_type="database")
    async def suggest_goal_timeline(
        self,
        user_uid: str,
        goal_type: GoalType,
        timeframe: GoalTimeframe,
        complexity_factors: list[str] | None = None,
    ) -> Result[TimelineSuggestion]:
        """
        Suggest optimal target date for a goal.

        Based on:
        - Goal type and timeframe
        - User's historical completion rates
        - Current active goal load
        - Complexity factors

        Args:
            user_uid: User identifier
            goal_type: Type of goal
            timeframe: Desired timeframe
            complexity_factors: Additional complexity factors

        Returns:
            Result containing timeline suggestion
        """
        # Get default duration for timeframe
        default_days = DEFAULT_DAYS_BY_TIMEFRAME.get(timeframe, 90)

        # Get user's goal history for velocity estimation
        result = await self.backend.find_by(user_uid=user_uid)
        if result.is_error:
            # Fall back to defaults if can't get history
            return Result.ok(
                TimelineSuggestion(
                    suggested_target_date=date.today() + timedelta(days=default_days),
                    confidence=0.5,
                    rationale="Based on default timeframe duration (no history available)",
                    factors=("default_timeframe",),
                    alternative_dates=(
                        date.today() + timedelta(days=int(default_days * 0.8)),
                        date.today() + timedelta(days=int(default_days * 1.2)),
                    ),
                )
            )

        goals = result.value or []
        completed_goals = [g for g in goals if g.status == EntityStatus.COMPLETED]
        active_goals = [g for g in goals if g.status == EntityStatus.ACTIVE]

        factors = []
        adjustment = 1.0  # Multiplier for default duration

        # Factor 1: Historical completion rate for this type
        type_goals = [g for g in completed_goals if g.goal_type == goal_type]
        if len(type_goals) >= 3:
            # Calculate average actual vs planned duration
            durations = []
            for g in type_goals:
                if g.achieved_date and g.created_at:
                    actual_days = (g.achieved_date - g.created_at.date()).days
                    if g.target_date and g.created_at:
                        planned_days = (g.target_date - g.created_at.date()).days
                        if planned_days > 0:
                            durations.append(actual_days / planned_days)

            if durations:
                avg_ratio = sum(durations) / len(durations)
                adjustment *= avg_ratio
                factors.append(f"Historical completion ratio: {avg_ratio:.2f}x")

        # Factor 2: Current workload
        if len(active_goals) >= 4:
            adjustment *= 1.2  # Add 20% buffer for busy users
            factors.append("High active goal count (+20%)")
        elif len(active_goals) <= 1:
            adjustment *= 0.9  # Reduce for focused users
            factors.append("Low active goal count (-10%)")

        # Factor 3: Complexity factors
        if complexity_factors:
            complexity_adjustment = 1 + (len(complexity_factors) * 0.1)
            adjustment *= complexity_adjustment
            factors.append(f"Complexity factors: {', '.join(complexity_factors)}")

        # Factor 4: Goal type specific adjustments
        if goal_type == GoalType.MASTERY:
            adjustment *= 1.3  # Mastery takes longer
            factors.append("Mastery goal type (+30%)")
        elif goal_type == GoalType.MILESTONE:
            adjustment *= 0.8  # Milestones are focused
            factors.append("Milestone goal type (-20%)")

        # Calculate suggested date
        suggested_days = int(default_days * adjustment)
        suggested_date = date.today() + timedelta(days=suggested_days)

        # Calculate confidence based on data availability
        confidence = 0.5
        if len(type_goals) >= 5:
            confidence = 0.8
        elif len(type_goals) >= 3:
            confidence = 0.7
        elif len(completed_goals) >= 3:
            confidence = 0.6

        # Generate alternative dates
        alternative_dates = (
            date.today() + timedelta(days=int(suggested_days * 0.8)),  # Aggressive
            date.today() + timedelta(days=int(suggested_days * 1.2)),  # Conservative
        )

        rationale = (
            f"Based on {timeframe.value} timeframe ({default_days} days base) "
            f"with {adjustment:.2f}x adjustment from {len(factors)} factors"
        )

        return Result.ok(
            TimelineSuggestion(
                suggested_target_date=suggested_date,
                confidence=confidence,
                rationale=rationale,
                factors=tuple(factors) if factors else ("default_timeframe",),
                alternative_dates=alternative_dates,
            )
        )

    @with_error_handling("assess_goal_achievability", error_type="database", uid_param="goal_uid")
    async def assess_goal_achievability(
        self,
        goal_uid: str,
        user_context: UserContext,
    ) -> Result[AchievabilityResult]:
        """
        Assess if a goal is achievable by its target date.

        Uses progress velocity to determine if goal is on track
        and what adjustments might be needed.

        Args:
            goal_uid: Goal to assess
            user_context: User context

        Returns:
            Result containing achievability assessment
        """
        # Get the goal
        goal_result = await self.backend.get_goal(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())
        if not goal_result.value:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))

        goal = to_domain_model(goal_result.value, GoalDTO, Goal)

        # Calculate velocity
        current_progress = goal.progress_percentage
        days_elapsed = (date.today() - goal.created_at.date()).days if goal.created_at else 0

        current_velocity = current_progress / days_elapsed if days_elapsed > 0 else 0.0

        # Calculate required velocity
        days_remaining = goal.get_days_remaining() or 0
        remaining_progress = 100.0 - current_progress
        required_velocity = (
            remaining_progress / days_remaining if days_remaining > 0 else float("inf")
        )

        # Determine achievability
        risk_factors = []
        recommendations = []

        if days_remaining <= 0:
            is_achievable = current_progress >= 100
            if not is_achievable:
                risk_factors.append("Goal is overdue")
                recommendations.append("Consider extending target date or archiving")
        elif required_velocity <= 0:
            is_achievable = True
        else:
            velocity_ratio = (
                current_velocity / required_velocity if required_velocity > 0 else float("inf")
            )
            is_achievable = velocity_ratio >= 0.8  # 80% of required velocity

            if velocity_ratio < 0.5:
                risk_factors.append(f"Progress velocity ({current_velocity:.2f}%/day) is very low")
                recommendations.append("Break goal into smaller milestones")
                recommendations.append("Add more supporting habits or tasks")
            elif velocity_ratio < 0.8:
                risk_factors.append(
                    f"Progress velocity ({current_velocity:.2f}%/day) is below target"
                )
                recommendations.append("Increase focus on this goal")

        # Estimate completion date based on current velocity
        estimated_completion_date = None
        if current_velocity > 0:
            days_to_complete = remaining_progress / current_velocity
            estimated_completion_date = date.today() + timedelta(days=int(days_to_complete))

        # Calculate days ahead/behind
        days_diff = 0
        if estimated_completion_date and goal.target_date:
            days_diff = (goal.target_date - estimated_completion_date).days

        # Add context-based risk factors
        if goal_uid in user_context.at_risk_goals:
            risk_factors.append("Flagged as at-risk in user context")

        # Check supporting system
        if goal_uid in user_context.habits_by_goal:
            supporting_habits = user_context.habits_by_goal.get(goal_uid, [])
            if not supporting_habits:
                risk_factors.append("No supporting habits")
                recommendations.append("Link habits to support this goal")

        # Calculate confidence
        confidence = 0.8
        if len(risk_factors) >= 3:
            confidence = 0.4
        elif len(risk_factors) >= 2:
            confidence = 0.6
        elif len(risk_factors) >= 1:
            confidence = 0.7

        return Result.ok(
            AchievabilityResult(
                goal_uid=goal_uid,
                is_achievable=is_achievable,
                confidence=confidence,
                current_velocity=round(current_velocity, 3),
                required_velocity=round(required_velocity, 3)
                if required_velocity != float("inf")
                else 0.0,
                estimated_completion_date=estimated_completion_date,
                days_behind_or_ahead=days_diff,
                risk_factors=tuple(risk_factors),
                recommendations=tuple(recommendations),
            )
        )

    # ========================================================================
    # SCHEDULE-AWARE RECOMMENDATIONS
    # ========================================================================

    @with_error_handling("get_schedule_aware_next_goal", error_type="database")
    async def get_schedule_aware_next_goal(
        self,
        user_context: UserContext,
    ) -> Result[Goal | None]:
        """
        Get the best goal to focus on right now.

        Considers:
        - Goal urgency (days remaining)
        - Progress velocity
        - Current workload
        - Learning alignment

        Args:
            user_context: User context

        Returns:
            Result containing recommended goal or None
        """
        # Get active goals
        result = await self.backend.find_by(user_uid=user_context.user_uid)
        if result.is_error:
            return Result.fail(result.expect_error())

        goals = result.value or []
        active_goals = [g for g in goals if g.status == EntityStatus.ACTIVE]

        if not active_goals:
            return Result.ok(None)

        # Score each goal
        scored_goals: list[tuple[float, Goal]] = []

        for goal in active_goals:
            score = 0.0

            # Factor 1: Urgency (0-0.4)
            days_remaining = goal.get_days_remaining()
            if days_remaining is not None:
                if days_remaining <= 7:
                    score += 0.4  # Very urgent
                elif days_remaining <= 30:
                    score += 0.3
                elif days_remaining <= 90:
                    score += 0.2
                else:
                    score += 0.1

            # Factor 2: Priority (0-0.3)
            priority_scores = {
                Priority.CRITICAL: 0.3,
                Priority.HIGH: 0.25,
                Priority.MEDIUM: 0.15,
                Priority.LOW: 0.1,
            }
            score += priority_scores.get(Priority(goal.priority), 0.15) if goal.priority else 0.15

            # Factor 3: Progress momentum (0-0.2)
            progress = goal.progress_percentage
            if 30 <= progress <= 70:
                score += 0.2  # Mid-progress goals have momentum
            elif 70 < progress < 100:
                score += 0.15  # Near completion
            elif progress < 10:
                score += 0.05  # Just started

            # Factor 4: At-risk boost (0-0.1)
            if goal.uid in user_context.at_risk_goals:
                score += 0.1

            # Factor 5: Primary focus match
            if goal.uid == user_context.primary_goal_focus:
                score += 0.15

            scored_goals.append((score, goal))

        # Sort by score (highest first)
        scored_goals.sort(key=self._get_goal_score, reverse=True)

        if scored_goals:
            return Result.ok(scored_goals[0][1])

        return Result.ok(None)

    @staticmethod
    def _get_goal_score(scored_goal: tuple[float, Goal]) -> float:
        """Extract score from scored goal tuple (avoids lambda)."""
        return scored_goal[0]

    @with_error_handling("optimize_goal_sequencing", error_type="database")
    async def optimize_goal_sequencing(
        self,
        user_uid: str,
        goal_uids: list[str],
    ) -> Result[list[GoalSequenceItem]]:
        """
        Suggest optimal sequence for achieving multiple goals.

        Based on:
        - Dependencies (blocking relationships)
        - Urgency (target dates)
        - Complexity (easier wins first for momentum)

        Args:
            user_uid: User identifier
            goal_uids: Goals to sequence

        Returns:
            Result containing ordered sequence with reasoning
        """
        if not goal_uids:
            return Result.ok([])

        # Get all goals
        goals_dict: dict[str, Goal] = {}
        for uid in goal_uids:
            result = await self.backend.get_goal(uid)
            if result.is_ok and result.value:
                goals_dict[uid] = to_domain_model(result.value, GoalDTO, Goal)

        if not goals_dict:
            return Result.fail(Errors.not_found(resource="Goals", identifier=str(goal_uids)))

        # Score and sequence goals
        sequence: list[GoalSequenceItem] = []

        for uid, goal in goals_dict.items():
            # Determine blocking relationships
            blocking = []
            enabled_by = []

            # Parent goals block sub-goals (must complete parent first? No, usually opposite)
            # Sub-goals enable parent goals
            if goal.parent_goal_uid and goal.parent_goal_uid in goals_dict:
                enabled_by.append(goal.parent_goal_uid)

            # Build reasoning
            reasoning_parts = []

            # Urgency factor
            days = goal.get_days_remaining()
            if days is not None and days <= 30:
                reasoning_parts.append(f"Urgent ({days} days remaining)")

            # Progress factor
            if goal.progress_percentage >= 70:
                reasoning_parts.append("Near completion - quick win")
            elif goal.progress_percentage < 10:
                reasoning_parts.append("Just started - needs attention")

            # Complexity factor
            complexity = self._calculate_goal_complexity(goal)
            if complexity < 1.0:
                reasoning_parts.append("Low complexity - good for momentum")
            elif complexity > 2.0:
                reasoning_parts.append("High complexity - requires sustained focus")

            reasoning = "; ".join(reasoning_parts) if reasoning_parts else "Standard sequencing"

            sequence.append(
                GoalSequenceItem(
                    goal_uid=uid,
                    title=goal.title,
                    suggested_order=0,  # Will be set after sorting
                    reasoning=reasoning,
                    blocking_goals=tuple(blocking),
                    enabled_by=tuple(enabled_by),
                )
            )

        # Sort by: urgency (days remaining), then progress (near completion first), then complexity (easier first)
        def sort_key(item: GoalSequenceItem) -> tuple[int, float, float]:
            goal = goals_dict[item.goal_uid]
            days = goal.get_days_remaining() or 999
            progress_inv = 100 - goal.progress_percentage  # Lower = closer to completion
            complexity = self._calculate_goal_complexity(goal)
            return (days, progress_inv, complexity)

        sequence.sort(key=sort_key)

        # Update order numbers
        final_sequence = [
            GoalSequenceItem(
                goal_uid=item.goal_uid,
                title=item.title,
                suggested_order=i + 1,
                reasoning=item.reasoning,
                blocking_goals=item.blocking_goals,
                enabled_by=item.enabled_by,
            )
            for i, item in enumerate(sequence)
        ]

        self.logger.info(f"Sequenced {len(final_sequence)} goals for user {user_uid}")

        return Result.ok(final_sequence)

    # ========================================================================
    # LOAD ANALYSIS
    # ========================================================================

    @with_error_handling("get_goal_load_by_timeframe", error_type="database", uid_param="user_uid")
    async def get_goal_load_by_timeframe(
        self,
        user_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Calculate goal load by timeframe.

        Helps identify which timeframes are overloaded.

        Args:
            user_uid: User identifier

        Returns:
            Result containing load analysis by timeframe
        """
        result = await self.backend.find_by(user_uid=user_uid)
        if result.is_error:
            return Result.fail(result.expect_error())

        goals = result.value or []
        active_goals = [g for g in goals if g.status == EntityStatus.ACTIVE]

        # Calculate load by timeframe
        load_by_timeframe = {tf.value: 0.0 for tf in GoalTimeframe}
        count_by_timeframe = {tf.value: 0 for tf in GoalTimeframe}

        for goal in active_goals:
            timeframe_key = goal.timeframe.value if goal.timeframe else "quarterly"
            complexity = self._calculate_goal_complexity(goal)
            load_by_timeframe[timeframe_key] += complexity
            count_by_timeframe[timeframe_key] += 1

        # Find peak and light timeframes
        load_getter = make_dict_value_getter(load_by_timeframe)
        peak_timeframe = max(load_by_timeframe, key=load_getter)
        light_timeframe = min(
            (k for k, v in load_by_timeframe.items() if count_by_timeframe[k] > 0),
            key=load_getter,
            default=None,
        )

        total_load = sum(load_by_timeframe.values())
        num_timeframes = len(GoalTimeframe)
        avg_load = total_load / num_timeframes if num_timeframes > 0 else 0

        # Generate recommendations
        recommendations = self._generate_timeframe_recommendations(
            load_by_timeframe, count_by_timeframe, avg_load
        )

        return Result.ok(
            {
                "user_uid": user_uid,
                "active_goal_count": len(active_goals),
                "load_by_timeframe": load_by_timeframe,
                "count_by_timeframe": count_by_timeframe,
                "peak_timeframe": peak_timeframe,
                "peak_load": load_by_timeframe[peak_timeframe],
                "light_timeframe": light_timeframe,
                "light_load": load_by_timeframe[light_timeframe] if light_timeframe else 0,
                "average_load": round(avg_load, 2),
                "total_complexity_load": round(total_load, 2),
                "recommendations": recommendations,
            }
        )

    def _generate_timeframe_recommendations(
        self,
        load_by_timeframe: dict[str, float],
        count_by_timeframe: dict[str, int],
        avg_load: float,
    ) -> list[str]:
        """Generate recommendations based on timeframe distribution."""
        recommendations = []

        # Check for overloaded timeframes
        for timeframe, load in load_by_timeframe.items():
            if load > avg_load * 2.0 and count_by_timeframe[timeframe] > 0:
                recommendations.append(
                    f"{timeframe.capitalize()} timeframe is overloaded "
                    f"({count_by_timeframe[timeframe]} goals, {load:.1f} complexity). "
                    "Consider splitting or rescheduling goals."
                )

        # Check for neglected strategic timeframes
        if (
            count_by_timeframe.get("yearly", 0) == 0
            and count_by_timeframe.get("multi_year", 0) == 0
        ):
            recommendations.append(
                "No long-term goals defined. Consider adding yearly or multi-year strategic goals."
            )

        # Check for too many short-term goals
        short_term_count = count_by_timeframe.get("daily", 0) + count_by_timeframe.get("weekly", 0)
        if short_term_count > 5:
            recommendations.append(
                f"Many short-term goals ({short_term_count}). "
                "Consider consolidating into fewer, more focused objectives."
            )

        if not recommendations:
            recommendations.append("Goal timeframe distribution is well-balanced.")

        return recommendations
