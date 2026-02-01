"""
Goal DTO (Tier 2 - Transfer)
=============================

Mutable data transfer object for Goal operations.
Used internally by services for data manipulation.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, ClassVar

from core.models.activity_dto_mixin import ActivityDTOMixin

# Import goal-specific enums
# This works without circular import because:
# 1. Enums are defined at top of goal.py (before Goal class)
# 2. GoalDTO import is deferred to end of goal.py
# 3. When this imports enums, Goal class hasn't referenced GoalDTO yet
from core.models.goal.goal import GoalTimeframe, GoalType, MeasurementType
from core.models.shared_enums import Domain, GoalStatus, Priority


@dataclass
class GoalDTO(ActivityDTOMixin):
    """
    Mutable data transfer object for Goal.

    Used by services to:
    - Create new goals
    - Update existing goals
    - Track progress
    - Manage milestones
    """

    # Class variable for UID generation (ActivityDTOMixin)
    _uid_prefix: ClassVar[str] = "goal"

    # Identity
    uid: str
    user_uid: str  # REQUIRED - goal ownership
    title: str
    description: str | None = None
    vision_statement: str | None = None

    # Classification
    goal_type: GoalType = GoalType.OUTCOME
    domain: Domain = Domain.KNOWLEDGE
    timeframe: GoalTimeframe = GoalTimeframe.QUARTERLY

    # Measurement
    measurement_type: MeasurementType = MeasurementType.PERCENTAGE
    target_value: float | None = None
    current_value: float = 0.0
    unit_of_measurement: str | None = None

    # Timeline
    start_date: date | None = None
    target_date: date | None = None
    achieved_date: date | None = None

    # Learning Integration
    parent_goal_uid: str | None = None

    # Atomic Habits Integration (James Clear philosophy)
    # "You do not rise to the level of your goals. You fall to the level of your systems."
    target_identity: str | None = None
    identity_evidence_required: int = 0

    # Curriculum Spine Integration
    source_learning_path_uid: str | None = None
    curriculum_driven: bool = False

    # Choice Integration (INSPIRE → MOTIVATE bridge)
    inspired_by_choice_uid: str | None = None
    selected_choice_option_uid: str | None = None

    # Relationship Context (Phase 1: Making Connections Comprehensible)
    # Capture HOW principles guide and WHY choices create
    guidances: list[dict] = field(default_factory=list)  # List of Guidance dicts,
    derivation: dict | None = None  # Derivation dict or None

    # Milestones (mutable list of dicts)
    milestones: list[dict] = field(default_factory=list)

    # Progress Tracking
    progress_percentage: float = 0.0
    last_progress_update: datetime | None = None
    progress_history: list[dict] = field(default_factory=list)

    # Motivation & Context
    why_important: str | None = None
    success_criteria: str | None = None
    potential_obstacles: list[str] = field(default_factory=list)
    strategies: list[str] = field(default_factory=list)

    # Status
    status: GoalStatus = GoalStatus.PLANNED
    priority: Priority = Priority.MEDIUM

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(
        default_factory=dict
    )  # Rich context storage (graph neighborhoods, etc.)

    # ==========================================================================
    # FACTORY METHODS
    # ==========================================================================

    @classmethod
    def create(
        cls,
        user_uid: str,
        title: str,
        goal_type: GoalType = GoalType.OUTCOME,
        domain: Domain = Domain.KNOWLEDGE,
        timeframe: GoalTimeframe = GoalTimeframe.QUARTERLY,
        measurement_type: MeasurementType = MeasurementType.PERCENTAGE,
        target_date: date | None = None,
        **kwargs: Any,
    ) -> "GoalDTO":
        """
        Factory method to create new GoalDTO with defaults.

        Args:
            user_uid: User UID (REQUIRED - fail-fast philosophy),
            title: Goal title,
            goal_type: Type of goal,
            domain: Knowledge domain,
            timeframe: Time horizon,
            measurement_type: How to measure progress,
            target_date: Target completion date
            **kwargs: Additional fields

        Returns:
            New GoalDTO instance
        """
        # Set start date if not provided
        start_date = kwargs.pop("start_date", date.today())

        return cls._create_activity_dto(
            user_uid=user_uid,
            title=title,
            goal_type=goal_type,
            domain=domain,
            timeframe=timeframe,
            measurement_type=measurement_type,
            target_date=target_date,
            start_date=start_date,
            **kwargs,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoalDTO":
        """
        Create DTO from dictionary.

        Infrastructure fields (e.g., 'embedding', 'embedding_version') are
        automatically filtered out by dto_from_dict. Embeddings are search
        infrastructure stored in Neo4j for vector search, not domain data.

        Args:
            data: Dictionary with goal data

        Returns:
            GoalDTO instance

        See: /docs/patterns/three_tier_type_system.md
        """
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "goal_type": GoalType,
                "domain": Domain,
                "timeframe": GoalTimeframe,
                "measurement_type": MeasurementType,
                "status": GoalStatus,
                "priority": Priority,
            },
            date_fields=["start_date", "target_date", "achieved_date"],
            datetime_fields=["created_at", "updated_at", "last_progress_update"],
            list_fields=[
                "milestones",
                "progress_history",
                "potential_obstacles",
                "strategies",
                "tags",
                "guidances",
            ],
            dict_fields=["metadata"],
        )

    # ==========================================================================
    # UPDATE METHODS
    # ==========================================================================

    def update_from(self, updates: dict[str, Any]) -> None:
        """
        Update DTO fields from dictionary.

        Args:
            updates: Dictionary of fields to update
        """
        from core.models.dto_helpers import update_from_dict

        update_from_dict(
            self,
            updates,
            enum_mappings={
                "goal_type": GoalType,
                "domain": Domain,
                "timeframe": GoalTimeframe,
                "measurement_type": MeasurementType,
                "status": GoalStatus,
                "priority": Priority,
            },
            skip_none=False,
        )

    def update_progress(self, new_value: float, notes: str | None = None) -> None:
        """
        Update goal progress.

        Args:
            new_value: New progress value
            notes: Optional progress notes
        """
        # Store history
        self.progress_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "previous_value": self.current_value,
                "new_value": new_value,
                "notes": notes,
            }
        )

        # Update current value
        if self.measurement_type == MeasurementType.NUMERIC:
            self.current_value = new_value
            if self.target_value:
                self.progress_percentage = min((new_value / self.target_value) * 100, 100.0)
        elif self.measurement_type == MeasurementType.PERCENTAGE:
            self.progress_percentage = min(new_value, 100.0)
            self.current_value = new_value

        self.last_progress_update = datetime.now()
        self.updated_at = datetime.now()

        # Check if achieved
        if self.progress_percentage >= 100.0:
            self.status = GoalStatus.ACHIEVED
            self.achieved_date = date.today()

    def add_milestone(
        self,
        title: str,
        target_date: date,
        description: str | None = None,
        target_value: float | None = None,
    ) -> str:
        """
        Add a milestone to the goal.

        Args:
            title: Milestone title,
            target_date: Target date for milestone,
            description: Optional description,
            target_value: Optional target value

        Returns:
            Milestone UID
        """
        milestone_uid = f"milestone_{uuid.uuid4().hex[:8]}"

        self.milestones.append(
            {
                "uid": milestone_uid,
                "title": title,
                "description": description,
                "target_date": target_date,
                "target_value": target_value,
                "achieved_date": None,
                "is_completed": False,
                "required_knowledge_uids": [],
                "unlocked_knowledge_uids": [],
            }
        )

        self.updated_at = datetime.now()
        return milestone_uid

    def complete_milestone(self, milestone_uid: str) -> None:
        """
        Mark a milestone as completed.

        Args:
            milestone_uid: UID of milestone to complete
        """
        for milestone in self.milestones:
            if milestone["uid"] == milestone_uid:
                milestone["is_completed"] = True
                milestone["achieved_date"] = date.today()
                break

        # Recalculate progress if milestone-based
        if self.measurement_type == MeasurementType.MILESTONE:
            completed = sum(1 for m in self.milestones if m["is_completed"])
            total = len(self.milestones)
            if total > 0:
                self.progress_percentage = (completed / total) * 100

        self.updated_at = datetime.now()

    def revise(
        self, new_target_date: date | None = None, new_target_value: float | None = None
    ) -> None:
        """
        Revise goal targets.

        Args:
            new_target_date: New target date
            new_target_value: New target value

        Note:
            Revising a goal does not change its status (ACTIVE, PLANNED, etc.).
            Status remains unchanged - only the targets are updated.
        """
        if new_target_date:
            self.target_date = new_target_date
        if new_target_value:
            self.target_value = new_target_value

        # Note: Status intentionally NOT changed - goal keeps its current status
        self.updated_at = datetime.now()

    # ==========================================================================
    # CONVERSION METHODS
    # ==========================================================================

    def to_dict(self) -> dict[str, Any]:
        """
        Convert DTO to dictionary for storage.

        Returns:
            Dictionary representation
        """
        from core.models.dto_helpers import dto_to_dict

        return dto_to_dict(
            self,
            enum_fields=[
                "goal_type",
                "domain",
                "timeframe",
                "measurement_type",
                "status",
                "priority",
            ],
            date_fields=["start_date", "target_date", "achieved_date"],
            datetime_fields=["created_at", "updated_at", "last_progress_update"],
            nested_date_fields={"milestones": ["target_date", "achieved_date"]},
        )
