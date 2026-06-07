"""
GoalDTO - Goal-Specific DTO (Tier 2 - Transfer)
=================================================

Extends UserOwnedDTO with 24 goal-specific fields matching the Goal
frozen dataclass (Tier 3): classification, measurement, timeline,
progress, motivation, cross-domain links, identity, and flags.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── GoalDTO(UserOwnedDTO) +24 goal-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from datetime import date, datetime

from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.goal_enums import GoalTimeframe, GoalType, MeasurementType
from core.models.enums.metadata_enums import Visibility
from core.models.user_owned_dto import UserOwnedDTO


@dataclass
class GoalDTO(UserOwnedDTO):
    """
    Mutable DTO for goals (EntityType.GOAL).

    Extends UserOwnedDTO with 24 goal-specific fields:
    - Classification (3): goal_type, timeframe, measurement_type
    - Measurement (3): target_value, current_value, unit_of_measurement
    - Timeline (3): start_date, target_date, achieved_date
    - Progress (4): milestones, progress_percentage, last_progress_update, progress_history
    - Motivation (5): vision_statement, why_important, success_criteria, potential_obstacles, strategies
    - Cross-domain links (3): fulfills_goal_uid, source_path_step_uid, selected_choice_option_uid (Choice inspiration is a graph edge — see Goal model)
    - Identity (2): target_identity, identity_evidence_required
    """

    # =========================================================================
    # CLASSIFICATION
    # =========================================================================
    goal_type: GoalType | None = None
    timeframe: GoalTimeframe | None = None
    measurement_type: MeasurementType | None = None

    # =========================================================================
    # MEASUREMENT
    # =========================================================================
    target_value: float | None = None
    current_value: float = 0.0
    unit_of_measurement: str | None = None

    # =========================================================================
    # TIMELINE
    # =========================================================================
    start_date: date | None = None
    target_date: date | None = None
    achieved_date: date | None = None

    # =========================================================================
    # PROGRESS
    # =========================================================================
    milestones: list[dict[str, Any]] = field(default_factory=list)
    progress_percentage: float = 0.0
    last_progress_update: datetime | None = None
    progress_history: list[dict[str, Any]] = field(default_factory=list)
    dual_track_checkins: list[dict[str, Any]] = field(default_factory=list)

    # =========================================================================
    # MOTIVATION
    # =========================================================================
    vision_statement: str | None = None
    why_important: str | None = None
    success_criteria: str | None = None
    potential_obstacles: list[str] = field(default_factory=list)
    strategies: list[str] = field(default_factory=list)

    # =========================================================================
    # CROSS-DOMAIN LINKS
    # =========================================================================
    fulfills_goal_uid: str | None = None
    source_path_step_uid: str | None = None
    # Choice inspiration lives in the graph as (Goal)-[:INSPIRED_BY_CHOICE]->(Choice).
    selected_choice_option_uid: str | None = None

    # =========================================================================
    # IDENTITY
    # =========================================================================
    target_identity: str | None = None
    identity_evidence_required: int = 0

    # =========================================================================
    # PS+ACTIVITY LIFECYCLE
    # =========================================================================
    # Back-reference is (Goal)-[:SPAWNED_FROM]->(GoalTemplate).
    engagement_state: Literal["engaged", "owned"] | None = None

    # =========================================================================
    # FACTORY METHOD
    # =========================================================================

    @classmethod
    def create_goal(cls, user_uid: UserUID, title: str, **kwargs: Any) -> GoalDTO:
        """Create a GoalDTO with generated UID and correct defaults."""
        from core.utils.uid_generator import UIDGenerator

        uid = kwargs.pop("uid", None)
        if not uid:
            if title:
                uid = UIDGenerator.generate_uid("goal", title)
            else:
                uid = UIDGenerator.generate_random_uid("goal")

        kwargs.setdefault("status", EntityStatus.DRAFT)
        kwargs.setdefault("visibility", Visibility.PRIVATE)

        return cls(
            uid=uid,
            title=title,
            entity_type=EntityType.GOAL,
            user_uid=user_uid,
            **kwargs,
        )

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary using generic helper."""
        from core.models.dto_helpers import dto_to_dict

        return dto_to_dict(
            self,
            enum_fields=[
                "entity_type",
                "status",
                "domain",
                "visibility",
                "goal_type",
                "timeframe",
                "measurement_type",
            ],
            date_fields=["start_date", "target_date", "achieved_date"],
            datetime_fields=["created_at", "updated_at", "last_progress_update"],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoalDTO:
        """Create GoalDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "goal_type": GoalType,
                "timeframe": GoalTimeframe,
                "measurement_type": MeasurementType,
            },
            date_fields=["start_date", "target_date", "achieved_date"],
            datetime_fields=["created_at", "updated_at", "last_progress_update"],
            list_fields=[
                "tags",
                "potential_obstacles",
                "strategies",
                "milestones",
                "progress_history",
                "dual_track_checkins",
            ],
            dict_fields=["metadata"],
        )

    # =========================================================================
    # UPDATE
    # =========================================================================

    def update_from(self, updates: dict[str, Any]) -> None:
        """Update DTO fields from a dictionary."""
        from core.models.dto_helpers import update_from_dict

        update_from_dict(
            self,
            updates,
            allowed_fields={
                # EntityDTO fields
                "title",
                "content",
                "summary",
                "description",
                "word_count",
                "domain",
                "status",
                "tags",
                "metadata",
                # UserOwnedDTO fields
                "priority",
                "visibility",
                # Goal-specific fields
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
                "dual_track_checkins",
                "vision_statement",
                "why_important",
                "success_criteria",
                "potential_obstacles",
                "strategies",
                "fulfills_goal_uid",
                "source_path_step_uid",
                "selected_choice_option_uid",
                "target_identity",
                "identity_evidence_required",
                "engagement_state",
            },
            enum_mappings={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "goal_type": GoalType,
                "timeframe": GoalTimeframe,
                "measurement_type": MeasurementType,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, GoalDTO):
            return False
        return self.uid == other.uid
