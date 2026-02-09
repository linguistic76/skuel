"""
Habit Domain Model (Tier 3 - Core)
===================================

Immutable domain model with business logic for habits.
Aligned with Knowledge and LearningPath patterns for cohesive learning system.

Phase 1-4 Integration (October 3, 2025):
- Phase 1: APOC query building for knowledge reinforcement and goal support
- Phase 3: GraphContext for cross-domain habit intelligence
- Phase 4: QueryIntent selection for habit-specific patterns
"""

from __future__ import annotations

from core.constants import GraphDepth

__version__ = "2.1"  # Updated for Phase 1-4 integration


from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar

from core.models.enums import Priority, RecurrencePattern
from core.models.mixins import StatusChecksMixin
from core.models.query import QueryIntent

# Phase 1: Query Infrastructure
from core.models.query.graph_traversal import build_graph_context_query

if TYPE_CHECKING:
    from core.models.habit.habit_relationships import HabitRelationships


class HabitPolarity(str, Enum):
    """Whether building a positive habit or breaking a negative one"""

    BUILD = "build"  # Positive habit to build
    BREAK = "break"  # Negative habit to break
    NEUTRAL = "neutral"  # Neutral tracking


class HabitCategory(str, Enum):
    """Categories aligned with learning domains"""

    HEALTH = "health"
    FITNESS = "fitness"
    MINDFULNESS = "mindfulness"
    LEARNING = "learning"  # Direct learning activities
    PRODUCTIVITY = "productivity"
    CREATIVE = "creative"
    SOCIAL = "social"
    FINANCIAL = "financial"
    OTHER = "other"


class HabitDifficulty(str, Enum):
    """Difficulty level aligned with learning complexity"""

    TRIVIAL = "trivial"  # < 2 minutes
    EASY = "easy"  # 2-5 minutes
    MODERATE = "moderate"  # 5-20 minutes
    CHALLENGING = "challenging"  # 20-60 minutes
    HARD = "hard"  # > 60 minutes


