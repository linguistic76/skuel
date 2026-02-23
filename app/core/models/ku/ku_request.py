"""
Unified Knowledge Request Models (Tier 1 - External)
=====================================================

"Ku is the heartbeat of SKUEL."

Pydantic models for API boundaries — validation and serialization.
14 create requests (one per EntityType), one update, one response.

Create requests (Content Processing):
    CurriculumCreateRequest    → Admin creates shared knowledge
    SubmissionCreateRequest    → Student submits work
    AiReportCreateRequest      → System creates AI-derived analysis
    FeedbackCreateRequest      → Teacher provides feedback

Create requests (Activity Domains):
    TaskCreateRequest          → User creates task knowledge
    GoalCreateRequest          → User creates goal knowledge
    HabitCreateRequest         → User creates habit knowledge
    EventCreateRequest         → User creates event knowledge
    ChoiceCreateRequest        → User creates choice knowledge
    PrincipleCreateRequest     → User creates principle knowledge

Create requests (Shared/Curriculum):
    MocCreateRequest           → Admin creates MOC (shared)
    LearningStepCreateRequest  → Admin creates learning step (shared)
    LearningPathCreateRequest  → Admin creates learning path (shared)

Create requests (Destination):
    LifePathCreateRequest      → User creates life path knowledge

Nested request models (used in create requests):
    MilestoneRequest             → Goal milestones
    ChoiceOptionRequest          → Choice options
    PrincipleExpressionRequest   → Principle behavioral expressions

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from core.models.enums import (
    Domain,
    KuComplexity,
    LearningLevel,
    Priority,
    RecurrencePattern,
    SELCategory,
)
from core.models.enums.ku_enums import (
    AlignmentLevel,
    ChoiceType,
    EntityStatus,
    EntityType,
    GoalTimeframe,
    GoalType,
    HabitCategory,
    HabitDifficulty,
    HabitPolarity,
    LpType,
    MeasurementType,
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
    ProcessorType,
    StepDifficulty,
)
from core.models.enums.metadata_enums import Visibility
from core.models.request_base import (
    CreateRequestBase,
    ListResponseBase,
    ResponseBase,
    UpdateRequestBase,
)

if TYPE_CHECKING:
    from core.models.ku.entity_dto import EntityDTO


# =============================================================================
# NESTED REQUEST MODELS (used by create requests)
# =============================================================================


class MilestoneRequest(BaseModel):
    """Request model for creating a milestone within a GOAL Ku."""

    title: str = Field(min_length=1, max_length=200, description="Milestone title")
    target_date: date = Field(description="When this milestone should be achieved")
    description: str | None = Field(None, max_length=500, description="Detailed description")
    target_value: float | None = Field(None, ge=0, description="Numeric target")
    required_knowledge_uids: list[str] = Field(
        default_factory=list, description="KU UIDs needed to reach this milestone"
    )


class ChoiceOptionRequest(BaseModel):
    """Request model for creating an option within a CHOICE Ku."""

    title: str = Field(min_length=1, max_length=200, description="Option title")
    description: str = Field(default="", max_length=1000, description="Option description")
    feasibility_score: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_level: float = Field(default=0.5, ge=0.0, le=1.0)
    potential_impact: float = Field(default=0.5, ge=0.0, le=1.0)
    resource_requirement: float = Field(default=0.5, ge=0.0, le=1.0)
    estimated_duration: int | None = Field(None, ge=1, description="Duration in minutes")
    dependencies: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class PrincipleExpressionRequest(BaseModel):
    """Request model for creating an expression within a PRINCIPLE Ku."""

    context: str = Field(min_length=1, max_length=500, description="Life situation")
    behavior: str = Field(min_length=1, max_length=500, description="Expected behavior")
    example: str | None = Field(None, max_length=500, description="Concrete example")


# =============================================================================
# CREATE REQUESTS — Content Processing (original 4 KuTypes)
# =============================================================================


class CurriculumCreateRequest(CreateRequestBase):
    """Create admin-authored curriculum knowledge (CURRICULUM type)."""

    title: str = Field(min_length=1, max_length=200, description="Title of the knowledge unit")
    domain: Domain = Field(description="Knowledge domain")

    # Content
    content: str | None = Field(None, description="Body text")
    summary: str | None = Field(None, max_length=500, description="Brief summary")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")

    # Learning metadata
    complexity: KuComplexity = Field(default=KuComplexity.MEDIUM, description="Difficulty level")
    sel_category: SELCategory | None = Field(None, description="SEL category lens")
    learning_level: LearningLevel = Field(
        default=LearningLevel.BEGINNER, description="Target learning level"
    )
    estimated_time_minutes: int = Field(default=15, ge=1, description="Estimated completion time")
    difficulty_rating: float = Field(default=0.5, ge=0.0, le=1.0, description="Difficulty 0.0-1.0")


class SubmissionCreateRequest(CreateRequestBase):
    """Create a student submission (SUBMISSION type)."""

    title: str = Field(min_length=1, max_length=200, description="Submission title")

    # Content (at least one of content or file expected)
    content: str | None = Field(None, description="Text content of submission")
    domain: Domain = Field(default=Domain.KNOWLEDGE, description="Knowledge domain")
    tags: list[str] = Field(default_factory=list, description="Tags")

    # Derivation
    parent_ku_uid: str | None = Field(None, description="Curriculum Ku this assignment is based on")

    # Processing
    processor_type: ProcessorType | None = Field(
        None, description="How to process (LLM, HUMAN, etc.)"
    )
    instructions: str | None = Field(
        None, description="Processing instructions (absorbed from ReportProject)"
    )

    # File metadata (populated by upload handler, not user input)
    original_filename: str | None = Field(None, description="Uploaded filename")
    file_path: str | None = Field(None, description="Server file path")
    file_size: int | None = Field(None, ge=0, description="File size in bytes")
    file_type: str | None = Field(None, description="MIME type")


class AiReportCreateRequest(CreateRequestBase):
    """Create an AI-derived report (AI_REPORT type). System-initiated."""

    title: str = Field(min_length=1, max_length=200, description="Report title")
    parent_ku_uid: str = Field(description="Assignment Ku this report derives from")

    # Content
    content: str | None = Field(None, description="AI-generated analysis")
    processed_content: str | None = Field(None, description="Processed output")
    summary: str | None = Field(None, max_length=500, description="Brief summary")
    domain: Domain = Field(default=Domain.KNOWLEDGE, description="Knowledge domain")

    # Processing
    processor_type: ProcessorType = Field(default=ProcessorType.LLM, description="Processing type")
    instructions: str | None = Field(None, description="Instructions used for generation")


class FeedbackCreateRequest(CreateRequestBase):
    """Create teacher feedback on an assignment (FEEDBACK_REPORT type)."""

    title: str = Field(min_length=1, max_length=200, description="Feedback title")
    parent_ku_uid: str = Field(description="Assignment Ku being reviewed")
    subject_uid: str | None = Field(None, description="Student UID the feedback is about")

    # Content
    feedback: str = Field(min_length=1, description="Feedback text")
    content: str | None = Field(None, description="Additional content")
    domain: Domain = Field(default=Domain.KNOWLEDGE, description="Knowledge domain")


# =============================================================================
# CREATE REQUESTS — Activity Domains (6 new KuTypes)
# =============================================================================


class TaskCreateRequest(CreateRequestBase):
    """Create a TASK Ku (knowledge about what needs doing)."""

    title: str = Field(min_length=1, max_length=200, description="Task title")
    description: str | None = Field(None, max_length=2000, description="Task description")

    # Scheduling
    due_date: date | None = Field(None, description="When this task is due")
    scheduled_date: date | None = Field(None, description="When this task is scheduled")
    duration_minutes: int = Field(default=30, ge=5, le=480, description="Estimated duration")
    recurrence_pattern: RecurrencePattern | None = Field(None, description="Recurrence pattern")
    recurrence_end_date: date | None = Field(None, description="When recurrence ends")

    # Organization
    priority: Priority = Field(default=Priority.MEDIUM, description="Task priority")
    project: str | None = Field(None, max_length=200, description="Project name")
    assignee: str | None = Field(None, description="Assigned user UID")
    parent_uid: str | None = Field(None, description="Parent task UID (for subtasks)")
    progress_weight: float = Field(
        default=1.0, ge=0.0, description="Weight in parent goal progress"
    )
    tags: list[str] = Field(default_factory=list, description="Tags")

    # Cross-domain relationships (services create graph edges)
    fulfills_goal_uid: str | None = Field(None, description="Goal this task contributes to")
    reinforces_habit_uid: str | None = Field(None, description="Habit this task reinforces")
    applies_knowledge_uids: list[str] = Field(default_factory=list, description="KU UIDs applied")
    aligned_principle_uids: list[str] = Field(default_factory=list, description="Principle UIDs")
    prerequisite_knowledge_uids: list[str] = Field(
        default_factory=list, description="Required KU UIDs"
    )
    prerequisite_task_uids: list[str] = Field(
        default_factory=list, description="Required task UIDs"
    )


class GoalCreateRequest(CreateRequestBase):
    """Create a GOAL Ku (knowledge about where you're heading)."""

    title: str = Field(min_length=1, max_length=200, description="Goal title")
    description: str | None = Field(None, max_length=2000, description="Goal description")
    vision_statement: str | None = Field(
        None, max_length=1000, description="What success looks like"
    )

    # Classification
    goal_type: GoalType = Field(default=GoalType.OUTCOME, description="Goal type")
    domain: Domain = Field(default=Domain.KNOWLEDGE, description="Knowledge domain")
    timeframe: GoalTimeframe = Field(default=GoalTimeframe.QUARTERLY, description="Timeframe")

    # Measurement
    measurement_type: MeasurementType = Field(
        default=MeasurementType.PERCENTAGE, description="How to measure"
    )
    target_value: float | None = Field(None, ge=0, description="Target value")
    unit_of_measurement: str | None = Field(None, max_length=50, description="Unit label")

    # Timing
    start_date: date | None = Field(default_factory=date.today, description="Start date")
    target_date: date | None = Field(None, description="Target completion date")

    # Organization
    parent_uid: str | None = Field(None, description="Parent goal UID")
    progress_weight: float = Field(default=1.0, ge=0.0, description="Weight in parent goal")
    priority: Priority = Field(default=Priority.MEDIUM, description="Goal priority")
    tags: list[str] = Field(default_factory=list, max_length=20, description="Tags")

    # Motivation
    why_important: str | None = Field(None, max_length=1000, description="Why this goal matters")
    success_criteria: str | None = Field(None, max_length=1000, description="Criteria for success")
    potential_obstacles: list[str] = Field(
        default_factory=list, max_length=10, description="Known obstacles"
    )
    strategies: list[str] = Field(
        default_factory=list, max_length=10, description="Strategies to achieve"
    )

    # Milestones
    milestones: list[MilestoneRequest] = Field(default_factory=list, description="Goal milestones")

    # Cross-domain relationships
    required_knowledge_uids: list[str] = Field(default_factory=list, description="Required KU UIDs")
    supporting_habit_uids: list[str] = Field(
        default_factory=list, description="Supporting habit UIDs"
    )
    guiding_principle_uids: list[str] = Field(
        default_factory=list, description="Guiding principles"
    )


class HabitCreateRequest(CreateRequestBase):
    """Create a HABIT Ku (knowledge about what you practice)."""

    title: str = Field(min_length=1, max_length=200, description="Habit title")
    description: str | None = Field(None, max_length=1000, description="Habit description")

    # Habit characteristics
    polarity: HabitPolarity = Field(default=HabitPolarity.BUILD, description="Build or break")
    category: HabitCategory = Field(default=HabitCategory.OTHER, description="Habit category")
    difficulty: HabitDifficulty = Field(
        default=HabitDifficulty.MODERATE, description="Difficulty level"
    )

    # Schedule
    recurrence_pattern: RecurrencePattern = Field(
        default=RecurrencePattern.DAILY, description="Frequency"
    )
    target_days_per_week: int = Field(default=7, ge=1, le=7, description="Target days per week")
    preferred_time: str | None = Field(
        None, description="Preferred time: morning, afternoon, evening"
    )
    duration_minutes: int = Field(default=15, ge=1, le=480, description="Duration per session")

    # Behavior design (Atomic Habits)
    cue: str | None = Field(None, max_length=500, description="Cue/trigger")
    routine: str | None = Field(None, max_length=1000, description="The routine")
    reward: str | None = Field(None, max_length=500, description="The reward")
    reinforces_identity: str | None = Field(None, max_length=200, description="Identity reinforced")
    is_identity_habit: bool = Field(default=False, description="Is this an identity habit?")

    # Organization
    priority: Priority = Field(default=Priority.MEDIUM, description="Habit priority")
    tags: list[str] = Field(default_factory=list, max_length=20, description="Tags")

    # Cross-domain relationships
    linked_knowledge_uids: list[str] = Field(default_factory=list, description="Linked KU UIDs")
    linked_goal_uids: list[str] = Field(default_factory=list, description="Linked goal UIDs")
    linked_principle_uids: list[str] = Field(
        default_factory=list, description="Linked principle UIDs"
    )


class EventCreateRequest(CreateRequestBase):
    """Create an EVENT Ku (knowledge about what you attend)."""

    title: str = Field(min_length=1, max_length=200, description="Event title")
    description: str | None = Field(None, max_length=2000, description="Event description")

    # Scheduling
    event_date: date = Field(description="Event date")
    start_time: time = Field(description="Start time")
    end_time: time = Field(description="End time")
    recurrence_pattern: RecurrencePattern | None = Field(None, description="Recurrence")
    recurrence_end_date: date | None = Field(None, description="When recurrence ends")
    reminder_minutes: int | None = Field(
        None, ge=0, le=10080, description="Reminder (minutes before)"
    )

    # Location & type
    event_type: str = Field(default="personal", description="Event type")
    visibility: Visibility = Field(default=Visibility.PRIVATE, description="Visibility")
    location: str | None = Field(None, max_length=500, description="Physical location")
    is_online: bool = Field(default=False, description="Is this an online event?")
    meeting_url: str | None = Field(None, description="Meeting URL for online events")

    # Attendance
    attendee_emails: list[str] = Field(default_factory=list, description="Attendee emails")
    max_attendees: int | None = Field(None, ge=1, description="Maximum attendees")

    # Organization
    priority: Priority = Field(default=Priority.MEDIUM, description="Event priority")
    tags: list[str] = Field(default_factory=list, description="Tags")

    # Cross-domain relationships
    practices_knowledge_uids: list[str] = Field(
        default_factory=list, description="KU UIDs practiced"
    )
    executes_tasks: list[str] = Field(
        default_factory=list, description="Task UIDs executed at event"
    )
    reinforces_habit_uid: str | None = Field(None, description="Habit UID reinforced")


class ChoiceCreateRequest(CreateRequestBase):
    """Create a CHOICE Ku (knowledge about decisions you make)."""

    title: str = Field(min_length=1, max_length=200, description="Choice title")
    description: str = Field(min_length=1, max_length=1000, description="Choice description")

    # Decision characteristics
    choice_type: ChoiceType = Field(default=ChoiceType.MULTIPLE, description="Choice type")
    domain: Domain = Field(default=Domain.PERSONAL, description="Domain")
    decision_deadline: datetime | None = Field(None, description="Decision deadline")
    decision_criteria: list[str] = Field(default_factory=list, description="Criteria for deciding")
    constraints: list[str] = Field(default_factory=list, description="Constraints")
    stakeholders: list[str] = Field(default_factory=list, description="Stakeholders")

    # Options
    options: list[ChoiceOptionRequest] = Field(
        default_factory=list, description="Available options"
    )

    # Organization
    priority: Priority = Field(default=Priority.MEDIUM, description="Choice priority")
    tags: list[str] = Field(default_factory=list, description="Tags")

    # Cross-domain relationships
    informed_by_knowledge_uids: list[str] = Field(
        default_factory=list, description="KU UIDs informing this choice"
    )


class ChoiceEvaluationRequest(BaseModel):
    """Request model for evaluating choice outcomes."""

    satisfaction_score: int = Field(..., ge=1, le=5, description="Satisfaction score (1-5)")
    actual_outcome: str = Field(
        ..., min_length=1, max_length=1000, description="Actual outcome description"
    )
    lessons_learned: list[str] = Field(default_factory=list, description="Lessons learned")


class ChoiceDecisionRequest(BaseModel):
    """Request model for making a decision on a choice."""

    selected_option_uid: str = Field(..., description="UID of selected option")
    decision_rationale: str | None = Field(
        None, max_length=1000, description="Rationale for decision"
    )
    decided_at: datetime | None = Field(None, description="Decision timestamp")


class ChoiceOptionCreateRequest(BaseModel):
    """Request model for creating a choice option (standalone API endpoint)."""

    title: str = Field(..., min_length=1, max_length=200, description="Option title")
    description: str = Field(..., min_length=1, max_length=1000, description="Option description")
    feasibility_score: float = Field(0.5, ge=0.0, le=1.0, description="Feasibility score (0-1)")
    risk_level: float = Field(0.5, ge=0.0, le=1.0, description="Risk level (0-1)")
    potential_impact: float = Field(0.5, ge=0.0, le=1.0, description="Potential impact (0-1)")
    resource_requirement: float = Field(
        0.5, ge=0.0, le=1.0, description="Resource requirement (0-1)"
    )
    estimated_duration: int | None = Field(None, ge=1, description="Estimated duration in minutes")
    dependencies: list[str] = Field(default_factory=list, description="Dependency UIDs")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")


class ChoiceOptionUpdateRequest(BaseModel):
    """Request model for updating a choice option."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, min_length=1, max_length=1000)
    feasibility_score: float | None = Field(None, ge=0.0, le=1.0)
    risk_level: float | None = Field(None, ge=0.0, le=1.0)
    potential_impact: float | None = Field(None, ge=0.0, le=1.0)
    resource_requirement: float | None = Field(None, ge=0.0, le=1.0)
    estimated_duration: int | None = Field(None, ge=1)
    dependencies: list[str] | None = None
    tags: list[str] | None = None


class PrincipleCreateRequest(CreateRequestBase):
    """Create a PRINCIPLE Ku (knowledge about what you believe)."""

    title: str = Field(min_length=1, max_length=100, description="Principle title")
    statement: str = Field(min_length=1, max_length=500, description="Core statement")
    description: str | None = Field(None, max_length=1000, description="Full description")

    # Classification
    category: PrincipleCategory = Field(default=PrincipleCategory.PERSONAL, description="Category")
    source: PrincipleSource = Field(default=PrincipleSource.PERSONAL, description="Source")
    strength: PrincipleStrength = Field(default=PrincipleStrength.MODERATE, description="Strength")

    # Origin
    tradition: str | None = Field(None, max_length=100, description="Tradition/school of thought")
    original_source: str | None = Field(None, max_length=200, description="Original source text")
    personal_interpretation: str | None = Field(
        None, max_length=1000, description="Personal interpretation"
    )
    why_important: str | None = Field(
        None, max_length=1000, description="Why this principle matters"
    )
    origin_story: str | None = Field(
        None, max_length=2000, description="How you came to this principle"
    )

    # Behavioral expression
    key_behaviors: list[str] = Field(
        default_factory=list, max_length=10, description="Key behaviors"
    )
    decision_criteria: list[str] = Field(
        default_factory=list, max_length=10, description="Decision criteria"
    )
    expressions: list[PrincipleExpressionRequest] = Field(
        default_factory=list, description="Context expressions"
    )

    # Organization
    priority: Priority = Field(default=Priority.MEDIUM, description="Principle priority")
    tags: list[str] = Field(default_factory=list, max_length=20, description="Tags")


class AlignmentAssessmentRequest(BaseModel):
    """Request to assess alignment with a principle."""

    alignment_level: AlignmentLevel = Field(...)
    evidence: str = Field(..., min_length=1, max_length=1000)
    reflection: str | None = Field(None, max_length=1000)
    assessed_date: date | None = Field(default_factory=date.today)


class PrincipleLinkRequest(BaseModel):
    """Request to link a principle to goals/habits/knowledge."""

    link_type: str = Field(..., pattern="^(goal|habit|knowledge|principle)$")
    uid: str = Field(..., min_length=1)
    bidirectional: bool = Field(False, description="Create reverse link")


class PrincipleFilterRequest(BaseModel):
    """Request for filtering principles."""

    category: PrincipleCategory | None = None
    source: PrincipleSource | None = None
    strength: PrincipleStrength | None = None
    current_alignment: AlignmentLevel | None = None

    is_active: bool | None = None
    is_core: bool | None = None
    supports_learning: bool | None = None
    has_conflicts: bool | None = None

    priority: Priority | None = None
    tags: list[str] | None = None
    needs_review: bool | None = None
    well_aligned: bool | None = None


@dataclass(frozen=True)
class PrincipleAlignmentAssessmentResult:
    """
    Dual-track principle alignment result.

    Captures BOTH user self-assessment AND system-calculated alignment,
    enabling gap analysis between perception and measured reality.
    """

    principle_uid: str

    # USER-DECLARED (stored in alignment_history)
    user_assessment: Any  # AlignmentAssessment

    # SYSTEM-CALCULATED (computed from goals/habits/choices)
    system_alignment: AlignmentLevel
    system_score: float  # 0.0-1.0 numeric score
    system_evidence: tuple[str, ...]

    # GAP ANALYSIS
    perception_gap: float  # Absolute difference between user vs system (0.0-1.0)
    gap_direction: str  # "user_higher" | "system_higher" | "aligned"

    # INSIGHTS
    insights: tuple[str, ...]
    recommendations: tuple[str, ...]

    def has_perception_gap(self) -> bool:
        """Check if there's a meaningful gap between perception and reality."""
        return self.perception_gap >= 0.15

    def is_self_aware(self) -> bool:
        """Check if user's self-perception matches system measurement."""
        return self.gap_direction == "aligned"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "principle_uid": self.principle_uid,
            "user_assessment": {
                "assessed_date": self.user_assessment.assessed_date.isoformat(),
                "alignment_level": self.user_assessment.alignment_level.value,
                "evidence": self.user_assessment.evidence,
                "reflection": self.user_assessment.reflection,
            },
            "system_alignment": self.system_alignment.value,
            "system_score": self.system_score,
            "system_evidence": list(self.system_evidence),
            "perception_gap": self.perception_gap,
            "gap_direction": self.gap_direction,
            "insights": list(self.insights),
            "recommendations": list(self.recommendations),
            "has_perception_gap": self.has_perception_gap(),
            "is_self_aware": self.is_self_aware(),
        }


