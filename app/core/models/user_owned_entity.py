"""
UserOwnedEntity - Intermediate Base for User-Owned Domain Models
=================================================================

Adds user ownership fields (user_uid, priority) to Entity for domains where
entities belong to a specific user: Activity Domains (Task, Goal, Habit, Event,
Choice, Principle), Submission types (Journal, ActivityReport,
SubmissionFeedback), and LifePath.

Shared/curriculum types (Curriculum, LearningStep, LearningPath, Exercise,
Resource) inherit directly from Entity and do NOT have these fields.

Hierarchy:
    Entity (~19 fields: identity, content, status, visibility, meta, embedding)
    ├── UserOwnedEntity(Entity) +2 fields (user_uid, priority)
    │   ├── Task, Goal, Habit, Event, Choice, Principle
    │   ├── Submission → Journal, SubmissionFeedback
    │   ├── ActivityReport (activity-level feedback — no file fields)
    │   └── LifePath
    ├── Curriculum(Entity) → LearningStep, LearningPath, Exercise
    └── Resource(Entity)

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass

from core.models.entity import Entity
from core.models.enums.metadata_enums import Visibility


@dataclass(frozen=True)
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
    user_uid: str | None = None  # Owner user UID (e.g. "user_john")
    priority: str | None = None  # Priority enum value (LOW/MEDIUM/HIGH/CRITICAL)

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

    def can_view(self, viewer_uid: str, shared_user_uids: set[str] | None = None) -> bool:
        """
        Check if a user can view this entity.

        Access granted if:
        - Entity is PUBLIC
        - Viewer is the owner
        - Entity is SHARED and viewer is in shared_user_uids
        """
        if self.visibility == Visibility.PUBLIC:
            return True
        if self.user_uid and viewer_uid == self.user_uid:
            return True
        if self.visibility == Visibility.SHARED and shared_user_uids:
            return viewer_uid in shared_user_uids
        return False
