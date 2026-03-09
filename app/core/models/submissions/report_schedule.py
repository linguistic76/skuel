"""
ReportSchedule Models (Tier 2 + Tier 3)
========================================

A ReportSchedule defines recurring progress report generation:
- Schedule type (weekly, biweekly, monthly)
- Which domains to include
- Progress depth (summary, standard, detailed)
- Active/inactive toggle

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.enums.submissions_enums import ProgressDepth, ScheduleType

# ============================================================================
# TIER 2 - DTO (Transfer Layer)
# ============================================================================


@dataclass
class ReportScheduleDTO:
    """
    Mutable data transfer object for report generation schedules.

    Used for moving data between service and persistence layers.
    """

    uid: str
    user_uid: str
    schedule_type: str = "weekly"
    day_of_week: int = 0  # 0=Monday, 6=Sunday
    domains: list[str] | None = None
    depth: str = "standard"
    is_active: bool = True
    last_generated_at: datetime | None = None
    next_due_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "uid": self.uid,
            "user_uid": self.user_uid,
            "schedule_type": self.schedule_type,
            "day_of_week": self.day_of_week,
            "domains": self.domains,
            "depth": self.depth,
            "is_active": self.is_active,
            "last_generated_at": self.last_generated_at.isoformat()
            if self.last_generated_at
            else None,
            "next_due_at": self.next_due_at.isoformat() if self.next_due_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": self.metadata,
        }


# ============================================================================
# TIER 3 - Domain Model (Core Business Logic)
# ============================================================================


@dataclass(frozen=True)
class ReportSchedule:
    """
    Immutable domain model for report generation schedules.

    A ReportSchedule defines when and how progress reports are
    automatically generated for a user.
    """

    uid: str
    user_uid: str
    schedule_type: ScheduleType = ScheduleType.WEEKLY
    day_of_week: int = 0  # 0=Monday, 6=Sunday
    domains: list[str] = field(default_factory=list)
    depth: ProgressDepth = ProgressDepth.STANDARD
    is_active: bool = True
    last_generated_at: datetime | None = None
    next_due_at: datetime | None = None
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize timestamps with proper defaults."""
        now = datetime.now()
        if self.created_at is None:
            object.__setattr__(self, "created_at", now)
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", now)

    def is_due(self) -> bool:
        """Check if this schedule is due for generation."""
        if not self.is_active or not self.next_due_at:
            return False
        return datetime.now() >= self.next_due_at

    def get_summary(self) -> str:
        """Get one-line summary of schedule."""
        status = "active" if self.is_active else "inactive"
        return f"{self.schedule_type.get_display_name()} ({status})"


# ============================================================================
# CONVERSION FUNCTIONS
# ============================================================================


def report_schedule_dto_to_domain(dto: ReportScheduleDTO) -> ReportSchedule:
    """Convert ReportScheduleDTO (Tier 2) to ReportSchedule (Tier 3)."""
    return ReportSchedule(
        uid=dto.uid,
        user_uid=dto.user_uid,
        schedule_type=ScheduleType(dto.schedule_type) if dto.schedule_type else ScheduleType.WEEKLY,
        day_of_week=dto.day_of_week,
        domains=list(dto.domains) if dto.domains else [],
        depth=ProgressDepth(dto.depth) if dto.depth else ProgressDepth.STANDARD,
        is_active=dto.is_active,
        last_generated_at=dto.last_generated_at,
        next_due_at=dto.next_due_at,
        created_at=dto.created_at or datetime.now(),
        updated_at=dto.updated_at or datetime.now(),
        metadata=dto.metadata.copy() if dto.metadata else {},
    )


def report_schedule_domain_to_dto(schedule: ReportSchedule) -> ReportScheduleDTO:
    """Convert ReportSchedule (Tier 3) to ReportScheduleDTO (Tier 2)."""
    return ReportScheduleDTO(
        uid=schedule.uid,
        user_uid=schedule.user_uid,
        schedule_type=schedule.schedule_type.value
        if isinstance(schedule.schedule_type, ScheduleType)
        else schedule.schedule_type,
        day_of_week=schedule.day_of_week,
        domains=list(schedule.domains) if schedule.domains else None,
        depth=schedule.depth.value if isinstance(schedule.depth, ProgressDepth) else schedule.depth,
        is_active=schedule.is_active,
        last_generated_at=schedule.last_generated_at,
        next_due_at=schedule.next_due_at,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
        metadata=dict(schedule.metadata),
    )