# =============================================================================
# CREATE REQUESTS — Shared/Curriculum (3 new KuTypes)
# =============================================================================


class MocCreateRequest(CreateRequestBase):
    """Create a MOC Ku (Map of Content — KU organizing KUs). Admin-only, shared."""

    title: str = Field(min_length=1, max_length=200, description="MOC title")
    content: str | None = Field(None, description="MOC content")
    summary: str | None = Field(None, max_length=500, description="Brief summary")
    domain: Domain = Field(default=Domain.KNOWLEDGE, description="Knowledge domain")
    tags: list[str] = Field(default_factory=list, description="Tags")


class LearningStepCreateRequest(CreateRequestBase):
    """Create a LEARNING_STEP Ku (step in a learning path). Admin-only, shared."""

    title: str = Field(min_length=1, max_length=200, description="Step title")
    intent: str = Field(min_length=1, description="Step intent/purpose")
    description: str | None = Field(None, max_length=2000, description="Step description")

    # Curriculum placement
    learning_path_uid: str | None = Field(None, description="Parent LP UID")
    sequence: int | None = Field(None, ge=1, description="Order in learning path")

    # Learning parameters
    mastery_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="Mastery threshold")
    estimated_hours: float = Field(default=1.0, gt=0, description="Estimated hours")
    difficulty: StepDifficulty = Field(
        default=StepDifficulty.MODERATE, description="Step difficulty"
    )

    # Organization
    domain: Domain = Field(default=Domain.PERSONAL, description="Domain")
    priority: Priority = Field(default=Priority.MEDIUM, description="Priority")
    notes: str | None = Field(None, description="Additional notes")
    tags: list[str] = Field(default_factory=list, description="Tags")

    # Knowledge relationships
    primary_knowledge_uids: list[str] = Field(default_factory=list, description="Primary KU UIDs")
    supporting_knowledge_uids: list[str] = Field(
        default_factory=list, description="Supporting KU UIDs"
    )
    prerequisite_step_uids: list[str] = Field(
        default_factory=list, description="Prerequisite step UIDs"
    )
    prerequisite_knowledge_uids: list[str] = Field(
        default_factory=list, description="Prerequisite KU UIDs"
    )