class HabitStatus(str, Enum):
    """Current state of a habit"""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"  # Achieved target
    ABANDONED = "abandoned"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class Habit(StatusChecksMixin):
    """
    Immutable domain model representing a habit.

    Habits are core to learning - they create consistent practice patterns
    that reinforce knowledge acquisition and skill development.

    RELATIONSHIP ARCHITECTURE:

    Habits exist in a web of influences and impacts:
    - Upstream: Principles (alignment), Goals (support), Prerequisites (foundation)
    - Downstream: Dependent habits, Goal progress, Knowledge practice

    Use HabitService to query these relationships - domain models define structure,
    services provide graph-native operations.
    """

    # Identity
    uid: str
    user_uid: str  # REQUIRED - habit ownership
    name: str
    description: str | None = None

    # Behavior Definition
    polarity: HabitPolarity = HabitPolarity.BUILD
    category: HabitCategory = HabitCategory.OTHER
    difficulty: HabitDifficulty = HabitDifficulty.MODERATE

    # Schedule & Recurrence
    recurrence_pattern: RecurrencePattern = RecurrencePattern.DAILY
    target_days_per_week: int = 7
    preferred_time: str | None = None  # "morning", "afternoon", "evening"
    duration_minutes: int = 15

    # Reminders
    reminder_time: str | None = None  # HH:MM format
    reminder_days: tuple[str, ...] = ()  # Days of week (e.g., "monday", "tuesday")
    reminder_enabled: bool = False

    # Learning Integration - GRAPH-NATIVE: Relationships stored as Neo4j edges
    # Graph relationship: (habit)-[:PRACTICES_KNOWLEDGE]->(ku)
    # Graph relationship: (habit)-[:SUPPORTS_GOAL]->(goal)
    # Graph relationship: (habit)-[:ALIGNED_WITH_PRINCIPLE]->(principle)
    # Graph relationship: (habit)-[:REQUIRES_PREREQUISITE]->(prereq_habit)

    # Curriculum Spine Integration (NEW - habit ↔ ls ↔ lp)
    source_learning_step_uid: str | None = None  # ls: UID if habit generated from curriculum
    source_learning_path_uid: str | None = None  # lp: UID for path-level habits
    # Graph relationship: (habit)-[:REINFORCES_STEP]->(ls)
    curriculum_practice_type: str | None = (
        None  # 'daily_review', 'weekly_practice', 'skill_building'
    )

    # Atomic Habits Integration (Identity-Based Habits)
    # James Clear: "Every action you take is a vote for the type of person you wish to become."
    reinforces_identity: str | None = None  # e.g., "I am a writer", "I am a runner"
    identity_votes_cast: int = 0  # Total completions = votes for identity
    is_identity_habit: bool = False  # True if primary purpose is identity reinforcement

    # Progress Tracking
    current_streak: int = 0
    best_streak: int = 0
    total_completions: int = 0
    total_attempts: int = 0
    success_rate: float = 0.0
    last_completed: datetime | None = None  # type: ignore[assignment]

    # Behavioral Science
    cue: str | None = None  # Environmental/time trigger
    routine: str | None = None  # Specific actions to take
    reward: str | None = None  # Immediate benefit/reward

    # Status
    status: HabitStatus = HabitStatus.ACTIVE
    priority: Priority = Priority.MEDIUM

    # Metadata
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    started_at: datetime | None = None  # type: ignore[assignment]
    completed_at: datetime | None = None  # type: ignore[assignment]

    # Tags for organization
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = None  # type: ignore[assignment]  # Rich context storage (graph neighborhoods, etc.)

    # StatusChecksMixin configuration
    # Habit uses HabitStatus with COMPLETED as the completed state
    _completed_statuses: ClassVar[tuple[HabitStatus, ...]] = (HabitStatus.COMPLETED,)
    _cancelled_statuses: ClassVar[tuple[HabitStatus, ...]] = (HabitStatus.ABANDONED,)
    _terminal_statuses: ClassVar[tuple[HabitStatus, ...]] = (
        HabitStatus.COMPLETED,
        HabitStatus.ABANDONED,
        HabitStatus.ARCHIVED,
    )
    _active_statuses: ClassVar[tuple[HabitStatus, ...]] = (
        HabitStatus.ACTIVE,
        HabitStatus.PAUSED,
    )

    def __post_init__(self) -> None:
        """Set defaults for datetime and metadata fields."""
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", datetime.now())
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})

    # ==========================================================================
    # KNOWLEDGE CARRIER PROTOCOL IMPLEMENTATION
    # ==========================================================================
    # Habit implements KnowledgeCarrier and ActivityCarrier.
    # Habit PRACTICES knowledge - relevance based on learning integration.

    def knowledge_relevance(self) -> float:
        """
        How relevant is knowledge to this entity? (0.0-1.0)

        Habit relevance based on curriculum and learning integration.

        Returns:
            0.0-1.0 based on learning integration
        """
        score = 0.0

        # Learning category habit (highest relevance)
        if self.category == HabitCategory.LEARNING:
            score = 0.8

        # From learning step
        if self.source_learning_step_uid:
            score = max(score, 0.9)

        # From learning path
        if self.source_learning_path_uid:
            score = max(score, 0.7)

        # Identity-based habit (builds knowledge identity)
        if self.is_identity_habit:
            score = max(score, 0.6)

        # Has curriculum practice type
        if self.curriculum_practice_type:
            score = max(score, 0.7)

        return score

    def get_knowledge_uids(self) -> tuple[str, ...]:
        """
        Get all knowledge UIDs this entity practices.

        Habit knowledge is stored as graph relationships.
        This is a GRAPH-NATIVE placeholder - actual data requires service layer.

        Use service.relationships.get_habit_knowledge(habit_uid) for real data.

        Returns:
            Empty tuple (placeholder - actual KU UIDs via graph query)
        """
        # GRAPH-NATIVE: Real implementation requires service layer query
        # Query: MATCH (habit)-[:PRACTICES_KNOWLEDGE]->(ku) RETURN ku.uid
        return ()

    def learning_impact_score(self) -> float:
        """
        Calculate learning impact when this habit is completed.

        Used by event-driven updates to increment KU substance counters.
        Habits have highest substance impact (lifestyle integration).

        Returns:
            Impact score 0.0-1.0
        """
        score = 0.0

        # From curriculum (highest impact)
        if self.source_learning_step_uid:
            score += 0.4

        # Learning category
        if self.category == HabitCategory.LEARNING:
            score += 0.3

        # Identity habit (strong integration)
        if self.is_identity_habit:
            score += 0.2

        # Streak bonus (consistency matters)
        if self.current_streak >= 21:  # 21-day habit formation
            score += 0.1

        return min(1.0, score)

    # ==========================================================================
    # STATUS CHECKS
    # ==========================================================================
    # is_completed(), is_cancelled(), is_terminal() provided by StatusChecksMixin

    def is_active(self) -> bool:
        """Check if habit is currently active."""
        return self.status == HabitStatus.ACTIVE

    def is_abandoned(self) -> bool:
        """Check if habit was abandoned. Alias for is_cancelled()."""
        return self.is_cancelled()

    # ==========================================================================
    # LEARNING INTEGRATION
    # ==========================================================================

    def supports_learning(self) -> bool:
        """
        Check if this habit is linked to learning activities.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "PRACTICES_KNOWLEDGE", "outgoing") > 0
        """
        return (
            self.category == HabitCategory.LEARNING or self.is_from_curriculum()
        )  # Partial check - missing PRACTICES_KNOWLEDGE relationship check

    # ==========================================================================
    # CURRICULUM SPINE INTEGRATION (Habit ↔ ls ↔ lp bridge)
    # ==========================================================================

    def is_from_curriculum(self) -> bool:
        """Check if habit originated from curriculum (learning step or path)."""
        return (
            self.source_learning_step_uid is not None or self.source_learning_path_uid is not None
        )

    def is_from_learning_step(self) -> bool:
        """Check if habit was generated from a learning step."""
        return self.source_learning_step_uid is not None

    def is_from_learning_path(self) -> bool:
        """Check if habit is a path-level practice habit."""
        return self.source_learning_path_uid is not None

    def reinforces_curriculum(self) -> bool:
        """
        Check if habit reinforces any learning steps.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "REINFORCES_STEP", "outgoing") > 0
        """
        return False  # Placeholder - service queries backend.count_related()

    def is_curriculum_practice_habit(self) -> bool:
        """Check if habit is specifically for curriculum practice."""
        return self.curriculum_practice_type is not None

    def is_daily_review_habit(self) -> bool:
        """Check if habit is for daily curriculum review."""
        return self.curriculum_practice_type == "daily_review"

    def is_skill_building_habit(self) -> bool:
        """Check if habit is for skill building."""
        return self.curriculum_practice_type == "skill_building"

    def get_curriculum_context(self) -> dict:
        """
        Get complete curriculum context for this habit.

        Returns:
            Dictionary with curriculum linkage information

        GRAPH-NATIVE: Service layer must populate relationship UIDs from graph.
        Use: backend.get_related_uids() for REINFORCES_STEP and PRACTICES_KNOWLEDGE
        """
        return {
            "is_curriculum_habit": self.is_from_curriculum(),
            "source_learning_step": self.source_learning_step_uid,
            "source_learning_path": self.source_learning_path_uid,
            "reinforces_steps": [],  # GRAPH QUERY REQUIRED: REINFORCES_STEP relationships
            "practice_type": self.curriculum_practice_type,
            "reinforces_knowledge": [],  # GRAPH QUERY REQUIRED: PRACTICES_KNOWLEDGE relationships
            "is_learning_habit": self.supports_learning(),
            "total_curriculum_connections": 0,  # GRAPH QUERY REQUIRED: count both relationships
        }

    def curriculum_integration_score(self) -> float:
        """
        Calculate how well integrated this habit is with curriculum (0-1).

        Higher scores indicate stronger curriculum connection.

        GRAPH-NATIVE: Service layer must query graph to calculate full score.
        Use: backend.count_related() for REINFORCES_STEP and PRACTICES_KNOWLEDGE
        """
        score = 0.0

        # Direct curriculum source (40%)
        if self.is_from_curriculum():
            score += 0.4

        # Reinforces steps (30%) - GRAPH QUERY REQUIRED
        # Service must: count_related(uid, "REINFORCES_STEP", "outgoing")

        # Knowledge linkage (20%) - GRAPH QUERY REQUIRED
        # Service must: count_related(uid, "PRACTICES_KNOWLEDGE", "outgoing")

        # Practice type defined (10%)
        if self.curriculum_practice_type:
            score += 0.1

        return score  # Partial score - missing 50% from graph relationships

    def is_keystone(self) -> bool:
        """
        Check if this is a keystone habit.
        Keystone habits trigger positive changes in other areas.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "SUPPORTS_GOAL", "outgoing") >= 3
        """
        return self.category in [HabitCategory.FITNESS, HabitCategory.MINDFULNESS]
        # Partial check - missing SUPPORTS_GOAL graph query

    # ==========================================================================
    # ATOMIC HABITS INTEGRATION (Identity + Goal Systems)
    # ==========================================================================
    # James Clear: "Every action you take is a vote for the type of person
    #               you wish to become."
    # ==========================================================================

    def is_identity_based(self) -> bool:
        """Check if this habit reinforces an identity."""
        return self.reinforces_identity is not None or self.is_identity_habit

    def cast_identity_vote(self) -> int:
        """
        Record completion as a vote for identity.

        James Clear: "Every action is a vote for the person you want to become."

        Returns:
            New total identity votes
        """
        return self.identity_votes_cast + 1  # Immutable, so just return new value

    def get_identity_strength(self) -> float:
        """
        Calculate how well this habit has established the target identity.

        Based on James Clear's research: ~40-50 repetitions to form identity.

        Returns:
            Score 0-1 where 1.0 = identity fully established (50+ votes)
        """
        if not self.is_identity_based():
            return 0.0

        # 50 completions = full identity establishment
        return min(1.0, self.identity_votes_cast / 50.0)

    def get_goal_system_contribution(self) -> dict:
        """
        Get analysis of how this habit contributes to goal systems.

        Returns:
            Dictionary with system contribution metrics

        GRAPH-NATIVE: Service layer must populate goal UIDs from graph.
        Use: backend.get_related_uids(uid, "SUPPORTS_GOAL", "outgoing")
        """
        return {
            "supports_goals": False,  # GRAPH QUERY REQUIRED: count SUPPORTS_GOAL relationships
            "goal_count": 0,  # GRAPH QUERY REQUIRED
            "goal_uids": [],  # GRAPH QUERY REQUIRED: get_related_uids
            "is_identity_based": self.is_identity_based(),
            "identity": self.reinforces_identity,
            "identity_strength": self.get_identity_strength(),
            "success_rate": self.success_rate,
            "consistency_score": self.calculate_consistency_score(),
            "system_health": "strong"
            if self.success_rate > 0.7
            else "moderate"
            if self.success_rate > 0.4
            else "weak",
        }

    def calculate_consistency_score(self) -> float:
        """
        Calculate habit consistency (crucial for goal systems).

        James Clear: "Systems > Goals" because systems are about consistency.

        Returns:
            0-1 score where 1.0 = perfect consistency
        """
        # Combine success rate with streak performance
        if self.total_attempts == 0:
            return 0.0

        # Success rate is 70% of score
        success_component = self.success_rate * 0.7

        # Current streak relative to best streak is 30%
        streak_component = 0.0
        if self.best_streak > 0:
            streak_component = (self.current_streak / self.best_streak) * 0.3

        return min(1.0, success_component + streak_component)

    def predict_goal_impact(self) -> float:
        """
        Predict this habit's impact based on consistency and identity alignment.

        This is a PARTIAL impact score (80% weight) based on habit characteristics only.
        For FULL impact including goal breadth (20% weight), service layer should query:
            goal_count = await backend.count_related(uid, "SUPPORTS_GOAL", "outgoing")
            goal_breadth_score = min(1.0, goal_count / 5.0)
            final_score = (partial_score * 0.8) + (goal_breadth_score * 0.2)

        Strong, consistent habits = high goal achievement probability.

        Returns:
            Partial impact score 0-1 (missing goal breadth component)

        Note: Domain model cannot access graph relationships - that's service layer responsibility.
        """
        # Consistency is most important
        consistency = self.calculate_consistency_score()

        # Identity alignment adds strength
        identity_bonus = 0.1 if self.is_identity_based() else 0.0

        impact = (consistency * 0.7) + identity_bonus

        return min(1.0, impact)  # Partial score - service layer adds goal breadth

    def get_atomic_habits_analysis(self, rels: HabitRelationships | None = None) -> dict:
        """
        Get complete Atomic Habits analysis for this habit.

        Shows how this habit fits into James Clear's framework.

        Returns:
            Complete analysis including identity, systems, and impact
        """
        return {
            "identity": {
                "is_identity_based": self.is_identity_based(),
                "reinforces_identity": self.reinforces_identity,
                "identity_votes_cast": self.identity_votes_cast,
                "identity_strength": self.get_identity_strength(),
                "votes_to_establishment": max(0, 50 - self.identity_votes_cast),
            },
            "system_contribution": {
                "part_of_system": (len(rels.linked_goal_uids) if rels else 0) > 0,
                "supports_goal_count": len(rels.linked_goal_uids) if rels else 0,
                "consistency_score": self.calculate_consistency_score(),
                "predicted_impact": self.predict_goal_impact(),
            },
            "habit_quality": {
                "success_rate": self.success_rate,
                "current_streak": self.current_streak,
                "best_streak": self.best_streak,
                "total_completions": self.total_completions,
                "is_on_streak": self.is_on_streak(),
            },
            "behavioral_design": {
                "has_cue": self.cue is not None,
                "has_routine": self.routine is not None,
                "has_reward": self.reward is not None,
                "design_completeness": sum([1 for x in [self.cue, self.routine, self.reward] if x])
                / 3.0,
            },
            "recommendations": self._generate_improvement_recommendations(),
        }

    def _generate_improvement_recommendations(
        self, rels: HabitRelationships | None = None
    ) -> list[str]:
        """Generate recommendations for improving this habit."""
        recommendations = []

        if self.success_rate < 0.5:
            recommendations.append(
                "Success rate below 50% - consider making habit easier or more rewarding"
            )

        if not self.cue:
            recommendations.append("Define a clear cue/trigger for this habit")

        if not self.reward:
            recommendations.append("Add an immediate reward to reinforce completion")

        if self.current_streak == 0 and self.best_streak > 0:
            recommendations.append(
                f"Rebuild streak - you've achieved {self.best_streak} days before"
            )

        if self.is_identity_based() and self.identity_votes_cast < 50:
            remaining = 50 - self.identity_votes_cast
            recommendations.append(
                f"Complete {remaining} more times to establish '{self.reinforces_identity}' identity"
            )

        if (len(rels.linked_goal_uids) if rels else 0) == 0:
            recommendations.append("Link this habit to a goal to create a system")

        return recommendations

    # ==========================================================================
    # PROGRESS CALCULATIONS
    # ==========================================================================

    def get_completion_rate(self) -> float:
        """Calculate completion rate as percentage."""
        if self.total_attempts == 0:
            return 0.0
        return (self.total_completions / self.total_attempts) * 100

    def is_on_streak(self, as_of: datetime | None = None) -> bool:
        """Check if habit is currently on a streak."""
        if not self.last_completed:
            return False

        check_date = as_of or datetime.now()
        days_since = (check_date - self.last_completed).days

        if self.recurrence_pattern == RecurrencePattern.DAILY:
            return days_since <= 1
        elif self.recurrence_pattern == RecurrencePattern.WEEKLY:
            return days_since <= 7
        else:
            return days_since <= 30

    def streak_at_risk(self) -> bool:
        """Check if current streak is at risk of being broken."""
        if not self.last_completed or self.current_streak == 0:
            return False

        days_since = (datetime.now() - self.last_completed).days

        if self.recurrence_pattern == RecurrencePattern.DAILY:
            return days_since >= 1
        elif self.recurrence_pattern == RecurrencePattern.WEEKLY:
            return days_since >= 6
        else:
            return days_since >= 25

    # ==========================================================================
    # DIFFICULTY & EFFORT
    # ==========================================================================

    def get_effort_score(self) -> int:
        """
        Calculate effort score based on difficulty and duration.
        Used for balancing daily habit load.
        """
        difficulty_scores = {
            HabitDifficulty.TRIVIAL: 1,
            HabitDifficulty.EASY: 2,
            HabitDifficulty.MODERATE: 3,
            HabitDifficulty.CHALLENGING: 4,
            HabitDifficulty.HARD: 5,
        }

        base_score = difficulty_scores.get(self.difficulty, 3)
        time_factor = self.duration_minutes / 15  # Every 15 minutes adds to effort

        return int(base_score * max(1, time_factor))

    def is_tiny_habit(self) -> bool:
        """Check if this qualifies as a 'tiny habit' (BJ Fogg method)."""
        return self.difficulty == HabitDifficulty.TRIVIAL and self.duration_minutes <= 2

    # ==========================================================================
    # BEHAVIORAL PATTERNS
    # ==========================================================================

    def has_complete_loop(self) -> bool:
        """Check if habit has complete cue-routine-reward loop defined."""
        return all([self.cue, self.routine, self.reward])

    def is_implementation_ready(self) -> bool:
        """Check if habit has enough detail for implementation."""
        return (
            self.routine is not None
            and self.preferred_time is not None
            and self.duration_minutes > 0
        )

    def get_consistency_level(self) -> str:
        """
        Get consistency level based on success rate.
        Returns: "struggling", "developing", "consistent", "mastered"
        """
        rate = self.get_completion_rate()
        if rate < 40:
            return "struggling"
        elif rate < 70:
            return "developing"
        elif rate < 90:
            return "consistent"
        else:
            return "mastered"

    # ==========================================================================
    # SCHEDULING
    # ==========================================================================

    def should_do_today(self, day_of_week: int) -> bool:
        """
        Check if habit should be done on given day.
        day_of_week: 0=Monday, 6=Sunday
        """
        if self.recurrence_pattern == RecurrencePattern.DAILY:
            return True
        elif self.recurrence_pattern == RecurrencePattern.WEEKLY:
            # Assume weekly habits are done on specific days
            # This would need more sophisticated logic based on target_days_per_week
            return day_of_week < self.target_days_per_week
        else:
            return False

    def get_next_scheduled_date(self) -> date | None:
        """Calculate next scheduled date for this habit."""
        if not self.last_completed:
            return date.today()

        last_date = self.last_completed.date()

        if self.recurrence_pattern == RecurrencePattern.DAILY:
            return last_date + timedelta(days=1)
        elif self.recurrence_pattern == RecurrencePattern.WEEKLY:
            return last_date + timedelta(weeks=1)
        elif self.recurrence_pattern == RecurrencePattern.MONTHLY:
            return last_date + timedelta(days=30)
        else:
            return None

    # ==========================================================================
    # CONVERSIONS
    # ==========================================================================

    @classmethod
    def from_dto(cls, dto: HabitDTO) -> Habit:
        """
        Create immutable Habit from mutable DTO.

        GRAPH-NATIVE: UID list fields are NOT transferred from DTO to domain model.
        Relationships exist only as Neo4j edges, queried via service layer.
        """
        return cls(
            uid=dto.uid,
            user_uid=dto.user_uid,
            name=dto.name,
            description=dto.description,
            polarity=dto.polarity,
            category=dto.category,
            difficulty=dto.difficulty,
            recurrence_pattern=dto.recurrence_pattern,
            target_days_per_week=dto.target_days_per_week,
            preferred_time=dto.preferred_time,
            duration_minutes=dto.duration_minutes,
            # Reminders
            reminder_time=getattr(dto, "reminder_time", None),
            reminder_days=tuple(getattr(dto, "reminder_days", [])),
            reminder_enabled=getattr(dto, "reminder_enabled", False),
            # UID list fields REMOVED - relationships stored as graph edges only
            source_learning_step_uid=getattr(dto, "source_learning_step_uid", None),
            source_learning_path_uid=getattr(dto, "source_learning_path_uid", None),
            # reinforces_step_uids REMOVED - use (habit)-[:REINFORCES_STEP]->(ls)
            curriculum_practice_type=getattr(dto, "curriculum_practice_type", None),
            current_streak=dto.current_streak,
            best_streak=dto.best_streak,
            total_completions=dto.total_completions,
            total_attempts=dto.total_attempts,
            success_rate=dto.success_rate,
            last_completed=dto.last_completed,
            cue=dto.cue,
            routine=dto.routine,
            reward=dto.reward,
            reinforces_identity=getattr(dto, "reinforces_identity", None),
            identity_votes_cast=getattr(dto, "identity_votes_cast", 0),
            is_identity_habit=getattr(dto, "is_identity_habit", False),
            status=dto.status,
            priority=dto.priority,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            started_at=dto.started_at,
            completed_at=dto.completed_at,
            tags=tuple(dto.tags),
            metadata=getattr(dto, "metadata", {})
            or {},  # Copy metadata from DTO (rich context storage)
        )

    def to_dto(self) -> HabitDTO:
        """
        Convert to mutable DTO for updates.

        GRAPH-NATIVE: UID list fields set to empty lists.
        Service layer must populate from graph queries before API serialization.
        """
        return HabitDTO(
            uid=self.uid,
            user_uid=self.user_uid,
            name=self.name,
            description=self.description,
            polarity=self.polarity,
            category=self.category,
            difficulty=self.difficulty,
            recurrence_pattern=self.recurrence_pattern,
            target_days_per_week=self.target_days_per_week,
            preferred_time=self.preferred_time,
            duration_minutes=self.duration_minutes,
            # Reminders
            reminder_time=self.reminder_time,
            reminder_days=list(self.reminder_days),
            reminder_enabled=self.reminder_enabled,
            # Phase 2: Graph-native relationship fields removed from DTO
            # Query via HabitsRelationshipService instead:
            #   - get_habit_knowledge() for knowledge links
            #   - get_habit_goals() for goal links
            #   - get_habit_principles() for principle links
            #   - get_habit_prerequisites() for prerequisite chains
            current_streak=self.current_streak,
            best_streak=self.best_streak,
            total_completions=self.total_completions,
            total_attempts=self.total_attempts,
            success_rate=self.success_rate,
            last_completed=self.last_completed,
            cue=self.cue,
            routine=self.routine,
            reward=self.reward,
            reinforces_identity=self.reinforces_identity,
            identity_votes_cast=self.identity_votes_cast,
            is_identity_habit=self.is_identity_habit,
            status=self.status,
            priority=self.priority,
            created_at=self.created_at,
            updated_at=self.updated_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            tags=list(self.tags),
            metadata=self.metadata,  # Copy metadata to DTO (rich context storage)
        )

    # ==========================================================================
    # PHASE 1-4 INTEGRATION: GRAPH INTELLIGENCE
    # ==========================================================================

    def build_knowledge_reinforcement_query(self, depth: int = 2) -> str:
        """
        Build pure Cypher query for knowledge reinforcement

        Finds all knowledge units this habit reinforces.

        Args:
            depth: Maximum knowledge graph depth

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.PRACTICE, depth=depth
        )

    def build_goal_support_query(self) -> str:
        """
        Build pure Cypher query for goal support

        Finds goals this habit supports and progress impact.

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.HIERARCHICAL, depth=GraphDepth.NEIGHBORHOOD
        )

    def build_principle_alignment_query(self) -> str:
        """
        Build pure Cypher query for principle alignment

        Finds principles this habit embodies and alignment patterns.

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.RELATIONSHIP, depth=GraphDepth.NEIGHBORHOOD
        )

    def build_prerequisite_habits_query(self, depth: int = 3) -> str:
        """
        Build pure Cypher query for prerequisite habits

        Finds habits that should be established before this one.

        Args:
            depth: Maximum prerequisite depth

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.PREREQUISITE, depth=depth
        )

    def get_suggested_query_intent(self) -> QueryIntent:
        """
        Get suggested QueryIntent based on habit characteristics.

        Business rules:
        - Habits with prerequisites → PREREQUISITE (understand foundation)
        - Learning habits → PRACTICE (knowledge reinforcement)
        - Goal-supporting habits → HIERARCHICAL (progress tracking)
        - Principle-based habits → RELATIONSHIP (values alignment)
        - Default → PRACTICE (reinforcement patterns)

        Returns:
            Recommended QueryIntent for this habit

        GRAPH-NATIVE: Service layer must query graph to determine full intent.
        Use: backend.count_related() for all relationship types
        """
        # GRAPH QUERY REQUIRED for full determination
        # For now, use partial checks based on category only

        if self.category == HabitCategory.LEARNING:
            return QueryIntent.PRACTICE

        return (
            QueryIntent.PRACTICE
        )  # Default - service should use graph queries for better accuracy

    # ==========================================================================
    # GRAPHENTITY PROTOCOL IMPLEMENTATION (Phase 2)
    # ==========================================================================

    def explain_existence(self) -> str:
        """
        WHY does this habit exist? One-sentence reasoning.

        Returns:
            str: Explanation of habit's existence and purpose

        GRAPH-NATIVE: Service layer must query graph to build complete explanation.
        Use: backend.count_related() for SUPPORTS_GOAL, PRACTICES_KNOWLEDGE, ALIGNED_WITH_PRINCIPLE
        """
        # GRAPH QUERY REQUIRED: count SUPPORTS_GOAL relationships
        # GRAPH QUERY REQUIRED: count PRACTICES_KNOWLEDGE relationships
        # GRAPH QUERY REQUIRED: count ALIGNED_WITH_PRINCIPLE relationships

        return self.name  # Partial explanation - service should enrich with graph data

    def get_upstream_influences(self) -> list[dict]:
        """
        WHAT shaped this habit? (Scaffolding method - see HabitService for implementation)

        Returns:
            Upstream entities (principles, prerequisite habits, goals)

        GRAPH-NATIVE IMPLEMENTATION:
        This requires graph queries and must be called via service layer:

            result = await habit_service.get_upstream_influences(habit.uid)

        Service will query:
        - backend.get_related_uids(uid, "ALIGNED_WITH_PRINCIPLE", "outgoing")
        - backend.get_related_uids(uid, "REQUIRES_PREREQUISITE", "outgoing")
        - backend.get_related_uids(uid, "SUPPORTS_GOAL", "outgoing")

        Future enhancements:
        - Add Choice derivation for habits (tracking decision that created habit)
        - Add Knowledge requirements (prerequisite knowledge for habit)

        NOTE: This method exists for API discoverability and documentation.
        It intentionally returns [] to indicate service layer is required.
        """
        return []  # Service layer implementation required

    def get_downstream_impacts(self) -> list[dict]:
        """
        WHAT does this habit shape? (Scaffolding method - see HabitService for implementation)

        Returns:
            Downstream entities (dependent habits, goals, knowledge)

        GRAPH-NATIVE IMPLEMENTATION:
        This requires graph queries and must be called via service layer:

            result = await habit_service.get_downstream_impacts(habit.uid)

        Service will query:
        - backend.get_related_uids(uid, "SUPPORTS_GOAL", "outgoing")
        - backend.get_related_uids(uid, "PRACTICES_KNOWLEDGE", "outgoing")
        - backend.get_related_uids(uid, "REQUIRES_PREREQUISITE", "incoming") for dependent habits

        Future enhancements:
        - Track dependent habits that require this one as prerequisite
        - Track goal progress impact from habit completion
        - Track knowledge mastery improvement from practice

        NOTE: This method exists for API discoverability and documentation.
        It intentionally returns [] to indicate service layer is required.
        """
        return []  # Service layer implementation required

    def get_relationship_summary(self) -> dict:
        """
        Get comprehensive relationship context for this habit.

        Returns:
            Dict with explanation, upstream influences, and downstream impacts
        """
        return {
            "explanation": self.explain_existence(),
            "upstream": self.get_upstream_influences(),
            "downstream": self.get_downstream_impacts(),
            "upstream_count": len(self.get_upstream_influences()),
            "downstream_count": len(self.get_downstream_impacts()),
        }


# Import HabitDTO after Habit class is defined to avoid circular import
from core.models.habit.habit_dto import HabitDTO  # noqa: E402
