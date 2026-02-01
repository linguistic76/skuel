"""
Choice DTO Models (Tier 2 - Transfer)
======================================

Mutable data transfer objects for choice domain.
Used for data movement between layers and API responses.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

from core.models.activity_dto_mixin import ActivityDTOMixin
from core.models.choice.choice import ChoiceStatus, ChoiceType
from core.models.shared_enums import Domain, Priority
from core.services.protocols import get_enum_value


@dataclass
class ChoiceOptionDTO:
    """Mutable DTO for choice options."""

    # Identity
    uid: str
    title: str
    description: str

    # Evaluation
    feasibility_score: float = 0.5
    risk_level: float = 0.5
    potential_impact: float = 0.5
    resource_requirement: float = 0.5

    # Metadata
    estimated_duration: int | None = None
    dependencies: list[str] = None
    tags: list[str] = None

    def __post_init__(self) -> None:
        """Initialize empty lists."""
        if self.dependencies is None:
            self.dependencies = []
        if self.tags is None:
            self.tags = []


@dataclass
class ChoiceDTO(ActivityDTOMixin):
    """Mutable DTO for choices."""

    # Class variable for UID generation (ActivityDTOMixin)
    _uid_prefix: ClassVar[str] = "choice"

    # Identity
    uid: str
    title: str
    description: str
    user_uid: str

    # Choice Configuration
    choice_type: str = ChoiceType.MULTIPLE.value
    status: str = ChoiceStatus.PENDING.value
    priority: str = Priority.MEDIUM.value
    domain: str = Domain.PERSONAL.value

    # Options and Decision
    options: list[ChoiceOptionDTO] = None

    selected_option_uid: str | None = None
    decision_rationale: str | None = None

    # Context
    decision_criteria: list[str] = None

    constraints: list[str] = None

    stakeholders: list[str] = None

    # Timing
    decision_deadline: datetime | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None

    decided_at: datetime | None = None

    # Outcome Tracking
    satisfaction_score: int | None = None

    actual_outcome: str | None = None
    lessons_learned: list[str] = None

    # Curriculum Integration (Educate)
    # informed_by_knowledge_uids removed - query via service.relationships.get_choice_knowledge()
    # opens_learning_paths removed - query via service.relationships.get_choice_learning_paths()
    # requires_knowledge_for_decision removed - query via service.relationships.get_choice_required_knowledge()
    # aligned_with_principles removed - query via service.relationships.get_choice_principles()

    # Inspiration & Possibility (Inspire)
    inspiration_type: str | None = (
        None  # 'career_path', 'life_direction', 'skill_acquisition', 'project_idea',
    )
    expands_possibilities: bool = False

    vision_statement: str | None = None

    # Computed fields (not stored)
    complexity_score: float | None = None

    time_until_deadline_minutes: int | None = None
    is_overdue: bool = False

    inspiration_strength: float | None = None
    metadata: dict[str, Any] = None  # Rich context storage (graph neighborhoods, etc.)

    def __post_init__(self) -> None:
        """
        Initialize empty lists and set defaults.

        Migration Note (November 8, 2025):
        Removed initialization of deprecated graph-native relationship fields
        during Phase 2 migration to relationship-based architecture.
        """
        if self.options is None:
            self.options = []
        if self.decision_criteria is None:
            self.decision_criteria = []
        if self.constraints is None:
            self.constraints = []
        if self.stakeholders is None:
            self.stakeholders = []
        if self.lessons_learned is None:
            self.lessons_learned = []
        # Relationship field initialization removed (Phase 2 migration):
        # - informed_by_knowledge_uids → service.relationships.get_choice_knowledge()
        # - opens_learning_paths → service.relationships.get_choice_learning_paths()
        # - requires_knowledge_for_decision → service.relationships.get_choice_required_knowledge()
        # - aligned_with_principles → service.relationships.get_choice_principles()
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict[str, Any]:
        """Convert DTO to dictionary for database operations."""
        from core.models.dto_helpers import dto_to_dict

        return dto_to_dict(
            self,
            enum_fields=["choice_type", "status", "priority", "domain"],
            datetime_fields=["decision_deadline", "created_at", "updated_at", "decided_at"],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChoiceDTO":
        """
        Create DTO from dictionary (typically from database/API).

        Infrastructure fields (e.g., 'embedding') are automatically filtered out
        by dto_from_dict. Embeddings are search infrastructure, not domain data.

        Args:
            data: Dictionary with choice data

        Returns:
            ChoiceDTO instance
        """
        from core.models.dto_helpers import (
            dto_from_dict,
            ensure_list_fields,
        )

        # Make a copy to avoid mutating the original
        data = dict(data)

        # Handle options list (convert dicts to ChoiceOptionDTO if needed)
        if data.get("options"):
            options = []
            for opt in data["options"]:
                if isinstance(opt, dict):
                    # Ensure option list fields
                    if opt.get("dependencies") is None:
                        opt["dependencies"] = []
                    if opt.get("tags") is None:
                        opt["tags"] = []
                    options.append(ChoiceOptionDTO(**opt))
                elif isinstance(opt, ChoiceOptionDTO):
                    options.append(opt)
            data["options"] = options

        # Use generic dto_from_dict with automatic field filtering
        # This filters out infrastructure fields like 'embedding' automatically
        return dto_from_dict(
            cls,
            data,
            enum_fields={},  # Enums stored as strings in ChoiceDTO
            datetime_fields=["decision_deadline", "created_at", "updated_at", "decided_at"],
            list_fields=["decision_criteria", "constraints", "stakeholders", "lessons_learned"],
            dict_fields=["metadata"],
        )

    @classmethod
    def create(
        cls,
        user_uid: str,
        title: str,
        description: str,
        priority: Priority = Priority.MEDIUM,
        domain: Domain = Domain.PERSONAL,
        deadline: datetime | None = None,
    ) -> "ChoiceDTO":
        """
        Factory method to create new ChoiceDTO with generated UID.

        Args:
            user_uid: User UID (REQUIRED - fail-fast philosophy)
            title: Choice title
            description: Choice description
            priority: Choice priority
            domain: Life domain
            deadline: Decision deadline

        Returns:
            ChoiceDTO with generated UID
        """
        return cls._create_activity_dto(
            user_uid=user_uid,
            title=title,
            description=description,
            priority=get_enum_value(priority),
            domain=get_enum_value(domain),
            decision_deadline=deadline,
            status=ChoiceStatus.PENDING.value,
        )


@dataclass
class ChoiceCreateDTO:
    """DTO for creating new choices."""

    title: str
    description: str
    user_uid: str
    choice_type: str = ChoiceType.MULTIPLE.value
    priority: str = Priority.MEDIUM.value
    domain: str = Domain.PERSONAL.value
    decision_deadline: datetime | None = None
    decision_criteria: list[str] = None
    constraints: list[str] = None
    stakeholders: list[str] = None

    def __post_init__(self) -> None:
        """Initialize empty lists."""
        if self.decision_criteria is None:
            self.decision_criteria = []
        if self.constraints is None:
            self.constraints = []
        if self.stakeholders is None:
            self.stakeholders = []


@dataclass
class ChoiceUpdateDTO:
    """DTO for updating existing choices."""

    uid: str
    title: str | None = None
    description: str | None = None

    choice_type: str | None = None
    priority: str | None = None

    domain: str | None = None
    status: str | None = None

    selected_option_uid: str | None = None
    decision_rationale: str | None = None

    decision_deadline: datetime | None = None
    satisfaction_score: int | None = None

    actual_outcome: str | None = None
    lessons_learned: list[str] = None

    def __post_init__(self) -> None:
        """Initialize empty lists."""
        if self.lessons_learned is None:
            self.lessons_learned = []


@dataclass
class ChoiceOptionCreateDTO:
    """DTO for creating choice options."""

    title: str
    description: str
    choice_uid: str
    feasibility_score: float = 0.5
    risk_level: float = 0.5
    potential_impact: float = 0.5
    resource_requirement: float = 0.5
    estimated_duration: int | None = None
    dependencies: list[str] = None
    tags: list[str] = None

    def __post_init__(self) -> None:
        """Initialize empty lists."""
        if self.dependencies is None:
            self.dependencies = []
        if self.tags is None:
            self.tags = []


@dataclass
class ChoiceOptionUpdateDTO:
    """DTO for updating choice options."""

    uid: str
    title: str | None = None
    description: str | None = None

    feasibility_score: float | None = None
    risk_level: float | None = None

    potential_impact: float | None = None
    resource_requirement: float | None = None

    estimated_duration: int | None = None
    dependencies: list[str] = None

    tags: list[str] = None

    def __post_init__(self) -> None:
        """Initialize empty lists."""
        if self.dependencies is None:
            self.dependencies = []
        if self.tags is None:
            self.tags = []


@dataclass
class ChoiceDecisionDTO:
    """DTO for making a decision on a choice."""

    choice_uid: str
    selected_option_uid: str
    decision_rationale: str | None = None
    decided_at: datetime | None = None

    def __post_init__(self) -> None:
        """Set default decision time."""
        if self.decided_at is None:
            self.decided_at = datetime.now()


@dataclass
class ChoiceEvaluationDTO:
    """DTO for evaluating choice outcomes."""

    choice_uid: str
    satisfaction_score: int  # 1-5 scale
    actual_outcome: str
    lessons_learned: list[str] = None

    def __post_init__(self) -> None:
        """Initialize empty lists."""
        if self.lessons_learned is None:
            self.lessons_learned = []


@dataclass
class ChoiceFilterDTO:
    """DTO for filtering choices."""

    user_uid: str
    status: str | None = None
    priority: str | None = None
    domain: str | None = None
    choice_type: str | None = None
    is_overdue: bool | None = None
    has_deadline: bool | None = None
    limit: int = 50
    offset: int = 0


@dataclass
class ChoiceAnalyticsDTO:
    """DTO for choice analytics and insights."""

    user_uid: str
    total_choices: int = 0
    pending_choices: int = 0

    decided_choices: int = 0
    overdue_choices: int = 0

    average_satisfaction: float | None = None
    average_decision_time_days: float | None = None

    most_common_priority: str | None = None
    decision_patterns: dict[str, Any] = None

    complexity_distribution: dict[str, int] = None

    def __post_init__(self) -> None:
        """Initialize empty dictionaries."""
        if self.decision_patterns is None:
            self.decision_patterns = {}
        if self.complexity_distribution is None:
            self.complexity_distribution = {}
