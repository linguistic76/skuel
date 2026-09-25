"""
UserOwnedEntity - Intermediate Base for User-Owned Domain Models
=================================================================

Adds user ownership fields (user_uid, priority) to Entity for domains where
entities belong to a specific user: Activity Domains (Task, Goal, Habit, Event,
Choice, Principle), Submission types (Journal, ActivityReport,
EntryReport), and LifePath.

Shared/curriculum types (Curriculum, PathStep, LearningPath, Exercise,
Resource) inherit directly from Entity and do NOT have these fields.

Hierarchy:
    Entity (~19 fields: identity, content, status, visibility, meta, embedding)
    ├── UserOwnedEntity(Entity) +2 fields (user_uid, priority)
    │   ├── Task, Goal, Habit, Event, Choice, Principle
    │   ├── UserEntry (ADR-054 — replaces ExerciseSubmission/JeInput/JeOutput)
    │   ├── EntryReport, ActivityReport (activity-level feedback — no file fields)
    │   └── LifePath
    ├── Curriculum(Entity) → PathStep, LearningPath, Exercise
    └── Resource(Entity)

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass

from core.models.entity import Entity
from core.models.enums.metadata_enums import Visibility
from core.models.type_hints import UserUID


@dataclass(frozen=True, kw_only=True)
class UserOwnedEntity(Entity):
    """
    Intermediate frozen dataclass for user-owned entities.

    Adds user_uid and priority to Entity. Overrides visibility default
    from PUBLIC (shared types) to PRIVATE (user-owned types).

    All activity domains, submission types, and LifePath inherit from this.
    """

    # =========================================================================
    # USER OWNERSHIP
    # =========================================================================
    user_uid: (
        UserUID  # Owner user UID (e.g. "user_john") — required on every persisted UserOwnedEntity
    )
    priority: str | None = None  # Priority enum value (LOW/MEDIUM/HIGH)

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    def __post_init__(self) -> None:
        """Default visibility to PRIVATE for user-owned entities."""
        # Set PRIVATE before calling Entity.__post_init__ (which defaults PUBLIC)
        if self.visibility is None:
            object.__setattr__(self, "visibility", Visibility.PRIVATE)
        super().__post_init__()

    # =========================================================================
    # USER OWNERSHIP CHECKS
    # =========================================================================

    @property
    def is_user_owned(self) -> bool:
        """Check if this entity has an owner."""
        return self.user_uid is not None
