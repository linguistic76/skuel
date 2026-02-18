"""
Unified Knowledge Domain Model (Tier 3 - Core)
===============================================

"Ku is the heartbeat of SKUEL."

Immutable domain model for ALL knowledge in the system. 15 manifestations:

    Knowledge (shared):
        CURRICULUM      -> Admin-created shared knowledge
    Curriculum Structure:
        LEARNING_STEP   -> Step in a learning path
        LEARNING_PATH   -> Ordered sequence of steps
    Content Processing:
        SUBMISSION      -> Student submission (user-owned)
        AI_REPORT       -> AI-derived from submission
        FEEDBACK_REPORT -> Teacher feedback on submission
    Activity (user-owned):
        TASK            -> Knowledge about what needs doing
        GOAL            -> Knowledge about where you're heading
        HABIT           -> Knowledge about what you practice
        EVENT           -> Knowledge about what you attend
        CHOICE          -> Knowledge about decisions you make
        PRINCIPLE       -> Knowledge about what you believe
    Destination:
        LIFE_PATH       -> Knowledge about your life direction

Inherits ~48 common fields + methods from KuBase.
Adds ~90 domain-specific fields + domain methods.

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
See: /.claude/plans/ku-decomposition-domain-types.md
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.ku.ku_dto import KuDTO

from core.models.enums.ku_enums import (
    AlignmentLevel,
    ChoiceType,
    GoalTimeframe,
    GoalType,
    HabitCategory,
    HabitDifficulty,
    HabitPolarity,
    KuStatus,
    KuType,
    LpType,
    MeasurementType,
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
    ProcessorType,
    StepDifficulty,
)
from core.models.ku.ku_base import KuBase
from core.models.ku.ku_nested_types import (
    AlignmentAssessment,
    ChoiceOption,
    Milestone,
    PrincipleExpression,
)

# =============================================================================
# TYPE CLASS MAP — dispatcher for Ku decomposition (Phase 1+)
#
# Maps KuType to domain-specific subclass. Used by from_dto dispatcher and
# cross-domain deserialization. During incremental migration, only migrated
# types appear here — unmigrated types fall back to Ku (god object).
# =============================================================================
# Populated after class definitions to avoid circular imports
KU_TYPE_CLASS_MAP: dict[KuType, type[KuBase]] = {}


def _populate_type_class_map() -> None:
    """Populate KU_TYPE_CLASS_MAP after all classes are defined."""
    from core.models.ku.ku_goal import GoalKu
    from core.models.ku.ku_habit import HabitKu
    from core.models.ku.ku_task import TaskKu

    KU_TYPE_CLASS_MAP[KuType.TASK] = TaskKu
    KU_TYPE_CLASS_MAP[KuType.GOAL] = GoalKu
    KU_TYPE_CLASS_MAP[KuType.HABIT] = HabitKu


# Called at module load time (after Ku class is defined, at bottom of file)


@dataclass(frozen=True)
class Ku(KuBase):
    """
    Immutable domain model representing a Knowledge Unit.

    Inherits ~48 common fields + methods from KuBase (identity, content,
    status, learning, sharing, substance, meta, embedding).

    Adds ~90 domain-specific fields in 10 sections:
    - File (4): original_filename, file_path, file_size, file_type
    - Processing (8): processor_type, processing timestamps, instructions
    - Feedback (3): feedback, feedback_generated_at, subject_uid
    - Scheduling (37): dates, times, recurrence, reminders, event logistics
    - Progress (26): goal tracking, milestones, task hierarchy, learning integration
    - Streak (20): habit tracking, behavioral science, identity
    - Decision (13): choice options, criteria, outcome tracking
    - Conviction (19): principle expressions, alignment, philosophical context
    - Alignment (10): life path designation, dimension scores
    - Curriculum Structure (13): LS/LP fields -- mastery, sequence, path type
    """

    # =========================================================================
    # FILE (SUBMISSION uploads)
    # =========================================================================
    original_filename: str | None = None
    file_path: str | None = None
    file_size: int | None = None
    file_type: str | None = None  # MIME type (e.g., "audio/mpeg")

    # =========================================================================
    # PROCESSING
    # =========================================================================
    processor_type: ProcessorType | None = None
    processing_started_at: datetime | None = None  # type: ignore[assignment]
    processing_completed_at: datetime | None = None  # type: ignore[assignment]
    processing_error: str | None = None
    processed_content: str | None = None
    processed_file_path: str | None = None
    instructions: str | None = None  # LLM processing instructions
    max_retention: int | None = None  # FIFO cleanup limit (None = permanent)

    # =========================================================================
    # FEEDBACK
    # =========================================================================
    feedback: str | None = None
    feedback_generated_at: datetime | None = None  # type: ignore[assignment]
    subject_uid: str | None = None  # Who the feedback is about

    # =========================================================================
    # SCHEDULING (TASK, EVENT, HABIT, CHOICE)
    # Dates, times, recurrence, reminders, event logistics
    # =========================================================================
    due_date: date | None = None  # type: ignore[assignment]  # TASK deadline
    scheduled_date: date | None = None  # type: ignore[assignment]  # TASK planned date
    completion_date: date | None = None  # type: ignore[assignment]  # TASK actual completion
    event_date: date | None = None  # type: ignore[assignment]  # EVENT date
    start_time: time | None = None  # EVENT start
    end_time: time | None = None  # EVENT end
    duration_minutes: int | None = None  # TASK/HABIT expected duration
    actual_minutes: int | None = None  # TASK actual time spent
    decision_deadline: datetime | None = None  # type: ignore[assignment]  # CHOICE deadline

    # Event logistics
    event_type: str | None = None  # EVENT type (e.g., "PERSONAL", "MEETING")
    location: str | None = None  # EVENT location
    is_online: bool = False  # EVENT online flag
    meeting_url: str | None = None  # EVENT video call URL

    # Recurrence (TASK, HABIT, EVENT)
    recurrence_pattern: str | None = None  # RecurrencePattern enum value
    recurrence_end_date: date | None = None  # type: ignore[assignment]
    recurrence_parent_uid: str | None = None
    target_days_per_week: int | None = None  # HABIT frequency
    preferred_time: str | None = None  # HABIT preferred time of day

    # Reminders
    reminder_time: str | None = None  # HABIT reminder time
    reminder_days: tuple[str, ...] = ()  # HABIT reminder days
    reminder_enabled: bool = False  # HABIT reminder toggle
    reminder_minutes: int | None = None  # EVENT reminder lead time
    reminder_sent: bool = False  # EVENT reminder status

    # Attendees (EVENT)
    attendee_emails: tuple[str, ...] = ()
    max_attendees: int | None = None

    # Scheduling links
    scheduled_event_uid: str | None = None  # TASK linked event

    # =========================================================================
    # PROGRESS (GOAL, TASK)
    # Goal tracking, milestones, task hierarchy, learning integration
    # =========================================================================
    vision_statement: str | None = None  # GOAL/CHOICE/LIFE_PATH vision

    # Goal classification
    goal_type: GoalType | None = None
    timeframe: GoalTimeframe | None = None
    measurement_type: MeasurementType | None = None

    # Goal measurement
    target_value: float | None = None
    current_value: float = 0.0
    unit_of_measurement: str | None = None

    # Goal timeline
    start_date: date | None = None  # type: ignore[assignment]
    target_date: date | None = None  # type: ignore[assignment]
    achieved_date: date | None = None  # type: ignore[assignment]

    # Goal milestones
    milestones: tuple[Milestone, ...] = ()
    progress_percentage: float = 0.0
    last_progress_update: datetime | None = None  # type: ignore[assignment]
    progress_history: tuple[dict, ...] = ()  # type: ignore[assignment]

    # Goal motivation
    why_important: str | None = None  # GOAL/PRINCIPLE
    success_criteria: str | None = None
    potential_obstacles: tuple[str, ...] = ()
    strategies: tuple[str, ...] = ()

    # Task hierarchy
    parent_uid: str | None = None  # TASK parent (not derivation chain)
    project: str | None = None  # TASK project grouping
    assignee: str | None = None  # TASK assignee

    # Cross-domain links
    fulfills_goal_uid: str | None = None  # TASK -> GOAL
    reinforces_habit_uid: str | None = None  # TASK/EVENT -> HABIT
    source_learning_step_uid: str | None = None  # TASK/HABIT/EVENT -> LS
    source_learning_path_uid: str | None = None  # GOAL/HABIT/EVENT -> LP

    # Progress impact
    goal_progress_contribution: float = 0.0  # TASK contribution to GOAL
    knowledge_mastery_check: bool = False  # TASK knowledge verification
    habit_streak_maintainer: bool = False  # TASK maintains habit streak
    completion_updates_goal: bool = False  # TASK completion updates GOAL progress
    curriculum_driven: bool = False  # GOAL derived from curriculum
    curriculum_practice_type: str | None = None  # HABIT curriculum connection

    # Knowledge intelligence (TASK)
    knowledge_confidence_scores: dict[str, float] | None = None
    knowledge_inference_metadata: dict[str, Any] | None = None
    learning_opportunities_count: int = 0

    # Choice integration (GOAL)
    inspired_by_choice_uid: str | None = None
    selected_choice_option_uid: str | None = None

    # Event curriculum integration
    milestone_celebration_for_goal: str | None = None  # EVENT -> GOAL milestone
    is_milestone_event: bool = False
    milestone_type: str | None = None
    curriculum_week: int | None = None

    # Event quality tracking
    habit_completion_quality: int | None = None
    knowledge_retention_check: bool = False
    recurrence_maintains_habit: bool = False
    skip_breaks_habit_streak: bool = False

    # =========================================================================
    # STREAK (HABIT)
    # Habit tracking, behavioral science, identity
    # =========================================================================
    polarity: HabitPolarity | None = None  # BUILD, BREAK, NEUTRAL
    habit_category: HabitCategory | None = None
    habit_difficulty: HabitDifficulty | None = None

    # Streak tracking
    current_streak: int = 0
    best_streak: int = 0
    total_completions: int = 0
    total_attempts: int = 0
    success_rate: float = 0.0
    last_completed: datetime | None = None  # type: ignore[assignment]

    # Behavioral science (Atomic Habits)
    cue: str | None = None  # Habit loop: cue
    routine: str | None = None  # Habit loop: routine
    reward: str | None = None  # Habit loop: reward

    # Identity
    reinforces_identity: str | None = None  # "I am the type of person who..."
    identity_votes_cast: int = 0
    is_identity_habit: bool = False
    target_identity: str | None = None  # GOAL identity target
    identity_evidence_required: int = 0  # GOAL evidence needed

    # Lifecycle
    started_at: datetime | None = None  # type: ignore[assignment]  # HABIT start
    completed_at: datetime | None = None  # type: ignore[assignment]  # HABIT completion

    # =========================================================================
    # DECISION (CHOICE)
    # Choice options, criteria, outcome tracking
    # =========================================================================
    choice_type: ChoiceType | None = None
    options: tuple[ChoiceOption, ...] = ()
    selected_option_uid: str | None = None
    decision_rationale: str | None = None

    # Decision context
    decision_criteria: tuple[str, ...] = ()  # CHOICE/PRINCIPLE
    constraints: tuple[str, ...] = ()
    stakeholders: tuple[str, ...] = ()

    # Decision timing
    decided_at: datetime | None = None  # type: ignore[assignment]

    # Outcome
    satisfaction_score: int | None = None
    actual_outcome: str | None = None
    lessons_learned: tuple[str, ...] = ()

    # Choice-curriculum integration
    inspiration_type: str | None = None
    expands_possibilities: bool = False

    # =========================================================================
    # CONVICTION (PRINCIPLE)
    # Principle expressions, alignment, philosophical context
    # =========================================================================
    statement: str | None = None  # Core principle statement

    # Classification
    principle_category: PrincipleCategory | None = None
    principle_source: PrincipleSource | None = None
    strength: PrincipleStrength | None = None

    # Philosophical context
    tradition: str | None = None  # Philosophical/religious tradition
    original_source: str | None = None  # Source text/author
    personal_interpretation: str | None = None

    # Expressions & applications
    expressions: tuple[PrincipleExpression, ...] = ()
    key_behaviors: tuple[str, ...] = ()

    # Alignment tracking
    current_alignment: AlignmentLevel | None = None
    alignment_history: tuple[AlignmentAssessment, ...] = ()
    last_review_date: date | None = None  # type: ignore[assignment]

    # Conflicts & tensions
    potential_conflicts: tuple[str, ...] = ()
    conflicting_principles: tuple[str, ...] = ()
    resolution_strategies: tuple[str, ...] = ()

    # Personal reflection
    origin_story: str | None = None
    evolution_notes: str | None = None

    # Principle status
    is_active: bool = True
    adopted_date: date | None = None  # type: ignore[assignment]

    # =========================================================================
    # ALIGNMENT (LIFE_PATH)
    # Life path designation and dimension scores
    # =========================================================================
    life_path_uid: str | None = None  # LP designated as life path
    designated_at: datetime | None = None  # type: ignore[assignment]

    # Scores
    alignment_score: float = 0.0  # Overall 0.0-1.0
    word_action_gap: float = 0.0  # Vision vs. behavior gap
    alignment_level: AlignmentLevel | None = None

    # Dimension scores (5 dimensions)
    knowledge_alignment: float = 0.0
    activity_alignment: float = 0.0
    goal_alignment: float = 0.0
    principle_alignment: float = 0.0
    momentum: float = 0.0

    # Vision
    vision_themes: tuple[str, ...] = ()
    vision_captured_at: datetime | None = None  # type: ignore[assignment]

    # =========================================================================
    # CURRICULUM STRUCTURE (LEARNING_STEP, LEARNING_PATH)
    # =========================================================================
    intent: str | None = None  # LS learning intent
    primary_knowledge_uids: tuple[str, ...] = ()  # LS primary KU references
    supporting_knowledge_uids: tuple[str, ...] = ()  # LS supporting KU references
    learning_path_uid: str | None = None  # LS -> LP relationship
    sequence: int | None = None  # LS order in path

    # Mastery
    mastery_threshold: float = 0.7  # LS mastery target
    current_mastery: float = 0.0  # LS current progress
    estimated_hours: float | None = None  # LS/LP time estimate
    step_difficulty: StepDifficulty | None = None  # LS difficulty

    # Path configuration (LP)
    path_type: LpType | None = None
    outcomes: tuple[str, ...] = ()  # LP expected outcomes
    checkpoint_week_intervals: tuple[int, ...] = ()  # LP milestone intervals

    # =========================================================================
    # DOMAIN-SPECIFIC METHODS
    # =========================================================================

    def get_processing_duration(self) -> float | None:
        """Get processing duration in seconds, or None if not applicable."""
        if not self.processing_started_at or not self.processing_completed_at:
            return None
        delta = self.processing_completed_at - self.processing_started_at
        if isinstance(delta, timedelta):
            return delta.total_seconds()
        try:
            return float(delta.seconds)
        except AttributeError:
            try:
                return float(delta)
            except (TypeError, ValueError):
                return None

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of content (body text or processed content)."""
        text = self.content or self.processed_content or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    @property
    def category(self) -> str | None:
        """Domain-aware category: habit_category, principle_category, or domain."""
        if self.ku_type == KuType.HABIT and self.habit_category:
            return self.habit_category.value
        if self.ku_type == KuType.PRINCIPLE and self.principle_category:
            return self.principle_category.value
        if self.ku_type == KuType.CHOICE and self.choice_type:
            return self.choice_type.value
        return self.domain.value if self.domain else None

    @property
    def parent_goal_uid(self) -> str | None:
        """Alias for fulfills_goal_uid."""
        return self.fulfills_goal_uid

    # --- Goal methods ---

    def calculate_progress(self) -> float:
        """Calculate goal progress (0.0-1.0)."""
        if self.measurement_type == MeasurementType.PERCENTAGE:
            return min(1.0, self.progress_percentage / 100.0)
        if self.target_value and self.target_value > 0:
            return min(1.0, self.current_value / self.target_value)
        return self.progress_percentage / 100.0 if self.progress_percentage else 0.0

    def get_days_remaining(self) -> int | None:
        """Days until target_date or due_date."""
        target = self.target_date or self.due_date
        if not target:
            return None
        delta = target - date.today()
        return delta.days

    def days_remaining(self) -> int:
        """Days until target_date/due_date (0 if none set or past)."""
        result = self.get_days_remaining()
        return max(0, result) if result is not None else 0

    def expected_progress_percentage(self) -> float:
        """Expected progress based on elapsed time vs total timeline."""
        if not self.start_date or not self.target_date:
            return 0.0
        total = (self.target_date - self.start_date).days
        if total <= 0:
            return 100.0
        elapsed = (date.today() - self.start_date).days
        return min(100.0, max(0.0, (elapsed / total) * 100.0))

    def is_on_track(self) -> bool:
        """Check if progress >= expected progress."""
        expected = self.expected_progress_percentage()
        return self.progress_percentage >= expected if expected > 0 else True

    def is_overdue(self) -> bool:
        """Check if past due_date/target_date without completion."""
        if self.is_completed:
            return False
        remaining = self.get_days_remaining()
        return remaining is not None and remaining < 0

    def is_achieved(self) -> bool:
        """Check if goal is achieved (completed status)."""
        return self.status == KuStatus.COMPLETED

    def is_past(self) -> bool:
        """Check if event date is in the past."""
        if self.event_date:
            return self.event_date < date.today()
        target = self.target_date or self.due_date
        if target:
            return target < date.today()
        return False

    def calculate_system_strength(
        self, habit_success_rates: dict[str, float] | None = None
    ) -> float:
        """Calculate goal system strength based on supporting habits."""
        if not habit_success_rates:
            return 0.0
        if not habit_success_rates:
            return 0.0
        avg_rate = sum(habit_success_rates.values()) / len(habit_success_rates)
        return min(1.0, avg_rate)

    def calculate_habit_velocity(
        self, habit_completion_counts: dict[str, int] | None = None
    ) -> float:
        """Calculate velocity of habit completion toward goal."""
        if not habit_completion_counts:
            return 0.0
        total = sum(habit_completion_counts.values())
        return min(1.0, total / max(1, len(habit_completion_counts) * 30))

    def diagnose_system_health(
        self, habit_success_rates: dict[str, float] | None = None
    ) -> dict[str, Any]:
        """Diagnose the health of a goal's habit system."""
        strength = self.calculate_system_strength(habit_success_rates)
        return {
            "system_strength": strength,
            "health": "strong" if strength >= 0.7 else "moderate" if strength >= 0.4 else "weak",
            "habit_count": len(habit_success_rates) if habit_success_rates else 0,
        }

    def explain_existence(self) -> str:
        """Explain why this entity exists."""
        return (
            self.why_important
            or self.description
            or self.summary
            or f"{self.ku_type.value}: {self.title}"
        )

    # --- Task methods ---

    def impact_score(self) -> float:
        """Calculate task impact score based on priority and knowledge connections."""
        from contextlib import suppress

        from core.models.enums.activity_enums import Priority

        base = 0.5
        if self.priority:
            with suppress(ValueError, KeyError):
                base = Priority(self.priority).to_numeric() / 4.0
        if self.fulfills_goal_uid:
            base = min(1.0, base + 0.2)
        return base

    def learning_alignment_score(self) -> float:
        """Score for how well a task aligns with learning paths."""
        score = 0.0
        if self.source_learning_step_uid:
            score += 0.5
        if self.source_learning_path_uid:
            score += 0.3
        if self.knowledge_mastery_check:
            score += 0.2
        return min(1.0, score)

    def get_combined_knowledge_uids(self) -> set[str]:
        """Get all knowledge UIDs related to this entity."""
        uids: set[str] = set()
        if self.primary_knowledge_uids:
            uids.update(self.primary_knowledge_uids)
        if self.supporting_knowledge_uids:
            uids.update(self.supporting_knowledge_uids)
        return uids

    def get_all_knowledge_uids(self) -> set[str]:
        """Alias for get_combined_knowledge_uids."""
        return self.get_combined_knowledge_uids()

    # --- Habit methods ---

    def calculate_consistency_score(self) -> float:
        """Calculate habit consistency based on streak and success rate."""
        if self.total_attempts == 0:
            return 0.0
        streak_factor = min(1.0, self.current_streak / 30.0)
        rate_factor = self.success_rate
        return streak_factor * 0.4 + rate_factor * 0.6

    @property
    def is_keystone(self) -> bool:
        """Check if this is a keystone habit (high impact)."""
        return self.is_identity_habit or self.calculate_consistency_score() >= 0.8

    def should_do_today(self) -> bool:
        """Check if a habit should be done today."""
        if not self.is_active:
            return False
        if self.last_completed:
            days_since = (datetime.now() - self.last_completed).days
            if self.target_days_per_week:
                interval = max(1, 7 // self.target_days_per_week)
                return days_since >= interval
        return True

    def get_effort_score(self) -> float:
        """Get habit effort score (0.0-1.0) based on difficulty."""
        if self.habit_difficulty:
            mapping = {
                HabitDifficulty.TRIVIAL: 0.1,
                HabitDifficulty.EASY: 0.3,
                HabitDifficulty.MODERATE: 0.5,
                HabitDifficulty.CHALLENGING: 0.7,
                HabitDifficulty.HARD: 0.9,
            }
            return mapping.get(self.habit_difficulty, 0.5)
        return 0.5

    def is_identity_based(self) -> bool:
        """Check if this is an identity-based habit."""
        return self.is_identity_habit

    def get_atomic_habits_analysis(self) -> dict[str, Any]:
        """Get Atomic Habits analysis for this habit."""
        return {
            "cue": self.cue or "Not defined",
            "routine": self.routine or "Not defined",
            "reward": self.reward or "Not defined",
            "identity": self.reinforces_identity or "Not defined",
            "has_complete_loop": bool(self.cue and self.routine and self.reward),
            "is_identity_based": self.is_identity_habit,
        }

    # --- Choice methods ---

    def has_high_stakes(self) -> bool:
        """Check if choice has high stakes."""
        return bool(self.stakeholders) or bool(self.constraints)

    def calculate_decision_complexity(self) -> float:
        """Calculate decision complexity (0.0-1.0)."""
        score = 0.0
        if self.options:
            score += min(0.3, len(self.options) * 0.1)
        if self.decision_criteria:
            score += min(0.3, len(self.decision_criteria) * 0.1)
        if self.stakeholders:
            score += min(0.2, len(self.stakeholders) * 0.1)
        if self.constraints:
            score += min(0.2, len(self.constraints) * 0.1)
        return min(1.0, score)

    def get_decision_quality_score(self) -> float:
        """Get quality score for a decision."""
        if not self.decided_at:
            return 0.0
        score = 0.3  # Base for having decided
        if self.decision_rationale:
            score += 0.3
        if self.satisfaction_score:
            score += 0.2 * (self.satisfaction_score / 5.0)
        if self.actual_outcome:
            score += 0.2
        return min(1.0, score)

    # --- Principle methods ---

    def is_well_aligned(self) -> bool:
        """Check if principle is well-aligned."""
        return self.current_alignment in (AlignmentLevel.ALIGNED, AlignmentLevel.FLOURISHING)

    def has_alignment_issues(self) -> bool:
        """Check if principle has alignment issues."""
        return self.current_alignment in (AlignmentLevel.DRIFTING, AlignmentLevel.MISALIGNED)

    def has_concrete_behaviors(self) -> bool:
        """Check if principle has concrete key behaviors defined."""
        return len(self.key_behaviors) > 0

    def is_actionable(self) -> bool:
        """Check if principle is actionable (has behaviors and expressions)."""
        return self.has_concrete_behaviors() or len(self.expressions) > 0

    def assess_alignment(self) -> dict[str, Any]:
        """Assess principle alignment status."""
        return {
            "level": self.current_alignment.value if self.current_alignment else "unknown",
            "is_well_aligned": self.is_well_aligned(),
            "has_issues": self.has_alignment_issues(),
            "behaviors_defined": len(self.key_behaviors),
            "expressions_count": len(self.expressions),
        }

    # --- Knowledge methods ---

    def calculate_knowledge_complexity(self) -> float:
        """Calculate knowledge complexity (0.0-1.0)."""
        return self.difficulty_rating

    def is_knowledge_bridge(self) -> bool:
        """Check if this KU bridges multiple domains."""
        return len(self.semantic_links) >= 3

    def validates_knowledge_mastery(self) -> bool:
        """Check if this entity validates knowledge mastery."""
        return self.knowledge_mastery_check

    def calculate_learning_impact(self) -> float:
        """Calculate learning impact score."""
        score = 0.0
        if self.primary_knowledge_uids:
            score += min(0.4, len(self.primary_knowledge_uids) * 0.1)
        if self.supporting_knowledge_uids:
            score += min(0.3, len(self.supporting_knowledge_uids) * 0.1)
        score += self.difficulty_rating * 0.3
        return min(1.0, score)

    # --- Event methods ---

    def start_datetime(self) -> datetime | None:
        """Get event start as datetime."""
        if self.event_date and self.start_time:
            return datetime.combine(self.event_date, self.start_time)
        return None

    def end_datetime(self) -> datetime | None:
        """Get event end as datetime."""
        if self.event_date and self.end_time:
            return datetime.combine(self.event_date, self.end_time)
        if self.event_date and self.start_time and self.duration_minutes:
            start = datetime.combine(self.event_date, self.start_time)
            return start + timedelta(minutes=self.duration_minutes)
        return None

    def overlaps_with(self, other: "Ku") -> bool:
        """Check if two events overlap in time."""
        my_start = self.start_datetime()
        my_end = self.end_datetime()
        other_start = other.start_datetime()
        other_end = other.end_datetime()
        if not all([my_start, my_end, other_start, other_end]):
            return False
        return my_start < other_end and other_start < my_end  # type: ignore[operator]

    # --- Learning Path methods ---

    @property
    def steps(self) -> tuple[()]:
        """LP steps are graph relationships, not model attributes. Returns empty tuple."""
        return ()

    @property
    def goal(self) -> str:
        """LP goal -- alias for description or vision_statement."""
        return self.description or self.vision_statement or ""

    # --- Cross-domain query helpers ---

    @property
    def is_from_learning_step(self) -> bool:
        """Check if this entity originated from a learning step."""
        return self.source_learning_step_uid is not None

    @property
    def fulfills_learning_step(self) -> bool:
        """Check if this entity fulfills a learning step."""
        return self.source_learning_step_uid is not None

    # =========================================================================
    # FACTORY METHODS
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "KuDTO") -> "Ku":
        """
        Create immutable Ku from mutable DTO.

        Converts mutable lists to immutable tuples.
        All business fields are copied -- lossless round-trip with to_dto().
        """

        return cls(
            # Identity (from KuBase)
            uid=dto.uid,
            title=dto.title,
            ku_type=dto.ku_type,
            user_uid=dto.user_uid,
            parent_ku_uid=dto.parent_ku_uid,
            domain=dto.domain,
            created_by=dto.created_by,
            # Content (from KuBase)
            content=dto.content,
            summary=dto.summary,
            description=dto.description,
            word_count=dto.word_count,
            # File
            original_filename=dto.original_filename,
            file_path=dto.file_path,
            file_size=dto.file_size,
            file_type=dto.file_type,
            # Processing
            status=dto.status,
            processor_type=dto.processor_type,
            processing_started_at=dto.processing_started_at,
            processing_completed_at=dto.processing_completed_at,
            processing_error=dto.processing_error,
            processed_content=dto.processed_content,
            processed_file_path=dto.processed_file_path,
            instructions=dto.instructions,
            # Feedback
            feedback=dto.feedback,
            feedback_generated_at=dto.feedback_generated_at,
            subject_uid=dto.subject_uid,
            # Learning (from KuBase)
            complexity=dto.complexity,
            learning_level=dto.learning_level,
            sel_category=dto.sel_category,
            quality_score=dto.quality_score,
            estimated_time_minutes=dto.estimated_time_minutes,
            difficulty_rating=dto.difficulty_rating,
            semantic_links=tuple(dto.semantic_links),
            priority=dto.priority,
            # Sharing (from KuBase)
            visibility=dto.visibility,
            # Scheduling
            due_date=dto.due_date,
            scheduled_date=dto.scheduled_date,
            completion_date=dto.completion_date,
            event_date=dto.event_date,
            start_time=dto.start_time,
            end_time=dto.end_time,
            duration_minutes=dto.duration_minutes,
            actual_minutes=dto.actual_minutes,
            decision_deadline=dto.decision_deadline,
            event_type=dto.event_type,
            location=dto.location,
            is_online=dto.is_online,
            meeting_url=dto.meeting_url,
            recurrence_pattern=dto.recurrence_pattern,
            recurrence_end_date=dto.recurrence_end_date,
            recurrence_parent_uid=dto.recurrence_parent_uid,
            target_days_per_week=dto.target_days_per_week,
            preferred_time=dto.preferred_time,
            reminder_time=dto.reminder_time,
            reminder_days=tuple(dto.reminder_days),
            reminder_enabled=dto.reminder_enabled,
            reminder_minutes=dto.reminder_minutes,
            reminder_sent=dto.reminder_sent,
            attendee_emails=tuple(dto.attendee_emails),
            max_attendees=dto.max_attendees,
            scheduled_event_uid=dto.scheduled_event_uid,
            # Progress
            vision_statement=dto.vision_statement,
            goal_type=dto.goal_type,
            timeframe=dto.timeframe,
            measurement_type=dto.measurement_type,
            target_value=dto.target_value,
            current_value=dto.current_value,
            unit_of_measurement=dto.unit_of_measurement,
            start_date=dto.start_date,
            target_date=dto.target_date,
            achieved_date=dto.achieved_date,
            milestones=tuple(dto.milestones),
            progress_percentage=dto.progress_percentage,
            last_progress_update=dto.last_progress_update,
            progress_history=tuple(dto.progress_history),
            why_important=dto.why_important,
            success_criteria=dto.success_criteria,
            potential_obstacles=tuple(dto.potential_obstacles),
            strategies=tuple(dto.strategies),
            parent_uid=dto.parent_uid,
            project=dto.project,
            assignee=dto.assignee,
            fulfills_goal_uid=dto.fulfills_goal_uid,
            reinforces_habit_uid=dto.reinforces_habit_uid,
            source_learning_step_uid=dto.source_learning_step_uid,
            source_learning_path_uid=dto.source_learning_path_uid,
            goal_progress_contribution=dto.goal_progress_contribution,
            knowledge_mastery_check=dto.knowledge_mastery_check,
            habit_streak_maintainer=dto.habit_streak_maintainer,
            completion_updates_goal=dto.completion_updates_goal,
            curriculum_driven=dto.curriculum_driven,
            curriculum_practice_type=dto.curriculum_practice_type,
            knowledge_confidence_scores=dto.knowledge_confidence_scores,
            knowledge_inference_metadata=dto.knowledge_inference_metadata,
            learning_opportunities_count=dto.learning_opportunities_count,
            inspired_by_choice_uid=dto.inspired_by_choice_uid,
            selected_choice_option_uid=dto.selected_choice_option_uid,
            milestone_celebration_for_goal=dto.milestone_celebration_for_goal,
            is_milestone_event=dto.is_milestone_event,
            milestone_type=dto.milestone_type,
            curriculum_week=dto.curriculum_week,
            habit_completion_quality=dto.habit_completion_quality,
            knowledge_retention_check=dto.knowledge_retention_check,
            recurrence_maintains_habit=dto.recurrence_maintains_habit,
            skip_breaks_habit_streak=dto.skip_breaks_habit_streak,
            # Streak
            polarity=dto.polarity,
            habit_category=dto.habit_category,
            habit_difficulty=dto.habit_difficulty,
            current_streak=dto.current_streak,
            best_streak=dto.best_streak,
            total_completions=dto.total_completions,
            total_attempts=dto.total_attempts,
            success_rate=dto.success_rate,
            last_completed=dto.last_completed,
            cue=dto.cue,
            routine=dto.routine,
            reward=dto.reward,
            reinforces_identity=dto.reinforces_identity,
            identity_votes_cast=dto.identity_votes_cast,
            is_identity_habit=dto.is_identity_habit,
            target_identity=dto.target_identity,
            identity_evidence_required=dto.identity_evidence_required,
            started_at=dto.started_at,
            completed_at=dto.completed_at,
            # Decision
            choice_type=dto.choice_type,
            options=tuple(dto.options),
            selected_option_uid=dto.selected_option_uid,
            decision_rationale=dto.decision_rationale,
            decision_criteria=tuple(dto.decision_criteria),
            constraints=tuple(dto.constraints),
            stakeholders=tuple(dto.stakeholders),
            decided_at=dto.decided_at,
            satisfaction_score=dto.satisfaction_score,
            actual_outcome=dto.actual_outcome,
            lessons_learned=tuple(dto.lessons_learned),
            inspiration_type=dto.inspiration_type,
            expands_possibilities=dto.expands_possibilities,
            # Conviction
            statement=dto.statement,
            principle_category=dto.principle_category,
            principle_source=dto.principle_source,
            strength=dto.strength,
            tradition=dto.tradition,
            original_source=dto.original_source,
            personal_interpretation=dto.personal_interpretation,
            expressions=tuple(dto.expressions),
            key_behaviors=tuple(dto.key_behaviors),
            current_alignment=dto.current_alignment,
            alignment_history=tuple(dto.alignment_history),
            last_review_date=dto.last_review_date,
            potential_conflicts=tuple(dto.potential_conflicts),
            conflicting_principles=tuple(dto.conflicting_principles),
            resolution_strategies=tuple(dto.resolution_strategies),
            origin_story=dto.origin_story,
            evolution_notes=dto.evolution_notes,
            is_active=dto.is_active,
            adopted_date=dto.adopted_date,
            # Alignment
            life_path_uid=dto.life_path_uid,
            designated_at=dto.designated_at,
            alignment_score=dto.alignment_score,
            word_action_gap=dto.word_action_gap,
            alignment_level=dto.alignment_level,
            knowledge_alignment=dto.knowledge_alignment,
            activity_alignment=dto.activity_alignment,
            goal_alignment=dto.goal_alignment,
            principle_alignment=dto.principle_alignment,
            momentum=dto.momentum,
            vision_themes=tuple(dto.vision_themes),
            vision_captured_at=dto.vision_captured_at,
            # Curriculum Structure
            intent=dto.intent,
            primary_knowledge_uids=tuple(dto.primary_knowledge_uids),
            supporting_knowledge_uids=tuple(dto.supporting_knowledge_uids),
            learning_path_uid=dto.learning_path_uid,
            sequence=dto.sequence,
            mastery_threshold=dto.mastery_threshold,
            current_mastery=dto.current_mastery,
            estimated_hours=dto.estimated_hours,
            step_difficulty=dto.step_difficulty,
            path_type=dto.path_type,
            outcomes=tuple(dto.outcomes),
            checkpoint_week_intervals=tuple(dto.checkpoint_week_intervals),
            # Substance tracking (from KuBase)
            times_applied_in_tasks=dto.times_applied_in_tasks,
            times_practiced_in_events=dto.times_practiced_in_events,
            times_built_into_habits=dto.times_built_into_habits,
            journal_reflections_count=dto.journal_reflections_count,
            choices_informed_count=dto.choices_informed_count,
            last_applied_date=dto.last_applied_date,
            last_practiced_date=dto.last_practiced_date,
            last_built_into_habit_date=dto.last_built_into_habit_date,
            last_reflected_date=dto.last_reflected_date,
            last_choice_informed_date=dto.last_choice_informed_date,
            # Meta (from KuBase)
            tags=tuple(dto.tags),
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            metadata=dto.metadata if dto.metadata is not None else {},
        )

    def to_dto(self) -> "KuDTO":
        """
        Convert to mutable DTO for data operations.

        Converts immutable tuples back to mutable lists.
        All business fields are copied -- lossless round-trip with from_dto().
        """
        from core.models.ku.ku_dto import KuDTO

        return KuDTO(
            # Identity (from KuBase)
            uid=self.uid,
            title=self.title,
            ku_type=self.ku_type,
            user_uid=self.user_uid,
            parent_ku_uid=self.parent_ku_uid,
            domain=self.domain,
            created_by=self.created_by,
            # Content (from KuBase)
            content=self.content,
            summary=self.summary,
            description=self.description,
            word_count=self.word_count,
            # File
            original_filename=self.original_filename,
            file_path=self.file_path,
            file_size=self.file_size,
            file_type=self.file_type,
            # Processing
            status=self.status,
            processor_type=self.processor_type,
            processing_started_at=self.processing_started_at,
            processing_completed_at=self.processing_completed_at,
            processing_error=self.processing_error,
            processed_content=self.processed_content,
            processed_file_path=self.processed_file_path,
            instructions=self.instructions,
            # Feedback
            feedback=self.feedback,
            feedback_generated_at=self.feedback_generated_at,
            subject_uid=self.subject_uid,
            # Learning (from KuBase)
            complexity=self.complexity,
            learning_level=self.learning_level,
            sel_category=self.sel_category,
            quality_score=self.quality_score,
            estimated_time_minutes=self.estimated_time_minutes,
            difficulty_rating=self.difficulty_rating,
            semantic_links=list(self.semantic_links),
            priority=self.priority,
            # Sharing (from KuBase)
            visibility=self.visibility,
            # Scheduling
            due_date=self.due_date,
            scheduled_date=self.scheduled_date,
            completion_date=self.completion_date,
            event_date=self.event_date,
            start_time=self.start_time,
            end_time=self.end_time,
            duration_minutes=self.duration_minutes,
            actual_minutes=self.actual_minutes,
            decision_deadline=self.decision_deadline,
            event_type=self.event_type,
            location=self.location,
            is_online=self.is_online,
            meeting_url=self.meeting_url,
            recurrence_pattern=self.recurrence_pattern,
            recurrence_end_date=self.recurrence_end_date,
            recurrence_parent_uid=self.recurrence_parent_uid,
            target_days_per_week=self.target_days_per_week,
            preferred_time=self.preferred_time,
            reminder_time=self.reminder_time,
            reminder_days=list(self.reminder_days),
            reminder_enabled=self.reminder_enabled,
            reminder_minutes=self.reminder_minutes,
            reminder_sent=self.reminder_sent,
            attendee_emails=list(self.attendee_emails),
            max_attendees=self.max_attendees,
            scheduled_event_uid=self.scheduled_event_uid,
            # Progress
            vision_statement=self.vision_statement,
            goal_type=self.goal_type,
            timeframe=self.timeframe,
            measurement_type=self.measurement_type,
            target_value=self.target_value,
            current_value=self.current_value,
            unit_of_measurement=self.unit_of_measurement,
            start_date=self.start_date,
            target_date=self.target_date,
            achieved_date=self.achieved_date,
            milestones=list(self.milestones),
            progress_percentage=self.progress_percentage,
            last_progress_update=self.last_progress_update,
            progress_history=list(self.progress_history),
            why_important=self.why_important,
            success_criteria=self.success_criteria,
            potential_obstacles=list(self.potential_obstacles),
            strategies=list(self.strategies),
            parent_uid=self.parent_uid,
            project=self.project,
            assignee=self.assignee,
            fulfills_goal_uid=self.fulfills_goal_uid,
            reinforces_habit_uid=self.reinforces_habit_uid,
            source_learning_step_uid=self.source_learning_step_uid,
            source_learning_path_uid=self.source_learning_path_uid,
            goal_progress_contribution=self.goal_progress_contribution,
            knowledge_mastery_check=self.knowledge_mastery_check,
            habit_streak_maintainer=self.habit_streak_maintainer,
            completion_updates_goal=self.completion_updates_goal,
            curriculum_driven=self.curriculum_driven,
            curriculum_practice_type=self.curriculum_practice_type,
            knowledge_confidence_scores=self.knowledge_confidence_scores,
            knowledge_inference_metadata=self.knowledge_inference_metadata,
            learning_opportunities_count=self.learning_opportunities_count,
            inspired_by_choice_uid=self.inspired_by_choice_uid,
            selected_choice_option_uid=self.selected_choice_option_uid,
            milestone_celebration_for_goal=self.milestone_celebration_for_goal,
            is_milestone_event=self.is_milestone_event,
            milestone_type=self.milestone_type,
            curriculum_week=self.curriculum_week,
            habit_completion_quality=self.habit_completion_quality,
            knowledge_retention_check=self.knowledge_retention_check,
            recurrence_maintains_habit=self.recurrence_maintains_habit,
            skip_breaks_habit_streak=self.skip_breaks_habit_streak,
            # Streak
            polarity=self.polarity,
            habit_category=self.habit_category,
            habit_difficulty=self.habit_difficulty,
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
            target_identity=self.target_identity,
            identity_evidence_required=self.identity_evidence_required,
            started_at=self.started_at,
            completed_at=self.completed_at,
            # Decision
            choice_type=self.choice_type,
            options=list(self.options),
            selected_option_uid=self.selected_option_uid,
            decision_rationale=self.decision_rationale,
            decision_criteria=list(self.decision_criteria),
            constraints=list(self.constraints),
            stakeholders=list(self.stakeholders),
            decided_at=self.decided_at,
            satisfaction_score=self.satisfaction_score,
            actual_outcome=self.actual_outcome,
            lessons_learned=list(self.lessons_learned),
            inspiration_type=self.inspiration_type,
            expands_possibilities=self.expands_possibilities,
            # Conviction
            statement=self.statement,
            principle_category=self.principle_category,
            principle_source=self.principle_source,
            strength=self.strength,
            tradition=self.tradition,
            original_source=self.original_source,
            personal_interpretation=self.personal_interpretation,
            expressions=list(self.expressions),
            key_behaviors=list(self.key_behaviors),
            current_alignment=self.current_alignment,
            alignment_history=list(self.alignment_history),
            last_review_date=self.last_review_date,
            potential_conflicts=list(self.potential_conflicts),
            conflicting_principles=list(self.conflicting_principles),
            resolution_strategies=list(self.resolution_strategies),
            origin_story=self.origin_story,
            evolution_notes=self.evolution_notes,
            is_active=self.is_active,
            adopted_date=self.adopted_date,
            # Alignment
            life_path_uid=self.life_path_uid,
            designated_at=self.designated_at,
            alignment_score=self.alignment_score,
            word_action_gap=self.word_action_gap,
            alignment_level=self.alignment_level,
            knowledge_alignment=self.knowledge_alignment,
            activity_alignment=self.activity_alignment,
            goal_alignment=self.goal_alignment,
            principle_alignment=self.principle_alignment,
            momentum=self.momentum,
            vision_themes=list(self.vision_themes),
            vision_captured_at=self.vision_captured_at,
            # Curriculum Structure
            intent=self.intent,
            primary_knowledge_uids=list(self.primary_knowledge_uids),
            supporting_knowledge_uids=list(self.supporting_knowledge_uids),
            learning_path_uid=self.learning_path_uid,
            sequence=self.sequence,
            mastery_threshold=self.mastery_threshold,
            current_mastery=self.current_mastery,
            estimated_hours=self.estimated_hours,
            step_difficulty=self.step_difficulty,
            path_type=self.path_type,
            outcomes=list(self.outcomes),
            checkpoint_week_intervals=list(self.checkpoint_week_intervals),
            # Substance tracking (from KuBase)
            times_applied_in_tasks=self.times_applied_in_tasks,
            times_practiced_in_events=self.times_practiced_in_events,
            times_built_into_habits=self.times_built_into_habits,
            journal_reflections_count=self.journal_reflections_count,
            choices_informed_count=self.choices_informed_count,
            last_applied_date=self.last_applied_date,
            last_practiced_date=self.last_practiced_date,
            last_built_into_habit_date=self.last_built_into_habit_date,
            last_reflected_date=self.last_reflected_date,
            last_choice_informed_date=self.last_choice_informed_date,
            # Meta (from KuBase)
            tags=list(self.tags),
            created_at=self.created_at,
            updated_at=self.updated_at,
            metadata=self.metadata if self.metadata is not None else {},
        )


# Populate type class map now that Ku class is defined
_populate_type_class_map()
