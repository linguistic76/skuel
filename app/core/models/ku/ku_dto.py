"""
Unified Knowledge DTO (Tier 2 - Transfer)
==========================================

"Ku is the heartbeat of SKUEL."

Mutable data transfer object for ALL knowledge in the system. 14 manifestations:

    Knowledge (shared):
        CURRICULUM      → Admin-created shared knowledge (no owner)
        MOC             → Map of Content (KU organizing KUs)
    Curriculum Structure:
        LEARNING_STEP   → Step in a learning path
        LEARNING_PATH   → Ordered sequence of steps
    Content Processing:
        SUBMISSION      → Student submission (user-owned)
        AI_REPORT       → AI-derived from submission
        FEEDBACK_REPORT → Teacher feedback on submission
    Activity (user-owned):
        TASK            → Knowledge about what needs doing
        GOAL            → Knowledge about where you're heading
        HABIT           → Knowledge about what you practice
        EVENT           → Knowledge about what you attend
        CHOICE          → Knowledge about decisions you make
        PRINCIPLE       → Knowledge about what you believe
    Destination:
        LIFE_PATH       → Knowledge about your life direction

~138 mutable fields matching the Ku domain model (frozen dataclass).

Uses KuDTOMixin for conditional user_uid validation:
    CURRICULUM, MOC, LEARNING_STEP, LEARNING_PATH: user_uid must be None
    Others: user_uid is required

Factory methods per KuType for type-safe creation:
    KuDTO.create_curriculum(title, domain, ...)
    KuDTO.create_submission(user_uid, title, ...)
    KuDTO.create_ai_report(user_uid, title, parent_ku_uid, ...)
    KuDTO.create_feedback_report(user_uid, title, parent_ku_uid, ...)

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from enum import Enum
from typing import Any

from core.models.enums import Domain, KuComplexity, LearningLevel, SELCategory
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
from core.models.enums.metadata_enums import Visibility
from core.models.ku.ku_nested_types import (
    AlignmentAssessment,
    ChoiceOption,
    Milestone,
    PrincipleExpression,
)
from core.models.ku_dto_mixin import KuDTOMixin
from core.services.protocols import get_enum_value

# =============================================================================
# NESTED TYPE SERIALIZATION HELPERS
# =============================================================================


def _serialize_nested_item(item: Any) -> dict[str, Any]:
    """Serialize a frozen dataclass nested type to a JSON-compatible dict.

    Handles date → ISO string, enum → value, tuple → list conversions
    within nested dataclass instances (Milestone, ChoiceOption, etc.).
    """
    d = asdict(item)
    for k, v in list(d.items()):
        if isinstance(v, datetime | date | time):
            d[k] = v.isoformat()
        elif isinstance(v, Enum):
            d[k] = v.value
        elif isinstance(v, tuple):
            d[k] = list(v)
    return d


def _parse_date_value(val: Any) -> date | None:
    """Parse a date from string or return as-is if already a date."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        try:
            return date.fromisoformat(val)
        except ValueError:
            # Handle datetime ISO strings like '2025-10-01T00:00:00'
            return datetime.fromisoformat(val).date()
    return None


def _reconstruct_milestones(raw: list | None) -> list[Milestone]:
    """Reconstruct Milestone objects from dicts (from database)."""
    if not raw:
        return []
    result = []
    for item in raw:
        if isinstance(item, Milestone):
            result.append(item)
        elif isinstance(item, dict):
            result.append(
                Milestone(
                    uid=item.get("uid", ""),
                    title=item.get("title", ""),
                    description=item.get("description"),
                    target_date=_parse_date_value(item.get("target_date")),
                    target_value=item.get("target_value"),
                    achieved_date=_parse_date_value(item.get("achieved_date")),
                    is_completed=item.get("is_completed", False),
                    required_knowledge_uids=tuple(item.get("required_knowledge_uids", ())),
                    unlocked_knowledge_uids=tuple(item.get("unlocked_knowledge_uids", ())),
                )
            )
    return result


def _reconstruct_choice_options(raw: list | None) -> list[ChoiceOption]:
    """Reconstruct ChoiceOption objects from dicts (from database)."""
    if not raw:
        return []
    result = []
    for item in raw:
        if isinstance(item, ChoiceOption):
            result.append(item)
        elif isinstance(item, dict):
            result.append(
                ChoiceOption(
                    uid=item.get("uid", ""),
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    feasibility_score=item.get("feasibility_score", 0.5),
                    risk_level=item.get("risk_level", 0.5),
                    potential_impact=item.get("potential_impact", 0.5),
                    resource_requirement=item.get("resource_requirement", 0.5),
                    estimated_duration=item.get("estimated_duration"),
                    dependencies=tuple(item.get("dependencies", ())),
                    tags=tuple(item.get("tags", ())),
                )
            )
    return result


def _reconstruct_expressions(raw: list | None) -> list[PrincipleExpression]:
    """Reconstruct PrincipleExpression objects from dicts (from database)."""
    if not raw:
        return []
    result = []
    for item in raw:
        if isinstance(item, PrincipleExpression):
            result.append(item)
        elif isinstance(item, dict):
            result.append(
                PrincipleExpression(
                    context=item.get("context", ""),
                    behavior=item.get("behavior", ""),
                    example=item.get("example"),
                )
            )
    return result


