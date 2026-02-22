"""
Habits Scheduling Service - Smart Habit Scheduling and Capacity Management
==========================================================================

Extracted following EventsSchedulingService pattern (January 2026).

**Purpose:** Smart habit scheduling, frequency optimization, capacity management,
and learning path integration.

**Pattern Source:** EventsSchedulingService + TasksSchedulingService

**Key Differences from Events:**
- Events: Calendar-based scheduling (time slots, conflict detection)
- Habits: Capacity-based scheduling (effort load, habit stacking)

**Responsibilities:**
- Context-validated habit creation
- Habit capacity checking (can user handle another habit?)
- Frequency optimization (best days/times from history)
- Habit stacking suggestions (James Clear pattern)
- Learning path integration for practice habits

**Methods:**
- create_habit_with_context(): Context-validated habit creation
- create_habit_with_learning_context(): Create from curriculum
- check_habit_capacity(): Can user handle another habit?
- optimize_habit_schedule(): Find best days/times
- suggest_habit_frequency(): Recommend frequency
- suggest_habit_stacking(): Find habits to stack
- create_habit_from_learning_step(): Generate practice habit
"""

from __future__ import annotations

from datetime import datetime
from operator import itemgetter
from typing import TYPE_CHECKING, Any

from core.events import HabitCreated, publish_event
from core.models.enums import Domain, EntityStatus, Priority, RecurrencePattern
from core.models.enums.ku_enums import HabitCategory, HabitDifficulty
from core.models.habit.habit_request import HabitCreateRequest
from core.models.ku.habit import Habit
from core.models.ku.ku_dto import KuDTO
from core.ports.domain_protocols import HabitsOperations
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.infrastructure import LearningAlignmentHelper
from core.utils.decorators import with_error_handling
from core.utils.dto_helpers import to_domain_model
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import make_dict_count_getter

if TYPE_CHECKING:
    from core.models.ku.lp_position import LpPosition
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.services.habits.habits_completion_service import HabitsCompletionService
    from core.services.user.unified_user_context import UserContext


# ============================================================================
# CONSTANTS
# ============================================================================

# Maximum daily habit effort load (sum of effort scores)
DEFAULT_MAX_DAILY_LOAD = 25

# Effort scores by difficulty
EFFORT_BY_DIFFICULTY = {
    HabitDifficulty.TRIVIAL: 1,
    HabitDifficulty.EASY: 2,
    HabitDifficulty.MODERATE: 3,
    HabitDifficulty.CHALLENGING: 4,
    HabitDifficulty.HARD: 5,
}

# Minimum streak to consider habit "established" (for stacking)
ESTABLISHED_STREAK_DAYS = 7