class LearningPathCreateRequest(CreateRequestBase):
    """Create a LEARNING_PATH Ku (ordered sequence of steps). Admin-only, shared."""

    title: str = Field(min_length=1, max_length=200, description="Learning path title")
    description: str | None = Field(None, max_length=2000, description="Path description")
    lp_goal: str = Field(min_length=1, description="Learning path goal statement")
    domain: Domain = Field(description="Knowledge domain")

    # Path characteristics
    lp_type: LpType = Field(default=LpType.STRUCTURED, description="Path type")
    difficulty_level: str = Field(default="intermediate", description="Difficulty level")
    estimated_hours: float | None = Field(None, gt=0.0, description="Total estimated hours")

    # Structure
    prerequisites: list[str] = Field(default_factory=list, description="Prerequisites")
    outcomes: list[str] = Field(default_factory=list, description="Expected outcomes")
    tags: list[str] = Field(default_factory=list, description="Tags")


# =============================================================================
# CREATE REQUESTS — Destination (1 new EntityType)
# =============================================================================


class LifePathCreateRequest(CreateRequestBase):
    """Create a LIFE_PATH Ku (knowledge about your life direction)."""

    title: str = Field(min_length=1, max_length=200, description="Life path title")
    description: str | None = Field(None, max_length=2000, description="Life path description")
    vision_statement: str = Field(min_length=10, max_length=2000, description="Vision statement")
    domain: Domain = Field(default=Domain.PERSONAL, description="Domain")
    tags: list[str] = Field(default_factory=list, description="Tags")