def _reconstruct_alignment_history(raw: list | None) -> list[AlignmentAssessment]:
    """Reconstruct AlignmentAssessment objects from dicts (from database)."""
    if not raw:
        return []
    result = []
    for item in raw:
        if isinstance(item, AlignmentAssessment):
            result.append(item)
        elif isinstance(item, dict):
            alignment_val = item.get("alignment_level", "unknown")
            if isinstance(alignment_val, str):
                alignment_level = AlignmentLevel(alignment_val)
            else:
                alignment_level = alignment_val

            assessed_date = _parse_date_value(item.get("assessed_date"))
            if assessed_date is None:
                assessed_date = date.today()

            result.append(
                AlignmentAssessment(
                    assessed_date=assessed_date,
                    alignment_level=alignment_level,
                    evidence=item.get("evidence", ""),
                    reflection=item.get("reflection"),
                )
            )
    return result


def _reconstruct_nested_types(data: dict[str, Any]) -> None:
    """Pre-process nested type fields from dicts to proper dataclass instances.

    Called before dto_from_dict() to ensure nested types are correctly typed.
    Handles both raw dicts (from database) and JSON strings.
    """
    import json

    for nested_field, reconstructor in (
        ("milestones", _reconstruct_milestones),
        ("options", _reconstruct_choice_options),
        ("expressions", _reconstruct_expressions),
        ("alignment_history", _reconstruct_alignment_history),
    ):
        if nested_field in data and data[nested_field] is not None:
            val = data[nested_field]
            if isinstance(val, str):
                val = json.loads(val)
            data[nested_field] = reconstructor(val)


# =============================================================================
# DTO CLASS
# =============================================================================