class HabitsSchedulingService(BaseService[HabitsOperations, Habit]):
    """
    Smart habit scheduling and capacity management service.

    **Unlike EventsSchedulingService** which checks calendar conflicts,
    this service checks **habit load capacity** - can the user take on
    more habits without becoming overwhelmed?

    **Habit Load Capacity:**
    - Each habit has an effort score based on difficulty + duration
    - Users have a maximum daily load capacity
    - New habits must fit within remaining capacity
    - Formula: remaining = max_load - sum(active_habit_efforts)

    **Habit Stacking (James Clear):**
    "After [CURRENT HABIT], I will [NEW HABIT]"
    - Find habits with same preferred_time
    - Suggest complementary category pairings
    - Build habit chains for better adherence

    SKUEL Architecture:
    - Uses BaseService for DTO conversion
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=KuDTO,
        model_class=Habit,
        entity_label="Ku",
        domain_name="habits",
        date_field="created_at",
        completed_statuses=(EntityStatus.ARCHIVED.value,),
    )

    # Configure BaseService

    def __init__(
        self,
        backend: HabitsOperations,
        completions_service: HabitsCompletionService | None = None,
        event_bus: EventBusOperations | None = None,
    ) -> None:
        """
        Initialize scheduling service.

        Args:
            backend: Protocol-based backend for habit operations
            completions_service: For analyzing completion patterns (optional)
            event_bus: Event bus for publishing domain events (optional)
        """
        super().__init__(backend, "habits.scheduling")
        self.completions = completions_service
        self.event_bus = event_bus

        # Initialize LearningAlignmentHelper for curriculum integration
        self.learning_helper = LearningAlignmentHelper[Habit, KuDTO, HabitCreateRequest](
            service=self,
            backend_get_method="get_habit",
            backend_get_user_method="get_user_habits",
            backend_create_method="create_habit",
            dto_class=KuDTO,
            model_class=Habit,
            domain=Domain.HABITS,
            entity_name="habit",
        )

    @property
    def entity_label(self) -> str:
        """Return the graph label for Habit entities."""
        return "Habit"

    # ========================================================================
    # CAPACITY MANAGEMENT
    # ========================================================================

    @with_error_handling("check_habit_capacity", error_type="database", uid_param="user_uid")
    async def check_habit_capacity(
        self,
        user_uid: str,
        proposed_difficulty: HabitDifficulty = HabitDifficulty.MODERATE,
        proposed_duration: int = 15,
        max_daily_load: int = DEFAULT_MAX_DAILY_LOAD,
    ) -> Result[dict[str, Any]]:
        """
        Check if user has capacity for another habit.

        Unlike events which check calendar conflicts, habits check
        **effort load** - can the user handle another habit without
        becoming overwhelmed?

        **Effort Calculation:**
        - Base effort from difficulty (1-5)
        - Time factor: duration_minutes / 15
        - Final effort: base * max(1, time_factor)

        Args:
            user_uid: User identifier
            proposed_difficulty: Difficulty of proposed new habit
            proposed_duration: Duration in minutes of proposed habit
            max_daily_load: Maximum daily effort load (default 25)

        Returns:
            Result containing capacity analysis dict
        """
        # Get user's active habits
        result = await self.backend.list_by_user(user_uid=user_uid, limit=100)
        if result.is_error:
            return Result.fail(result.expect_error())

        habits = result.value or []
        active_habits = [h for h in habits if h.status.value == "active"]

        # Calculate current load
        current_load = sum(h.get_effort_score() for h in active_habits)

        # Calculate proposed habit effort
        base_effort = EFFORT_BY_DIFFICULTY.get(proposed_difficulty, 3)
        time_factor = proposed_duration / 15
        proposed_effort = int(base_effort * max(1, time_factor))

        # Calculate remaining capacity
        remaining_capacity = max_daily_load - current_load
        can_add = proposed_effort <= remaining_capacity

        # Generate recommendations
        recommendations = []
        if not can_add:
            recommendations.append(
                f"Daily load would exceed {max_daily_load} effort points. "
                f"Consider archiving low-value habits first."
            )
            # Suggest habits to archive based on low streaks
            low_streak_habits = [h for h in active_habits if h.current_streak < 3]
            if low_streak_habits:
                low_names = [h.title for h in low_streak_habits[:3]]
                recommendations.append(
                    f"Consider archiving struggling habits: {', '.join(low_names)}"
                )
        else:
            headroom = remaining_capacity - proposed_effort
            if headroom < 5:
                recommendations.append(
                    f"Near capacity ({headroom} effort remaining after addition). "
                    "Monitor habit performance closely."
                )
            else:
                recommendations.append("Good capacity available for new habit.")

        # Find best time slot based on current habit distribution
        time_distribution = self._analyze_time_distribution(active_habits)

        return Result.ok(
            {
                "user_uid": user_uid,
                "current_habit_count": len(active_habits),
                "current_load": current_load,
                "max_load": max_daily_load,
                "remaining_capacity": remaining_capacity,
                "proposed_effort": proposed_effort,
                "can_add_habit": can_add,
                "load_percentage": round(current_load / max_daily_load * 100, 1),
                "recommendations": recommendations,
                "time_distribution": time_distribution,
                "suggested_time": self._suggest_best_time(time_distribution),
            }
        )

    def _analyze_time_distribution(self, habits: list[Habit]) -> dict[str, int]:
        """
        Analyze how habits are distributed across times of day.

        Args:
            habits: List of active habits

        Returns:
            Dict mapping time slot to habit count
        """
        distribution = {"morning": 0, "afternoon": 0, "evening": 0, "any": 0}

        for habit in habits:
            time_slot = habit.preferred_time or "any"
            if time_slot in distribution:
                distribution[time_slot] += 1
            else:
                distribution["any"] += 1

        return distribution

    def _suggest_best_time(self, distribution: dict[str, int]) -> str:
        """
        Suggest best time for new habit based on distribution.

        Prefers times with fewer existing habits for better balance.

        Args:
            distribution: Time slot distribution

        Returns:
            Suggested time slot
        """
        # Exclude "any" from comparison
        timed_slots = {k: v for k, v in distribution.items() if k != "any"}
        if not timed_slots:
            return "morning"

        # Return least loaded time slot
        return min(timed_slots, key=make_dict_count_getter(timed_slots))

    # ========================================================================
    # SMART SCHEDULING
    # ========================================================================

    @with_error_handling("create_habit_with_context", error_type="database")
    async def create_habit_with_context(
        self,
        habit_data: HabitCreateRequest,
        user_context: UserContext,
        check_capacity: bool = True,
    ) -> Result[Habit]:
        """
        Create a habit with context validation and capacity checking.

        This method:
        1. Checks habit capacity (if enabled)
        2. Validates prerequisites
        3. Creates the habit
        4. Publishes HabitCreated event

        Args:
            habit_data: Habit creation request
            user_context: User context for validation
            check_capacity: Whether to enforce capacity limits

        Returns:
            Result containing created habit or capacity error
        """
        # Step 1: Check capacity
        if check_capacity:
            capacity_result = await self.check_habit_capacity(
                user_uid=user_context.user_uid,
                proposed_difficulty=habit_data.difficulty,
                proposed_duration=habit_data.duration_minutes,
            )
            if capacity_result.is_error:
                return Result.fail(capacity_result.expect_error())

            capacity = capacity_result.value
            if not capacity["can_add_habit"]:
                return Result.fail(
                    Errors.validation(
                        message=(
                            f"Habit capacity exceeded. Current load: {capacity['current_load']}, "
                            f"Max: {capacity['max_load']}. "
                            f"{capacity['recommendations'][0] if capacity['recommendations'] else ''}"
                        ),
                        field="capacity",
                        value=str(capacity["load_percentage"]),
                    )
                )

        # Step 2: Validate prerequisites (check if prerequisite habits are established)
        if habit_data.prerequisite_habit_uids:
            for prereq_uid in habit_data.prerequisite_habit_uids:
                prereq_streak = user_context.habit_streaks.get(prereq_uid, 0)
                if prereq_streak < ESTABLISHED_STREAK_DAYS:
                    prereq_habit_result = await self.backend.get_habit(prereq_uid)
                    prereq_name = (
                        prereq_habit_result.value.title
                        if prereq_habit_result.is_ok and prereq_habit_result.value
                        else prereq_uid
                    )
                    return Result.fail(
                        Errors.validation(
                            message=(
                                f"Prerequisite habit '{prereq_name}' not established yet. "
                                f"Current streak: {prereq_streak}, need: {ESTABLISHED_STREAK_DAYS} days."
                            ),
                            field="prerequisite_habit_uids",
                            value=prereq_uid,
                        )
                    )

        # Step 3: Create habit via backend
        request_dict = habit_data.model_dump()
        request_dict["user_uid"] = user_context.user_uid

        create_result = await self.backend.create_habit(request_dict)
        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        habit = self._to_domain_model(create_result.value, KuDTO, Habit)

        # Step 4: Publish event
        event = HabitCreated(
            habit_uid=habit.uid,
            user_uid=habit.user_uid,
            title=habit.title,
            frequency=habit.recurrence_pattern if habit.recurrence_pattern else "daily",
            domain=None,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        self.logger.info(
            f"Created habit '{habit.title}' for user {user_context.user_uid} "
            f"(difficulty={habit.habit_difficulty.value if habit.habit_difficulty else 'unknown'}, duration={habit.duration_minutes}min)"
        )

        return Result.ok(habit)

    @with_error_handling("create_habit_with_learning_context", error_type="database")
    async def create_habit_with_learning_context(
        self,
        habit_data: HabitCreateRequest,
        learning_position: LpPosition | None,
        user_context: UserContext,
    ) -> Result[Habit]:
        """
        Create a habit aligned with learning path.

        Combines capacity checking with learning alignment assessment.

        Args:
            habit_data: Habit creation request
            learning_position: User's learning path position
            user_context: User context for validation

        Returns:
            Result containing created habit with learning alignment
        """
        # Check capacity first
        capacity_result = await self.check_habit_capacity(
            user_uid=user_context.user_uid,
            proposed_difficulty=habit_data.difficulty,
            proposed_duration=habit_data.duration_minutes,
        )
        if capacity_result.is_error:
            return Result.fail(capacity_result.expect_error())

        if not capacity_result.value["can_add_habit"]:
            return Result.fail(
                Errors.validation(
                    message="Habit capacity exceeded. Archive some habits first.",
                    field="capacity",
                )
            )

        # Use LearningAlignmentHelper for creation
        custom_fields = {"user_uid": user_context.user_uid}

        result = await self.learning_helper.create_with_learning_alignment(
            request=habit_data,
            learning_position=learning_position,
            context=user_context,
            custom_fields=custom_fields,
        )

        if result.is_ok:
            habit = result.value
            # Publish event
            event = HabitCreated(
                habit_uid=habit.uid,
                user_uid=habit.user_uid,
                title=habit.title,
                frequency=habit.recurrence_pattern if habit.recurrence_pattern else "daily",
                domain=None,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    # ========================================================================
    # FREQUENCY OPTIMIZATION
    # ========================================================================

    @with_error_handling("suggest_habit_frequency", error_type="database")
    async def suggest_habit_frequency(
        self,
        user_uid: str,
        category: HabitCategory,
        difficulty: HabitDifficulty = HabitDifficulty.MODERATE,
    ) -> Result[dict[str, Any]]:
        """
        Suggest optimal frequency for a new habit.

        Based on:
        - User's existing habits in the same category
        - Difficulty level (harder = less frequent to start)
        - Best practices for habit formation

        Args:
            user_uid: User identifier
            category: Habit category
            difficulty: Proposed difficulty

        Returns:
            Result containing frequency suggestion
        """
        # Get user's habits in same category
        result = await self.backend.list_by_user(user_uid=user_uid, limit=100)
        if result.is_error:
            return Result.fail(result.expect_error())

        habits = result.value or []
        category_habits = [h for h in habits if h.category == category]

        # Analyze success rates by frequency in this category
        frequency_success: dict[RecurrencePattern, list[float]] = {
            RecurrencePattern.DAILY: [],
            RecurrencePattern.WEEKLY: [],
        }

        for habit in category_habits:
            pattern = (
                RecurrencePattern(habit.recurrence_pattern) if habit.recurrence_pattern else None
            )
            if pattern in frequency_success:
                frequency_success[pattern].append(habit.success_rate)

        # Calculate average success by frequency
        avg_success = {}
        for freq, rates in frequency_success.items():
            if rates:
                avg_success[freq] = sum(rates) / len(rates)
            else:
                avg_success[freq] = 0.5  # Default 50% for no data

        # Adjust recommendation based on difficulty
        difficulty_factor = {
            HabitDifficulty.TRIVIAL: 1.0,  # Can do daily
            HabitDifficulty.EASY: 1.0,
            HabitDifficulty.MODERATE: 0.9,
            HabitDifficulty.CHALLENGING: 0.7,  # Might need to start weekly
            HabitDifficulty.HARD: 0.5,
        }.get(difficulty, 0.8)

        # Determine recommendation
        if difficulty in [HabitDifficulty.CHALLENGING, HabitDifficulty.HARD]:
            recommended = RecurrencePattern.WEEKLY
            rationale = (
                "Challenging habits benefit from weekly practice initially. "
                "You can increase to daily once established (after 7+ day streak)."
            )
        elif avg_success.get(RecurrencePattern.DAILY, 0) < 0.5 and category_habits:
            recommended = RecurrencePattern.WEEKLY
            rationale = (
                f"Your daily {category.value} habits have {avg_success.get(RecurrencePattern.DAILY, 0):.0%} success rate. "
                f"Consider starting weekly to build momentum."
            )
        else:
            recommended = RecurrencePattern.DAILY
            rationale = "Daily habits build faster momentum. Start with a tiny version if needed."

        return Result.ok(
            {
                "recommended_frequency": recommended.value,
                "confidence": difficulty_factor,
                "rationale": rationale,
                "category_habits_count": len(category_habits),
                "category_avg_success": {k.value: round(v, 2) for k, v in avg_success.items()},
                "target_days_suggestion": 7 if recommended == RecurrencePattern.DAILY else 2,
            }
        )

    @with_error_handling("optimize_habit_schedule", error_type="database", uid_param="habit_uid")
    async def optimize_habit_schedule(
        self,
        habit_uid: str,
        user_context: UserContext,
    ) -> Result[dict[str, Any]]:
        """
        Suggest optimal schedule adjustments for an existing habit.

        Analyzes completion patterns to find best times and days.

        Args:
            habit_uid: Habit to optimize
            user_context: User context

        Returns:
            Result containing schedule optimization suggestions
        """
        # Get the habit
        habit_result = await self.backend.get_habit(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result.expect_error())
        if not habit_result.value:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_uid))

        habit = to_domain_model(habit_result.value, KuDTO, Habit)

        # Get completion history if available
        completion_patterns: dict[str, Any] = {
            "best_day": None,
            "best_time": None,
            "completion_by_day": {},
            "completion_by_hour": {},
        }

        if self.completions:
            completions_result = await self.completions.get_completions_for_habit(habit_uid)
            if completions_result.is_ok and completions_result.value:
                completions = completions_result.value

                # Analyze day of week patterns
                day_counts: dict[int, int] = {}
                hour_counts: dict[int, int] = {}

                for comp in completions:
                    if comp.completed_at:
                        day = comp.completed_at.weekday()
                        hour = comp.completed_at.hour
                        day_counts[day] = day_counts.get(day, 0) + 1
                        hour_counts[hour] = hour_counts.get(hour, 0) + 1

                if day_counts:
                    best_day_num = max(day_counts, key=make_dict_count_getter(day_counts))
                    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                    completion_patterns["best_day"] = days[best_day_num]
                    completion_patterns["completion_by_day"] = {
                        days[k]: v for k, v in day_counts.items()
                    }

                if hour_counts:
                    best_hour = max(hour_counts, key=make_dict_count_getter(hour_counts))
                    if best_hour < 12:
                        completion_patterns["best_time"] = "morning"
                    elif best_hour < 17:
                        completion_patterns["best_time"] = "afternoon"
                    else:
                        completion_patterns["best_time"] = "evening"
                    completion_patterns["completion_by_hour"] = hour_counts

        # Generate recommendations
        recommendations = []

        if (
            completion_patterns["best_time"]
            and completion_patterns["best_time"] != habit.preferred_time
        ):
            recommendations.append(
                f"Consider switching to {completion_patterns['best_time']} - "
                f"you complete this habit most often then."
            )

        if habit.success_rate < 0.5:
            recommendations.append(
                "Success rate below 50% - consider reducing difficulty or frequency."
            )

        if habit.current_streak == 0 and habit.best_streak > 7:
            recommendations.append(
                f"Rebuild your streak! You've achieved {habit.best_streak} days before."
            )

        return Result.ok(
            {
                "habit_uid": habit_uid,
                "habit_name": habit.title,
                "current_schedule": {
                    "frequency": habit.recurrence_pattern if habit.recurrence_pattern else "daily",
                    "target_days": habit.target_days_per_week,
                    "preferred_time": habit.preferred_time,
                },
                "completion_patterns": completion_patterns,
                "recommendations": recommendations,
                "success_rate": habit.success_rate,
                "current_streak": habit.current_streak,
            }
        )

    # ========================================================================
    # HABIT STACKING (James Clear Pattern)
    # ========================================================================

    @with_error_handling("suggest_habit_stacking", error_type="database", uid_param="user_uid")
    async def suggest_habit_stacking(
        self,
        user_uid: str,
        new_habit_time: str | None = None,
        new_habit_category: HabitCategory | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Suggest habits to stack with a new habit.

        **James Clear's Habit Stacking:**
        "After [CURRENT HABIT], I will [NEW HABIT]"

        Finds established habits (streak >= 7) that can serve as
        anchors for new habits.

        **Stacking Criteria:**
        - Same preferred time (or close)
        - Established streak (7+ days)
        - Complementary category (not duplicate)

        Args:
            user_uid: User identifier
            new_habit_time: Preferred time for new habit
            new_habit_category: Category of new habit

        Returns:
            Result containing list of stacking suggestions
        """
        # Get user's established habits
        result = await self.backend.list_by_user(user_uid=user_uid, limit=100)
        if result.is_error:
            return Result.fail(result.expect_error())

        habits = result.value or []

        # Filter to established habits (streak >= 7)
        established = [
            h
            for h in habits
            if h.status.value == "active" and h.current_streak >= ESTABLISHED_STREAK_DAYS
        ]

        if not established:
            return Result.ok(
                [
                    {
                        "message": "No established habits found. Build a 7-day streak first.",
                        "suggestions": [],
                    }
                ]
            )

        # Score and rank potential anchor habits
        suggestions = []

        for habit in established:
            score = 0.0
            reasons = []

            # Time match (highest weight)
            if new_habit_time:
                if habit.preferred_time == new_habit_time:
                    score += 0.4
                    reasons.append(f"Same time slot ({new_habit_time})")
                elif habit.preferred_time in ["morning", "evening"] and new_habit_time in [
                    "morning",
                    "evening",
                ]:
                    score += 0.2
                    reasons.append("Similar time of day")

            # Category complementarity
            if new_habit_category:
                if habit.habit_category != new_habit_category:
                    score += 0.3
                    reasons.append(
                        f"Complementary category ({habit.habit_category.value if habit.habit_category else 'unknown'} + {new_habit_category.value})"
                    )

            # Streak strength
            streak_factor = min(1.0, habit.current_streak / 30)
            score += streak_factor * 0.2
            reasons.append(f"Strong streak ({habit.current_streak} days)")

            # Success rate
            if habit.success_rate > 0.8:
                score += 0.1
                reasons.append(f"High success rate ({habit.success_rate:.0%})")

            suggestions.append(
                {
                    "anchor_habit_uid": habit.uid,
                    "anchor_habit_name": habit.title,
                    "preferred_time": habit.preferred_time,
                    "category": habit.habit_category.value if habit.habit_category else "unknown",
                    "current_streak": habit.current_streak,
                    "success_rate": habit.success_rate,
                    "stacking_score": round(score, 2),
                    "reasons": reasons,
                    "stacking_formula": f'After "{habit.title}", I will [NEW HABIT]',
                }
            )

        # Sort by stacking score
        suggestions.sort(key=itemgetter("stacking_score"), reverse=True)

        self.logger.info(f"Found {len(suggestions)} habit stacking options for user {user_uid}")

        return Result.ok(suggestions[:5])  # Top 5 suggestions

    # ========================================================================
    # LEARNING PATH INTEGRATION
    # ========================================================================

    @with_error_handling("create_habit_from_learning_step", error_type="database")
    async def create_habit_from_learning_step(
        self,
        learning_step_uid: str,
        user_context: UserContext,
        frequency: RecurrencePattern = RecurrencePattern.DAILY,
        duration_minutes: int = 15,
    ) -> Result[Habit]:
        """
        Generate a practice habit from a learning step.

        Creates a habit designed to reinforce a specific learning step
        through regular practice.

        Args:
            learning_step_uid: UID of the learning step
            user_context: User context
            frequency: Practice frequency
            duration_minutes: Practice duration

        Returns:
            Result containing created practice habit
        """
        # Check capacity first
        capacity_result = await self.check_habit_capacity(
            user_uid=user_context.user_uid,
            proposed_difficulty=HabitDifficulty.MODERATE,
            proposed_duration=duration_minutes,
        )
        if capacity_result.is_error:
            return Result.fail(capacity_result.expect_error())

        if not capacity_result.value["can_add_habit"]:
            return Result.fail(
                Errors.validation(
                    message="Habit capacity exceeded. Cannot add learning practice habit.",
                    field="capacity",
                )
            )

        # Create habit for learning practice
        habit_dict = {
            "user_uid": user_context.user_uid,
            "name": f"Practice: {learning_step_uid}",
            "description": f"Daily practice to master learning step {learning_step_uid}",
            "category": HabitCategory.LEARNING,
            "difficulty": HabitDifficulty.MODERATE,
            "recurrence_pattern": frequency,
            "target_days_per_week": 7 if frequency == RecurrencePattern.DAILY else 3,
            "duration_minutes": duration_minutes,
            "preferred_time": capacity_result.value.get("suggested_time", "morning"),
            "source_learning_step_uid": learning_step_uid,
            "curriculum_practice_type": "daily_review",
            "priority": Priority.HIGH,
            "tags": ["learning", "practice", "curriculum"],
        }

        create_result = await self.backend.create_habit(habit_dict)
        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        habit = self._to_domain_model(create_result.value, KuDTO, Habit)

        # Publish event
        event = HabitCreated(
            habit_uid=habit.uid,
            user_uid=habit.user_uid,
            title=habit.title,
            frequency=frequency.value,
            domain=None,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        self.logger.info(
            f"Created learning practice habit '{habit.title}' from step {learning_step_uid}"
        )

        return Result.ok(habit)

    # ========================================================================
    # CALENDAR ANALYSIS (Habit-Focused)
    # ========================================================================

    @with_error_handling("get_habit_load_by_day", error_type="database", uid_param="user_uid")
    async def get_habit_load_by_day(
        self,
        user_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Calculate habit effort load by day of week.

        Helps identify which days are overloaded with habits.

        Args:
            user_uid: User identifier

        Returns:
            Result containing load analysis by day
        """
        result = await self.backend.list_by_user(user_uid=user_uid, limit=100)
        if result.is_error:
            return Result.fail(result.expect_error())

        habits = result.value or []
        active_habits = [h for h in habits if h.status.value == "active"]

        # Calculate load by day
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        load_by_day = {day: 0 for day in days}

        for habit in active_habits:
            effort = habit.get_effort_score()

            if habit.recurrence_pattern == RecurrencePattern.DAILY:
                # Add to all days
                for day in days:
                    load_by_day[day] += effort
            elif habit.recurrence_pattern == RecurrencePattern.WEEKLY:
                # Add to target_days_per_week days (assume first N days)
                for i in range(min(habit.target_days_per_week, 7)):
                    load_by_day[days[i]] += effort

        # Find peak and light days
        peak_day = max(load_by_day, key=make_dict_count_getter(load_by_day))
        light_day = min(load_by_day, key=make_dict_count_getter(load_by_day))
        avg_load = sum(load_by_day.values()) / 7

        return Result.ok(
            {
                "user_uid": user_uid,
                "active_habit_count": len(active_habits),
                "load_by_day": load_by_day,
                "peak_day": peak_day,
                "peak_load": load_by_day[peak_day],
                "light_day": light_day,
                "light_load": load_by_day[light_day],
                "average_daily_load": round(avg_load, 1),
                "recommendations": self._generate_load_recommendations(load_by_day, avg_load),
            }
        )

    def _generate_load_recommendations(
        self,
        load_by_day: dict[str, int],
        avg_load: float,
    ) -> list[str]:
        """Generate recommendations based on load distribution."""
        recommendations = []

        # Check for overloaded days
        for day, load in load_by_day.items():
            if load > avg_load * 1.5:
                recommendations.append(
                    f"{day.capitalize()} is overloaded ({load} effort). "
                    "Consider moving habits to lighter days."
                )

        # Check for empty days
        for day, load in load_by_day.items():
            if load < avg_load * 0.5 and load > 0:
                recommendations.append(
                    f"{day.capitalize()} has light load ({load} effort). "
                    "Good day for challenging habits."
                )

        if not recommendations:
            recommendations.append("Habit load is well-balanced across the week.")

        return recommendations