# =============================================================================
# UPDATE REQUEST (shared across all KuTypes)
# =============================================================================


class EntityUpdateRequest(UpdateRequestBase):
    """Update any Ku type. All fields optional.

    Services validate which fields are appropriate per EntityType.
    """

    # --- COMMON ---
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    content: str | None = None
    summary: str | None = Field(None, max_length=500)
    domain: Domain | None = None
    tags: list[str] | None = None
    priority: Priority | None = None

    # --- PROCESSING ---
    status: EntityStatus | None = None
    processor_type: ProcessorType | None = None
    instructions: str | None = None
    processing_error: str | None = None
    processed_content: str | None = None

    # --- FEEDBACK ---
    feedback: str | None = None
    subject_uid: str | None = None

    # --- LEARNING METADATA ---
    complexity: KuComplexity | None = None
    learning_level: LearningLevel | None = None
    sel_category: SELCategory | None = None
    quality_score: float | None = Field(None, ge=0.0, le=1.0)
    estimated_time_minutes: int | None = Field(None, ge=1)
    difficulty_rating: float | None = Field(None, ge=0.0, le=1.0)

    # --- SHARING ---
    visibility: Visibility | None = None

    # --- SCHEDULING (Tasks, Goals, Events, Choices) ---
    due_date: date | None = None
    scheduled_date: date | None = None
    start_date: date | None = None
    target_date: date | None = None
    event_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    decision_deadline: datetime | None = None
    duration_minutes: int | None = Field(None, ge=1, le=480)
    reminder_minutes: int | None = Field(None, ge=0, le=10080)
    recurrence_pattern: RecurrencePattern | None = None
    recurrence_end_date: date | None = None

    # --- PROGRESS (Goals, Tasks) ---
    progress_percentage: float | None = Field(None, ge=0.0, le=100.0)
    current_value: float | None = Field(None, ge=0)
    target_value: float | None = Field(None, ge=0)
    unit_of_measurement: str | None = Field(None, max_length=50)
    measurement_type: MeasurementType | None = None
    progress_weight: float | None = Field(None, ge=0.0)

    # --- STREAK (Habits) ---
    current_streak: int | None = Field(None, ge=0)
    longest_streak: int | None = Field(None, ge=0)
    total_completions: int | None = Field(None, ge=0)
    target_days_per_week: int | None = Field(None, ge=1, le=7)
    preferred_time: str | None = None

    # --- GOAL-SPECIFIC ---
    goal_type: GoalType | None = None
    timeframe: GoalTimeframe | None = None
    why_important: str | None = Field(None, max_length=1000)
    success_criteria: str | None = Field(None, max_length=1000)
    potential_obstacles: list[str] | None = None
    strategies: list[str] | None = None
    vision_statement: str | None = Field(None, max_length=2000)

    # --- HABIT-SPECIFIC ---
    polarity: HabitPolarity | None = None
    category: HabitCategory | None = None
    difficulty: HabitDifficulty | None = None
    cue: str | None = Field(None, max_length=500)
    routine: str | None = Field(None, max_length=1000)
    reward: str | None = Field(None, max_length=500)
    reinforces_identity: str | None = Field(None, max_length=200)
    is_identity_habit: bool | None = None

    # --- EVENT-SPECIFIC ---
    event_type: str | None = None
    location: str | None = Field(None, max_length=500)
    is_online: bool | None = None
    meeting_url: str | None = None
    attendee_emails: list[str] | None = None
    max_attendees: int | None = Field(None, ge=1)

    # --- CHOICE-SPECIFIC ---
    choice_type: ChoiceType | None = None
    decision_criteria: list[str] | None = None
    constraints: list[str] | None = None
    stakeholders: list[str] | None = None
    selected_option_uid: str | None = None
    decision_rationale: str | None = Field(None, max_length=1000)

    # --- PRINCIPLE-SPECIFIC ---
    statement: str | None = Field(None, max_length=500)
    principle_category: PrincipleCategory | None = None
    principle_source: PrincipleSource | None = None
    strength: PrincipleStrength | None = None
    tradition: str | None = Field(None, max_length=100)
    original_source: str | None = Field(None, max_length=200)
    personal_interpretation: str | None = Field(None, max_length=1000)
    origin_story: str | None = Field(None, max_length=2000)
    key_behaviors: list[str] | None = None

    # --- ORGANIZATION ---
    parent_uid: str | None = None
    project: str | None = Field(None, max_length=200)
    assignee: str | None = None

    # --- CURRICULUM STRUCTURE ---
    sequence: int | None = Field(None, ge=1)
    intent: str | None = None
    mastery_threshold: float | None = Field(None, ge=0.0, le=1.0)
    estimated_hours: float | None = Field(None, gt=0)
    learning_path_uid: str | None = None
    lp_goal: str | None = None
    lp_type: LpType | None = None
    difficulty_level: str | None = None
    step_difficulty: StepDifficulty | None = None
    prerequisites: list[str] | None = None
    outcomes: list[str] | None = None
    notes: str | None = None