@dataclass
class KuDTO(KuDTOMixin):
    """
    Mutable data transfer object for unified knowledge.

    ~138 business fields matching the Ku domain model, organized in 15 sections.

    Used for:
    - Moving data between service and repository layers
    - Database operations (save/update)
    - Service-to-service communication
    """

    # =========================================================================
    # IDENTITY
    # =========================================================================
    uid: str = ""
    title: str = ""
    ku_type: KuType = KuType.CURRICULUM
    user_uid: str | None = None
    parent_ku_uid: str | None = None
    domain: Domain = Domain.KNOWLEDGE
    created_by: str | None = None

    # =========================================================================
    # CONTENT
    # =========================================================================
    content: str | None = None
    summary: str = ""
    description: str | None = None
    word_count: int = 0

    # =========================================================================
    # FILE (SUBMISSION uploads)
    # =========================================================================
    original_filename: str | None = None
    file_path: str | None = None
    file_size: int | None = None
    file_type: str | None = None

    # =========================================================================
    # PROCESSING
    # =========================================================================
    status: KuStatus = KuStatus.DRAFT
    processor_type: ProcessorType | None = None
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    processing_error: str | None = None
    processed_content: str | None = None
    processed_file_path: str | None = None
    instructions: str | None = None
    max_retention: int | None = None  # FIFO cleanup limit (None = permanent)

    # =========================================================================
    # FEEDBACK
    # =========================================================================
    feedback: str | None = None
    feedback_generated_at: datetime | None = None
    subject_uid: str | None = None

    # =========================================================================
    # LEARNING
    # =========================================================================
    complexity: KuComplexity = KuComplexity.MEDIUM
    learning_level: LearningLevel = LearningLevel.BEGINNER
    sel_category: SELCategory | None = None
    quality_score: float = 0.0
    estimated_time_minutes: int = 15
    difficulty_rating: float = 0.5
    semantic_links: list[str] = field(default_factory=list)
    priority: str | None = None

    # =========================================================================
    # SHARING
    # =========================================================================
    visibility: Visibility = Visibility.PRIVATE

    # =========================================================================
    # SCHEDULING (TASK, EVENT, HABIT, CHOICE)
    # Dates, times, recurrence, reminders, event logistics
    # =========================================================================
    due_date: date | None = None
    scheduled_date: date | None = None
    completion_date: date | None = None
    event_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    duration_minutes: int | None = None
    actual_minutes: int | None = None
    decision_deadline: datetime | None = None

    # Event logistics
    event_type: str | None = None
    location: str | None = None
    is_online: bool = False
    meeting_url: str | None = None

    # Recurrence (TASK, HABIT, EVENT)
    recurrence_pattern: str | None = None
    recurrence_end_date: date | None = None
    recurrence_parent_uid: str | None = None
    target_days_per_week: int | None = None
    preferred_time: str | None = None

    # Reminders
    reminder_time: str | None = None
    reminder_days: list[str] = field(default_factory=list)
    reminder_enabled: bool = False
    reminder_minutes: int | None = None
    reminder_sent: bool = False

    # Attendees (EVENT)
    attendee_emails: list[str] = field(default_factory=list)
    max_attendees: int | None = None

    # Scheduling links
    scheduled_event_uid: str | None = None

    # =========================================================================
    # PROGRESS (GOAL, TASK)
    # Goal tracking, milestones, task hierarchy, learning integration
    # =========================================================================
    vision_statement: str | None = None

    # Goal classification
    goal_type: GoalType | None = None
    timeframe: GoalTimeframe | None = None
    measurement_type: MeasurementType | None = None

    # Goal measurement
    target_value: float | None = None
    current_value: float = 0.0
    unit_of_measurement: str | None = None

    # Goal timeline
    start_date: date | None = None
    target_date: date | None = None
    achieved_date: date | None = None

    # Goal milestones
    milestones: list[Milestone] = field(default_factory=list)
    progress_percentage: float = 0.0
    last_progress_update: datetime | None = None
    progress_history: list[dict] = field(default_factory=list)

    # Goal motivation
    why_important: str | None = None
    success_criteria: str | None = None
    potential_obstacles: list[str] = field(default_factory=list)
    strategies: list[str] = field(default_factory=list)

    # Task hierarchy
    parent_uid: str | None = None
    project: str | None = None
    assignee: str | None = None

    # Cross-domain links
    fulfills_goal_uid: str | None = None
    reinforces_habit_uid: str | None = None
    source_learning_step_uid: str | None = None
    source_learning_path_uid: str | None = None

    # Progress impact
    goal_progress_contribution: float = 0.0
    knowledge_mastery_check: bool = False
    habit_streak_maintainer: bool = False
    completion_updates_goal: bool = False
    curriculum_driven: bool = False
    curriculum_practice_type: str | None = None

    # Knowledge intelligence (TASK)
    knowledge_confidence_scores: dict[str, float] | None = None
    knowledge_inference_metadata: dict[str, Any] | None = None
    learning_opportunities_count: int = 0

    # Choice integration (GOAL)
    inspired_by_choice_uid: str | None = None
    selected_choice_option_uid: str | None = None

    # Event curriculum integration
    milestone_celebration_for_goal: str | None = None
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
    polarity: HabitPolarity | None = None
    habit_category: HabitCategory | None = None
    habit_difficulty: HabitDifficulty | None = None

    # Streak tracking
    current_streak: int = 0
    best_streak: int = 0
    total_completions: int = 0
    total_attempts: int = 0
    success_rate: float = 0.0
    last_completed: datetime | None = None

    # Behavioral science (Atomic Habits)
    cue: str | None = None
    routine: str | None = None
    reward: str | None = None

    # Identity
    reinforces_identity: str | None = None
    identity_votes_cast: int = 0
    is_identity_habit: bool = False
    target_identity: str | None = None
    identity_evidence_required: int = 0

    # Lifecycle
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # =========================================================================
    # DECISION (CHOICE)
    # Choice options, criteria, outcome tracking
    # =========================================================================
    choice_type: ChoiceType | None = None
    options: list[ChoiceOption] = field(default_factory=list)
    selected_option_uid: str | None = None
    decision_rationale: str | None = None

    # Decision context
    decision_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    stakeholders: list[str] = field(default_factory=list)

    # Decision timing
    decided_at: datetime | None = None

    # Outcome
    satisfaction_score: int | None = None
    actual_outcome: str | None = None
    lessons_learned: list[str] = field(default_factory=list)

    # Choice-curriculum integration
    inspiration_type: str | None = None
    expands_possibilities: bool = False

    # =========================================================================
    # CONVICTION (PRINCIPLE)
    # Principle expressions, alignment, philosophical context
    # =========================================================================
    statement: str | None = None

    # Classification
    principle_category: PrincipleCategory | None = None
    principle_source: PrincipleSource | None = None
    strength: PrincipleStrength | None = None

    # Philosophical context
    tradition: str | None = None
    original_source: str | None = None
    personal_interpretation: str | None = None

    # Expressions & applications
    expressions: list[PrincipleExpression] = field(default_factory=list)
    key_behaviors: list[str] = field(default_factory=list)

    # Alignment tracking
    current_alignment: AlignmentLevel | None = None
    alignment_history: list[AlignmentAssessment] = field(default_factory=list)
    last_review_date: date | None = None

    # Conflicts & tensions
    potential_conflicts: list[str] = field(default_factory=list)
    conflicting_principles: list[str] = field(default_factory=list)
    resolution_strategies: list[str] = field(default_factory=list)

    # Personal reflection
    origin_story: str | None = None
    evolution_notes: str | None = None

    # Principle status
    is_active: bool = True
    adopted_date: date | None = None

    # =========================================================================
    # ALIGNMENT (LIFE_PATH)
    # Life path designation and dimension scores
    # =========================================================================
    life_path_uid: str | None = None
    designated_at: datetime | None = None

    # Scores
    alignment_score: float = 0.0
    word_action_gap: float = 0.0
    alignment_level: AlignmentLevel | None = None

    # Dimension scores (5 dimensions)
    knowledge_alignment: float = 0.0
    activity_alignment: float = 0.0
    goal_alignment: float = 0.0
    principle_alignment: float = 0.0
    momentum: float = 0.0

    # Vision
    vision_themes: list[str] = field(default_factory=list)
    vision_captured_at: datetime | None = None

    # =========================================================================
    # CURRICULUM STRUCTURE (LEARNING_STEP, LEARNING_PATH)
    # =========================================================================
    intent: str | None = None
    primary_knowledge_uids: list[str] = field(default_factory=list)
    supporting_knowledge_uids: list[str] = field(default_factory=list)
    learning_path_uid: str | None = None
    sequence: int | None = None

    # Mastery
    mastery_threshold: float = 0.7
    current_mastery: float = 0.0
    estimated_hours: float | None = None
    step_difficulty: StepDifficulty | None = None

    # Path configuration (LP)
    path_type: LpType | None = None
    outcomes: list[str] = field(default_factory=list)
    checkpoint_week_intervals: list[int] = field(default_factory=list)

    # =========================================================================
    # SUBSTANCE TRACKING
    # =========================================================================
    times_applied_in_tasks: int = 0
    times_practiced_in_events: int = 0
    times_built_into_habits: int = 0
    journal_reflections_count: int = 0
    choices_informed_count: int = 0

    last_applied_date: datetime | None = None
    last_practiced_date: datetime | None = None
    last_built_into_habit_date: datetime | None = None
    last_reflected_date: datetime | None = None
    last_choice_informed_date: datetime | None = None

    # =========================================================================
    # META
    # =========================================================================
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    # =========================================================================
    # FACTORY METHODS (per KuType)
    # =========================================================================

    @classmethod
    def create_curriculum(
        cls,
        title: str,
        domain: Domain,
        **kwargs: Any,
    ) -> KuDTO:
        """
        Create a CURRICULUM Ku (admin-created shared knowledge).

        No user_uid — curriculum is shared content.
        Status defaults to COMPLETED, visibility to PUBLIC.
        """
        kwargs.pop("user_uid", None)  # Curriculum never has user_uid
        kwargs.setdefault("status", KuStatus.COMPLETED)
        kwargs.setdefault("visibility", Visibility.PUBLIC)
        return cls._create_ku_dto(
            ku_type=KuType.CURRICULUM,
            title=title,
            user_uid=None,
            domain=domain,
            **kwargs,
        )

    @classmethod
    def create_submission(
        cls,
        user_uid: str,
        title: str,
        **kwargs: Any,
    ) -> KuDTO:
        """
        Create a SUBMISSION Ku (student submission).

        Requires user_uid. Status defaults to DRAFT, visibility to PRIVATE.
        """
        return cls._create_ku_dto(
            ku_type=KuType.SUBMISSION,
            title=title,
            user_uid=user_uid,
            **kwargs,
        )

    @classmethod
    def create_ai_report(
        cls,
        user_uid: str,
        title: str,
        parent_ku_uid: str,
        **kwargs: Any,
    ) -> KuDTO:
        """
        Create an AI_REPORT Ku (AI-derived from assignment).

        Requires user_uid and parent_ku_uid (the assignment it derives from).
        """
        return cls._create_ku_dto(
            ku_type=KuType.AI_REPORT,
            title=title,
            user_uid=user_uid,
            parent_ku_uid=parent_ku_uid,
            **kwargs,
        )

    @classmethod
    def create_feedback_report(
        cls,
        user_uid: str,
        title: str,
        parent_ku_uid: str,
        **kwargs: Any,
    ) -> KuDTO:
        """
        Create a FEEDBACK_REPORT Ku (teacher feedback on assignment).

        Requires user_uid (teacher) and parent_ku_uid (the assignment reviewed).
        """
        return cls._create_ku_dto(
            ku_type=KuType.FEEDBACK_REPORT,
            title=title,
            user_uid=user_uid,
            parent_ku_uid=parent_ku_uid,
            **kwargs,
        )

    # =========================================================================
    # UPDATE
    # =========================================================================

    def update_from(self, updates: dict[str, Any]) -> None:
        """Update DTO fields from a dictionary (for update operations)."""
        from core.models.dto_helpers import update_from_dict

        update_from_dict(
            self,
            updates,
            allowed_fields={
                # Content
                "title",
                "content",
                "summary",
                "description",
                "word_count",
                "domain",
                # File
                "original_filename",
                "file_path",
                "file_size",
                "file_type",
                # Processing
                "status",
                "processor_type",
                "processing_started_at",
                "processing_completed_at",
                "processing_error",
                "processed_content",
                "processed_file_path",
                "instructions",
                "max_retention",
                # Feedback
                "feedback",
                "feedback_generated_at",
                "subject_uid",
                # Learning
                "complexity",
                "learning_level",
                "sel_category",
                "quality_score",
                "estimated_time_minutes",
                "difficulty_rating",
                "semantic_links",
                "priority",
                # Sharing
                "visibility",
                # Scheduling
                "due_date",
                "scheduled_date",
                "completion_date",
                "event_date",
                "start_time",
                "end_time",
                "duration_minutes",
                "actual_minutes",
                "decision_deadline",
                "event_type",
                "location",
                "is_online",
                "meeting_url",
                "recurrence_pattern",
                "recurrence_end_date",
                "recurrence_parent_uid",
                "target_days_per_week",
                "preferred_time",
                "reminder_time",
                "reminder_days",
                "reminder_enabled",
                "reminder_minutes",
                "reminder_sent",
                "attendee_emails",
                "max_attendees",
                "scheduled_event_uid",
                # Progress
                "vision_statement",
                "goal_type",
                "timeframe",
                "measurement_type",
                "target_value",
                "current_value",
                "unit_of_measurement",
                "start_date",
                "target_date",
                "achieved_date",
                "milestones",
                "progress_percentage",
                "last_progress_update",
                "progress_history",
                "why_important",
                "success_criteria",
                "potential_obstacles",
                "strategies",
                "parent_uid",
                "project",
                "assignee",
                "fulfills_goal_uid",
                "reinforces_habit_uid",
                "source_learning_step_uid",
                "source_learning_path_uid",
                "goal_progress_contribution",
                "knowledge_mastery_check",
                "habit_streak_maintainer",
                "completion_updates_goal",
                "curriculum_driven",
                "curriculum_practice_type",
                "knowledge_confidence_scores",
                "knowledge_inference_metadata",
                "learning_opportunities_count",
                "inspired_by_choice_uid",
                "selected_choice_option_uid",
                "milestone_celebration_for_goal",
                "is_milestone_event",
                "milestone_type",
                "curriculum_week",
                "habit_completion_quality",
                "knowledge_retention_check",
                "recurrence_maintains_habit",
                "skip_breaks_habit_streak",
                # Streak
                "polarity",
                "habit_category",
                "habit_difficulty",
                "current_streak",
                "best_streak",
                "total_completions",
                "total_attempts",
                "success_rate",
                "last_completed",
                "cue",
                "routine",
                "reward",
                "reinforces_identity",
                "identity_votes_cast",
                "is_identity_habit",
                "target_identity",
                "identity_evidence_required",
                "started_at",
                "completed_at",
                # Decision
                "choice_type",
                "options",
                "selected_option_uid",
                "decision_rationale",
                "decision_criteria",
                "constraints",
                "stakeholders",
                "decided_at",
                "satisfaction_score",
                "actual_outcome",
                "lessons_learned",
                "inspiration_type",
                "expands_possibilities",
                # Conviction
                "statement",
                "principle_category",
                "principle_source",
                "strength",
                "tradition",
                "original_source",
                "personal_interpretation",
                "expressions",
                "key_behaviors",
                "current_alignment",
                "alignment_history",
                "last_review_date",
                "potential_conflicts",
                "conflicting_principles",
                "resolution_strategies",
                "origin_story",
                "evolution_notes",
                "is_active",
                "adopted_date",
                # Alignment
                "life_path_uid",
                "designated_at",
                "alignment_score",
                "word_action_gap",
                "alignment_level",
                "knowledge_alignment",
                "activity_alignment",
                "goal_alignment",
                "principle_alignment",
                "momentum",
                "vision_themes",
                "vision_captured_at",
                # Curriculum Structure
                "intent",
                "primary_knowledge_uids",
                "supporting_knowledge_uids",
                "learning_path_uid",
                "sequence",
                "mastery_threshold",
                "current_mastery",
                "estimated_hours",
                "step_difficulty",
                "path_type",
                "outcomes",
                "checkpoint_week_intervals",
                # Substance tracking
                "times_applied_in_tasks",
                "times_practiced_in_events",
                "times_built_into_habits",
                "journal_reflections_count",
                "choices_informed_count",
                "last_applied_date",
                "last_practiced_date",
                "last_built_into_habit_date",
                "last_reflected_date",
                "last_choice_informed_date",
                # Meta
                "tags",
                "metadata",
            },
            enum_mappings={
                "ku_type": KuType,
                "status": KuStatus,
                "processor_type": ProcessorType,
                "domain": Domain,
                "complexity": KuComplexity,
                "learning_level": LearningLevel,
                "sel_category": SELCategory,
                "visibility": Visibility,
                "goal_type": GoalType,
                "timeframe": GoalTimeframe,
                "measurement_type": MeasurementType,
                "polarity": HabitPolarity,
                "habit_category": HabitCategory,
                "habit_difficulty": HabitDifficulty,
                "choice_type": ChoiceType,
                "principle_category": PrincipleCategory,
                "principle_source": PrincipleSource,
                "strength": PrincipleStrength,
                "current_alignment": AlignmentLevel,
                "alignment_level": AlignmentLevel,
                "step_difficulty": StepDifficulty,
                "path_type": LpType,
            },
        )

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database operations.

        Serializes all ~138 fields to JSON-compatible types:
        - Enums → string values
        - Dates → ISO format strings
        - Datetimes → ISO format strings
        - Times → ISO format strings
        - Nested types (Milestone, ChoiceOption, etc.) → list of dicts
        """
        from core.models.dto_helpers import (
            convert_dates_to_iso,
            convert_datetimes_to_iso,
        )

        data: dict[str, Any] = {
            # =================================================================
            # IDENTITY
            # =================================================================
            "uid": self.uid,
            "title": self.title,
            "ku_type": get_enum_value(self.ku_type),
            "user_uid": self.user_uid,
            "parent_ku_uid": self.parent_ku_uid,
            "domain": get_enum_value(self.domain),
            "created_by": self.created_by,
            # =================================================================
            # CONTENT
            # =================================================================
            "content": self.content,
            "summary": self.summary,
            "description": self.description,
            "word_count": self.word_count,
            # =================================================================
            # FILE
            # =================================================================
            "original_filename": self.original_filename,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "file_type": self.file_type,
            # =================================================================
            # PROCESSING
            # =================================================================
            "status": get_enum_value(self.status),
            "processor_type": get_enum_value(self.processor_type) if self.processor_type else None,
            "processing_started_at": self.processing_started_at,
            "processing_completed_at": self.processing_completed_at,
            "processing_error": self.processing_error,
            "processed_content": self.processed_content,
            "processed_file_path": self.processed_file_path,
            "instructions": self.instructions,
            # =================================================================
            # FEEDBACK
            # =================================================================
            "feedback": self.feedback,
            "feedback_generated_at": self.feedback_generated_at,
            "subject_uid": self.subject_uid,
            # =================================================================
            # LEARNING
            # =================================================================
            "complexity": get_enum_value(self.complexity),
            "learning_level": get_enum_value(self.learning_level),
            "sel_category": get_enum_value(self.sel_category) if self.sel_category else None,
            "quality_score": self.quality_score,
            "estimated_time_minutes": self.estimated_time_minutes,
            "difficulty_rating": self.difficulty_rating,
            "semantic_links": list(self.semantic_links),
            "priority": self.priority,
            # =================================================================
            # SHARING
            # =================================================================
            "visibility": get_enum_value(self.visibility),
            # =================================================================
            # SCHEDULING
            # =================================================================
            "due_date": self.due_date,
            "scheduled_date": self.scheduled_date,
            "completion_date": self.completion_date,
            "event_date": self.event_date,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_minutes": self.duration_minutes,
            "actual_minutes": self.actual_minutes,
            "decision_deadline": self.decision_deadline,
            "event_type": self.event_type,
            "location": self.location,
            "is_online": self.is_online,
            "meeting_url": self.meeting_url,
            "recurrence_pattern": self.recurrence_pattern,
            "recurrence_end_date": self.recurrence_end_date,
            "recurrence_parent_uid": self.recurrence_parent_uid,
            "target_days_per_week": self.target_days_per_week,
            "preferred_time": self.preferred_time,
            "reminder_time": self.reminder_time,
            "reminder_days": list(self.reminder_days),
            "reminder_enabled": self.reminder_enabled,
            "reminder_minutes": self.reminder_minutes,
            "reminder_sent": self.reminder_sent,
            "attendee_emails": list(self.attendee_emails),
            "max_attendees": self.max_attendees,
            "scheduled_event_uid": self.scheduled_event_uid,
            # =================================================================
            # PROGRESS
            # =================================================================
            "vision_statement": self.vision_statement,
            "goal_type": get_enum_value(self.goal_type) if self.goal_type else None,
            "timeframe": get_enum_value(self.timeframe) if self.timeframe else None,
            "measurement_type": get_enum_value(self.measurement_type)
            if self.measurement_type
            else None,
            "target_value": self.target_value,
            "current_value": self.current_value,
            "unit_of_measurement": self.unit_of_measurement,
            "start_date": self.start_date,
            "target_date": self.target_date,
            "achieved_date": self.achieved_date,
            "milestones": [_serialize_nested_item(m) for m in self.milestones],
            "progress_percentage": self.progress_percentage,
            "last_progress_update": self.last_progress_update,
            "progress_history": list(self.progress_history),
            "why_important": self.why_important,
            "success_criteria": self.success_criteria,
            "potential_obstacles": list(self.potential_obstacles),
            "strategies": list(self.strategies),
            "parent_uid": self.parent_uid,
            "project": self.project,
            "assignee": self.assignee,
            "fulfills_goal_uid": self.fulfills_goal_uid,
            "reinforces_habit_uid": self.reinforces_habit_uid,
            "source_learning_step_uid": self.source_learning_step_uid,
            "source_learning_path_uid": self.source_learning_path_uid,
            "goal_progress_contribution": self.goal_progress_contribution,
            "knowledge_mastery_check": self.knowledge_mastery_check,
            "habit_streak_maintainer": self.habit_streak_maintainer,
            "completion_updates_goal": self.completion_updates_goal,
            "curriculum_driven": self.curriculum_driven,
            "curriculum_practice_type": self.curriculum_practice_type,
            "knowledge_confidence_scores": dict(self.knowledge_confidence_scores)
            if self.knowledge_confidence_scores
            else None,
            "knowledge_inference_metadata": dict(self.knowledge_inference_metadata)
            if self.knowledge_inference_metadata
            else None,
            "learning_opportunities_count": self.learning_opportunities_count,
            "inspired_by_choice_uid": self.inspired_by_choice_uid,
            "selected_choice_option_uid": self.selected_choice_option_uid,
            "milestone_celebration_for_goal": self.milestone_celebration_for_goal,
            "is_milestone_event": self.is_milestone_event,
            "milestone_type": self.milestone_type,
            "curriculum_week": self.curriculum_week,
            "habit_completion_quality": self.habit_completion_quality,
            "knowledge_retention_check": self.knowledge_retention_check,
            "recurrence_maintains_habit": self.recurrence_maintains_habit,
            "skip_breaks_habit_streak": self.skip_breaks_habit_streak,
            # =================================================================
            # STREAK
            # =================================================================
            "polarity": get_enum_value(self.polarity) if self.polarity else None,
            "habit_category": get_enum_value(self.habit_category) if self.habit_category else None,
            "habit_difficulty": get_enum_value(self.habit_difficulty)
            if self.habit_difficulty
            else None,
            "current_streak": self.current_streak,
            "best_streak": self.best_streak,
            "total_completions": self.total_completions,
            "total_attempts": self.total_attempts,
            "success_rate": self.success_rate,
            "last_completed": self.last_completed,
            "cue": self.cue,
            "routine": self.routine,
            "reward": self.reward,
            "reinforces_identity": self.reinforces_identity,
            "identity_votes_cast": self.identity_votes_cast,
            "is_identity_habit": self.is_identity_habit,
            "target_identity": self.target_identity,
            "identity_evidence_required": self.identity_evidence_required,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            # =================================================================
            # DECISION
            # =================================================================
            "choice_type": get_enum_value(self.choice_type) if self.choice_type else None,
            "options": [_serialize_nested_item(o) for o in self.options],
            "selected_option_uid": self.selected_option_uid,
            "decision_rationale": self.decision_rationale,
            "decision_criteria": list(self.decision_criteria),
            "constraints": list(self.constraints),
            "stakeholders": list(self.stakeholders),
            "decided_at": self.decided_at,
            "satisfaction_score": self.satisfaction_score,
            "actual_outcome": self.actual_outcome,
            "lessons_learned": list(self.lessons_learned),
            "inspiration_type": self.inspiration_type,
            "expands_possibilities": self.expands_possibilities,
            # =================================================================
            # CONVICTION
            # =================================================================
            "statement": self.statement,
            "principle_category": get_enum_value(self.principle_category)
            if self.principle_category
            else None,
            "principle_source": get_enum_value(self.principle_source)
            if self.principle_source
            else None,
            "strength": get_enum_value(self.strength) if self.strength else None,
            "tradition": self.tradition,
            "original_source": self.original_source,
            "personal_interpretation": self.personal_interpretation,
            "expressions": [_serialize_nested_item(e) for e in self.expressions],
            "key_behaviors": list(self.key_behaviors),
            "current_alignment": get_enum_value(self.current_alignment)
            if self.current_alignment
            else None,
            "alignment_history": [_serialize_nested_item(a) for a in self.alignment_history],
            "last_review_date": self.last_review_date,
            "potential_conflicts": list(self.potential_conflicts),
            "conflicting_principles": list(self.conflicting_principles),
            "resolution_strategies": list(self.resolution_strategies),
            "origin_story": self.origin_story,
            "evolution_notes": self.evolution_notes,
            "is_active": self.is_active,
            "adopted_date": self.adopted_date,
            # =================================================================
            # ALIGNMENT
            # =================================================================
            "life_path_uid": self.life_path_uid,
            "designated_at": self.designated_at,
            "alignment_score": self.alignment_score,
            "word_action_gap": self.word_action_gap,
            "alignment_level": get_enum_value(self.alignment_level)
            if self.alignment_level
            else None,
            "knowledge_alignment": self.knowledge_alignment,
            "activity_alignment": self.activity_alignment,
            "goal_alignment": self.goal_alignment,
            "principle_alignment": self.principle_alignment,
            "momentum": self.momentum,
            "vision_themes": list(self.vision_themes),
            "vision_captured_at": self.vision_captured_at,
            # =================================================================
            # CURRICULUM STRUCTURE
            # =================================================================
            "intent": self.intent,
            "primary_knowledge_uids": list(self.primary_knowledge_uids),
            "supporting_knowledge_uids": list(self.supporting_knowledge_uids),
            "learning_path_uid": self.learning_path_uid,
            "sequence": self.sequence,
            "mastery_threshold": self.mastery_threshold,
            "current_mastery": self.current_mastery,
            "estimated_hours": self.estimated_hours,
            "step_difficulty": get_enum_value(self.step_difficulty)
            if self.step_difficulty
            else None,
            "path_type": get_enum_value(self.path_type) if self.path_type else None,
            "outcomes": list(self.outcomes),
            "checkpoint_week_intervals": list(self.checkpoint_week_intervals),
            # =================================================================
            # SUBSTANCE TRACKING
            # =================================================================
            "times_applied_in_tasks": self.times_applied_in_tasks,
            "times_practiced_in_events": self.times_practiced_in_events,
            "times_built_into_habits": self.times_built_into_habits,
            "journal_reflections_count": self.journal_reflections_count,
            "choices_informed_count": self.choices_informed_count,
            "last_applied_date": self.last_applied_date,
            "last_practiced_date": self.last_practiced_date,
            "last_built_into_habit_date": self.last_built_into_habit_date,
            "last_reflected_date": self.last_reflected_date,
            "last_choice_informed_date": self.last_choice_informed_date,
            # =================================================================
            # META
            # =================================================================
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata) if self.metadata else {},
        }

        # Convert datetime fields to ISO format
        convert_datetimes_to_iso(
            data,
            [
                "created_at",
                "updated_at",
                "processing_started_at",
                "processing_completed_at",
                "feedback_generated_at",
                "decision_deadline",
                "last_progress_update",
                "last_completed",
                "started_at",
                "completed_at",
                "decided_at",
                "designated_at",
                "vision_captured_at",
                "last_applied_date",
                "last_practiced_date",
                "last_built_into_habit_date",
                "last_reflected_date",
                "last_choice_informed_date",
            ],
        )

        # Convert date fields to ISO format
        convert_dates_to_iso(
            data,
            [
                "due_date",
                "scheduled_date",
                "completion_date",
                "event_date",
                "recurrence_end_date",
                "start_date",
                "target_date",
                "achieved_date",
                "last_review_date",
                "adopted_date",
            ],
        )

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KuDTO:
        """
        Create DTO from dictionary (from database).

        Infrastructure fields (embedding, embedding_version, etc.) are
        automatically filtered out by dto_from_dict.

        Nested types (Milestone, ChoiceOption, PrincipleExpression,
        AlignmentAssessment) are reconstructed from dicts.

        See: /docs/decisions/ADR-037-embedding-infrastructure-separation.md
        """
        from core.models.dto_helpers import dto_from_dict

        # Pre-process nested types before generic parsing
        _reconstruct_nested_types(data)

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "ku_type": KuType,
                "status": KuStatus,
                "processor_type": ProcessorType,
                "domain": Domain,
                "complexity": KuComplexity,
                "sel_category": SELCategory,
                "learning_level": LearningLevel,
                "visibility": Visibility,
                # New domain-specific enums
                "goal_type": GoalType,
                "timeframe": GoalTimeframe,
                "measurement_type": MeasurementType,
                "polarity": HabitPolarity,
                "habit_category": HabitCategory,
                "habit_difficulty": HabitDifficulty,
                "choice_type": ChoiceType,
                "principle_category": PrincipleCategory,
                "principle_source": PrincipleSource,
                "strength": PrincipleStrength,
                "current_alignment": AlignmentLevel,
                "alignment_level": AlignmentLevel,
                "step_difficulty": StepDifficulty,
                "path_type": LpType,
            },
            date_fields=[
                "due_date",
                "scheduled_date",
                "completion_date",
                "event_date",
                "recurrence_end_date",
                "start_date",
                "target_date",
                "achieved_date",
                "last_review_date",
                "adopted_date",
            ],
            datetime_fields=[
                "created_at",
                "updated_at",
                "processing_started_at",
                "processing_completed_at",
                "feedback_generated_at",
                "decision_deadline",
                "last_progress_update",
                "last_completed",
                "started_at",
                "completed_at",
                "decided_at",
                "designated_at",
                "vision_captured_at",
                "last_applied_date",
                "last_practiced_date",
                "last_built_into_habit_date",
                "last_reflected_date",
                "last_choice_informed_date",
            ],
            time_fields=[
                "start_time",
                "end_time",
            ],
            list_fields=[
                "tags",
                "semantic_links",
                "reminder_days",
                "attendee_emails",
                "potential_obstacles",
                "strategies",
                "decision_criteria",
                "constraints",
                "stakeholders",
                "lessons_learned",
                "key_behaviors",
                "potential_conflicts",
                "conflicting_principles",
                "resolution_strategies",
                "vision_themes",
                "primary_knowledge_uids",
                "supporting_knowledge_uids",
                "outcomes",
                "checkpoint_week_intervals",
                "progress_history",
                # Note: milestones, options, expressions, alignment_history
                # are pre-processed by _reconstruct_nested_types() above
            ],
            dict_fields=[
                "metadata",
                "knowledge_confidence_scores",
                "knowledge_inference_metadata",
            ],
            deprecated_fields=[
                # Old KuDTO fields
                "prerequisites",
                "enables",
                "related_to",
                # Old Report fields
                "report_type",
                "journal_category",
                "journal_type",
                "content_type",
                "entry_date",
                "reading_time_minutes",
                "source_type",
                "source_file",
                "transcription_uid",
                "mood",
                "energy_level",
                "key_topics",
                "mentioned_people",
                "mentioned_places",
                "action_items",
                "project_uid",
                # Old domain-specific labels
                "name",  # Habit used 'name' instead of 'title'
            ],
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, KuDTO):
            return False
        return self.uid == other.uid
