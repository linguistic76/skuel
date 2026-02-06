"""
Group Domain Model
===================

Three-tier type system for Groups.

A Group represents a teacher-student class (e.g., "Physics 101 - Spring 2026").
Teachers create groups and add students. Groups mediate all teacher-student
relationships — no direct TEACHES relationship.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ============================================================================
# TIER 2 - DTO (Transfer Layer)
# ============================================================================


@dataclass
class GroupDTO:
    """
    Mutable data transfer object for groups.

    Used for:
    - Moving data between service and persistence layers
    - Constructing groups before freezing into domain models
    - Database serialization/deserialization
    """

    uid: str
    name: str
    description: str | None = None
    owner_uid: str = ""
    is_active: bool = True
    max_members: int | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "uid": self.uid,
            "name": self.name,
            "description": self.description,
            "owner_uid": self.owner_uid,
            "is_active": self.is_active,
            "max_members": self.max_members,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": self.metadata,
        }


# ============================================================================
# TIER 3 - Domain Model (Core Business Logic)
# ============================================================================


@dataclass(frozen=True)
class Group:
    """
    Immutable domain model for groups.

    A Group is a container for teacher-student relationships:
    - One teacher (owner) creates and manages the group
    - Students are added via MEMBER_OF relationship
    - Assignments (ReportProjects with scope=ASSIGNED) target groups via FOR_GROUP
    """

    uid: str
    name: str
    description: str | None = None
    owner_uid: str = ""
    is_active: bool = True
    max_members: int | None = None
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

    def is_valid(self) -> bool:
        """Check if group has minimum required fields."""
        return bool(self.name and self.owner_uid)

    def get_summary(self) -> str:
        """Get one-line summary of group."""
        status = "active" if self.is_active else "inactive"
        return f"{self.name} ({status})"


# ============================================================================
# CONVERSION FUNCTIONS
# ============================================================================


def group_dto_to_pure(dto: GroupDTO) -> Group:
    """Convert GroupDTO (Tier 2) to Group (Tier 3)."""
    return Group(
        uid=dto.uid,
        name=dto.name,
        description=dto.description,
        owner_uid=dto.owner_uid,
        is_active=dto.is_active,
        max_members=dto.max_members,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
        metadata=dto.metadata.copy() if dto.metadata else {},
    )


def group_pure_to_dto(pure: Group) -> GroupDTO:
    """Convert Group (Tier 3) to GroupDTO (Tier 2)."""
    return GroupDTO(
        uid=pure.uid,
        name=pure.name,
        description=pure.description,
        owner_uid=pure.owner_uid,
        is_active=pure.is_active,
        max_members=pure.max_members,
        created_at=pure.created_at,
        updated_at=pure.updated_at,
        metadata=dict(pure.metadata),
    )


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================


def create_group(
    uid: str,
    name: str,
    owner_uid: str,
    description: str | None = None,
    max_members: int | None = None,
) -> Group:
    """
    Factory function to create a new group.

    Args:
        uid: Unique identifier (e.g., "group_physics-101_abc123")
        name: Display name (e.g., "Physics 101 - Spring 2026")
        owner_uid: Teacher who owns this group
        description: Optional description
        max_members: Optional member cap

    Returns:
        Immutable Group instance
    """
    return Group(
        uid=uid,
        name=name,
        description=description,
        owner_uid=owner_uid,
        is_active=True,
        max_members=max_members,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        metadata={},
    )