# =============================================================================
# RESPONSE MODELS
# =============================================================================


class EntityResponse(ResponseBase):
    """API response for any Ku type.

    Contains all fields needed to display any EntityType. Fields that don't apply
    to a specific EntityType will be at their default value (None, 0, [], etc.).
    """

    uid: str
    title: str
    ku_type: EntityType
    user_uid: str | None = None
    parent_ku_uid: str | None = None
    parent_uid: str | None = None
    domain: Domain
    created_by: str | None = None

    # Content
    description: str | None = None
    content: str | None = None
    summary: str = ""
    word_count: int = 0

    # File
    original_filename: str | None = None
    file_type: str | None = None

    # Processing
    status: EntityStatus
    processor_type: ProcessorType | None = None
    processing_error: str | None = None
    priority: Priority | None = None

    # Feedback
    feedback: str | None = None
    feedback_generated_at: datetime | None = None
    subject_uid: str | None = None

    # Learning
    complexity: KuComplexity = KuComplexity.MEDIUM
    learning_level: LearningLevel = LearningLevel.BEGINNER
    sel_category: SELCategory | None = None
    quality_score: float = 0.0
    estimated_time_minutes: int = 15
    difficulty_rating: float = 0.5
    semantic_links: list[str] = Field(default_factory=list)

    # Sharing
    visibility: Visibility = Visibility.PRIVATE

    # Substance tracking
    times_applied_in_tasks: int = 0
    times_practiced_in_events: int = 0
    times_built_into_habits: int = 0
    journal_reflections_count: int = 0
    choices_informed_count: int = 0

    # Scheduling
    due_date: date | None = None
    scheduled_date: date | None = None
    start_date: date | None = None
    target_date: date | None = None
    event_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    decision_deadline: datetime | None = None
    duration_minutes: int | None = None
    recurrence_pattern: RecurrencePattern | None = None

    # Progress
    progress_percentage: float = 0.0
    current_value: float = 0.0
    target_value: float | None = None
    unit_of_measurement: str | None = None
    measurement_type: MeasurementType | None = None

    # Streak (Habits)
    current_streak: int = 0
    longest_streak: int = 0
    total_completions: int = 0
    target_days_per_week: int | None = None

    # Goal-specific
    goal_type: GoalType | None = None
    timeframe: GoalTimeframe | None = None
    vision_statement: str | None = None
    why_important: str | None = None
    success_criteria: str | None = None

    # Habit-specific
    polarity: HabitPolarity | None = None
    category: HabitCategory | None = None
    difficulty: HabitDifficulty | None = None
    cue: str | None = None
    routine: str | None = None
    reward: str | None = None
    is_identity_habit: bool = False

    # Choice-specific
    choice_type: ChoiceType | None = None
    selected_option_uid: str | None = None
    decision_rationale: str | None = None

    # Principle-specific
    statement: str | None = None
    principle_category: PrincipleCategory | None = None
    principle_source: PrincipleSource | None = None
    strength: PrincipleStrength | None = None

    # Curriculum structure
    sequence: int | None = None
    intent: str | None = None
    mastery_threshold: float | None = None
    estimated_hours: float | None = None
    lp_type: LpType | None = None

    # Event-specific
    event_type: str | None = None
    location: str | None = None
    is_online: bool = False

    # Organization
    project: str | None = None
    assignee: str | None = None

    # Meta
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    # Computed
    is_user_owned: bool = False
    is_derived: bool = False
    estimated_reading_time: int = 0

    @classmethod
    def from_dto(cls, dto: "EntityDTO") -> "EntityResponse":
        """Create response from DTO."""
        estimated_reading_time = max(1, dto.word_count // 200) if dto.word_count > 0 else 0

        return cls(
            # Identity
            uid=dto.uid,
            title=dto.title,
            ku_type=dto.ku_type,
            user_uid=dto.user_uid,
            parent_ku_uid=dto.parent_ku_uid,
            parent_uid=dto.parent_uid,
            domain=dto.domain,
            created_by=dto.created_by,
            # Content
            description=dto.description,
            content=dto.content,
            summary=dto.summary,
            word_count=dto.word_count,
            # File
            original_filename=dto.original_filename,
            file_type=dto.file_type,
            # Processing
            status=dto.status,
            processor_type=dto.processor_type,
            processing_error=dto.processing_error,
            priority=dto.priority,
            # Feedback
            feedback=dto.feedback,
            feedback_generated_at=dto.feedback_generated_at,
            subject_uid=dto.subject_uid,
            # Learning
            complexity=dto.complexity,
            learning_level=dto.learning_level,
            sel_category=dto.sel_category,
            quality_score=dto.quality_score,
            estimated_time_minutes=dto.estimated_time_minutes,
            difficulty_rating=dto.difficulty_rating,
            semantic_links=dto.semantic_links,
            # Sharing
            visibility=dto.visibility,
            # Substance tracking
            times_applied_in_tasks=dto.times_applied_in_tasks,
            times_practiced_in_events=dto.times_practiced_in_events,
            times_built_into_habits=dto.times_built_into_habits,
            journal_reflections_count=dto.journal_reflections_count,
            choices_informed_count=dto.choices_informed_count,
            # Scheduling
            due_date=dto.due_date,
            scheduled_date=dto.scheduled_date,
            start_date=dto.start_date,
            target_date=dto.target_date,
            event_date=dto.event_date,
            start_time=dto.start_time,
            end_time=dto.end_time,
            decision_deadline=dto.decision_deadline,
            duration_minutes=dto.duration_minutes,
            recurrence_pattern=dto.recurrence_pattern,
            # Progress
            progress_percentage=dto.progress_percentage,
            current_value=dto.current_value,
            target_value=dto.target_value,
            unit_of_measurement=dto.unit_of_measurement,
            measurement_type=dto.measurement_type,
            # Streak
            current_streak=dto.current_streak,
            longest_streak=dto.best_streak,
            total_completions=dto.total_completions,
            target_days_per_week=dto.target_days_per_week,
            # Goal-specific
            goal_type=dto.goal_type,
            timeframe=dto.timeframe,
            vision_statement=dto.vision_statement,
            why_important=dto.why_important,
            success_criteria=dto.success_criteria,
            # Habit-specific
            polarity=dto.polarity,
            category=dto.habit_category,
            difficulty=dto.habit_difficulty,
            cue=dto.cue,
            routine=dto.routine,
            reward=dto.reward,
            is_identity_habit=dto.is_identity_habit,
            # Choice-specific
            choice_type=dto.choice_type,
            selected_option_uid=dto.selected_option_uid,
            decision_rationale=dto.decision_rationale,
            # Principle-specific
            statement=dto.statement,
            principle_category=dto.principle_category,
            principle_source=dto.principle_source,
            strength=dto.strength,
            # Curriculum structure
            sequence=dto.sequence,
            intent=dto.intent,
            mastery_threshold=dto.mastery_threshold,
            estimated_hours=dto.estimated_hours,
            lp_type=dto.path_type,
            # Event-specific
            event_type=dto.event_type,
            location=dto.location,
            is_online=dto.is_online,
            # Organization
            project=dto.project,
            assignee=dto.assignee,
            # Meta
            tags=dto.tags,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            # Computed
            is_user_owned=dto.user_uid is not None,
            is_derived=dto.parent_ku_uid is not None,
            estimated_reading_time=estimated_reading_time,
        )


class EntityListResponse(ListResponseBase):
    """Response for listing multiple Ku items."""

    items: list[EntityResponse]


# =============================================================================
# ROUTE-SPECIFIC REQUEST MODELS (content management, bulk ops, progress, schedule)
# =============================================================================


class CategorizeEntityRequest(BaseModel):
    """Request to categorize a Ku."""

    category: str = Field(
        ...,
        description="Category from KuCategory constants",
        examples=["daily", "weekly", "reflection", "work"],
    )


class AddTagsRequest(BaseModel):
    """Request to add tags to a Ku."""

    tags: list[str] = Field(
        ...,
        min_length=1,
        description="List of tags to add",
        examples=[["work", "priority", "review"]],
    )


class RemoveTagsRequest(BaseModel):
    """Request to remove tags from a Ku."""

    tags: list[str] = Field(..., min_length=1, description="List of tags to remove")


class BulkCategorizeRequest(BaseModel):
    """Request to categorize multiple Ku."""

    ku_uids: list[str] = Field(..., min_length=1, description="List of Ku UIDs")
    category: str = Field(..., description="Category to assign")


class BulkTagRequest(BaseModel):
    """Request to tag multiple Ku."""

    ku_uids: list[str] = Field(..., min_length=1, description="List of Ku UIDs")
    tags: list[str] = Field(..., min_length=1, description="List of tags to add")


class BulkDeleteRequest(BaseModel):
    """Request to delete multiple Ku."""

    ku_uids: list[str] = Field(..., min_length=1, description="List of Ku UIDs to delete")
    soft_delete: bool = Field(
        default=True,
        description="If True, archive instead of permanent delete",
    )


class ProgressReportGenerateRequest(BaseModel):
    """Request model for on-demand progress Ku generation."""

    time_period: str = Field(
        default="7d",
        description="Time period: 7d, 14d, 30d, or 90d",
        pattern=r"^(7d|14d|30d|90d)$",
    )
    domains: list[str] = Field(
        default_factory=list,
        description="Domains to include (empty = all activity domains)",
    )
    depth: str = Field(
        default="standard",
        description="Report depth: summary, standard, or detailed",
        pattern=r"^(summary|standard|detailed)$",
    )
    include_insights: bool = Field(
        default=True,
        description="Include active insights from InsightStore",
    )


class ScheduleCreateRequest(BaseModel):
    """Request model for creating a Ku generation schedule."""

    schedule_type: str = Field(
        default="weekly",
        description="Schedule frequency: weekly, biweekly, or monthly",
        pattern=r"^(weekly|biweekly|monthly)$",
    )
    day_of_week: int = Field(
        default=0,
        ge=0,
        le=6,
        description="Day of week (0=Monday, 6=Sunday)",
    )
    domains: list[str] = Field(
        default_factory=list,
        description="Domains to include (empty = all)",
    )
    depth: str = Field(
        default="standard",
        description="Report depth: summary, standard, or detailed",
        pattern=r"^(summary|standard|detailed)$",
    )


class ScheduleUpdateRequest(BaseModel):
    """Request model for updating a Ku schedule. All fields optional."""

    schedule_type: str | None = Field(
        None,
        description="Schedule frequency",
        pattern=r"^(weekly|biweekly|monthly)$",
    )
    day_of_week: int | None = Field(None, ge=0, le=6, description="Day of week")
    domains: list[str] | None = Field(None, description="Domains to include")
    depth: str | None = Field(
        None,
        description="Report depth",
        pattern=r"^(summary|standard|detailed)$",
    )
    is_active: bool | None = Field(None, description="Enable/disable schedule")


class AssessmentCreateRequest(BaseModel):
    """Request model for creating a teacher assessment (FEEDBACK_REPORT Ku)."""

    subject_uid: str = Field(..., description="Student being assessed")
    title: str = Field(..., min_length=1, max_length=500, description="Assessment title")
    content: str = Field(..., min_length=1, description="Assessment content (markdown)")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")


# =============================================================================
# LEARNING PATH FILTER & PROGRESS (migrated from lp_request.py)
# =============================================================================


class LearningPathFilterRequest(BaseModel):
    """Filter request for learning path browsing UI.

    Used by FormGenerator for filter form generation.
    Migrated from LpFilterRequest in the old lp_request.py.
    """

    difficulty: str | None = Field(None, description="Filter by difficulty level")
    domain: str | None = Field(None, description="Filter by domain")
    duration: str | None = Field(None, description="Filter by time commitment")


class LearningPathProgressRequest(BaseModel):
    """Request model for updating learning progress on a step.

    Migrated from LpProgressRequest in the old lp_request.py.
    """

    step_uid: str = Field(..., description="Step to update progress for")
    mastery_level: float = Field(..., ge=0.0, le=1.0)
    completed: bool | None = None
    notes: str | None = None
