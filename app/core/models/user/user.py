"""
User Domain Model
=================

Core user domain model following the three-tier architecture.
This is a frozen dataclass (immutable) that represents the core user entity.

Key principles:
- User stores identity and preferences
- Activities are managed as UserOwnedEntity types
- Relationships handled by unified relationship system

Three-tier position:
- External: user_schemas.py (Pydantic validation)
- Transfer: user_dto.py (mutable DTOs)
- Core: user.py (this file, frozen domain model)

-4 Integration (October 3, 2025):



"""

__version__ = "2.1"


from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.enums import EnergyLevel, JournalTier, LearningLevel, TimeOfDay, UserRole
from core.models.query_types import QueryIntent
from core.models.type_hints import EntityUID, UserUID


def _default_energy_pattern() -> dict[TimeOfDay, EnergyLevel]:
    """Create default energy pattern for user preferences."""
    return {
        TimeOfDay.MORNING: EnergyLevel.MEDIUM,
        TimeOfDay.AFTERNOON: EnergyLevel.HIGH,
        TimeOfDay.EVENING: EnergyLevel.LOW,
    }


# ============================================================================
# USER PREFERENCES
# ============================================================================


@dataclass(frozen=True)
class UserPreferences:
    """
    User preferences for learning, scheduling, and interaction.

    Immutable value object containing all user preferences.
    """

    # Learning preferences
    learning_level: LearningLevel = LearningLevel.INTERMEDIATE
    preferred_modalities: list[str] = field(default_factory=list)  # video, reading, interactive
    preferred_subjects: list[str] = field(default_factory=list)

    # Scheduling preferences
    preferred_time_of_day: TimeOfDay = TimeOfDay.ANYTIME
    available_minutes_daily: int = 60
    energy_pattern: dict[TimeOfDay, EnergyLevel] = field(default_factory=_default_energy_pattern)

    # Notification preferences
    enable_reminders: bool = True
    reminder_minutes_before: int = 15
    daily_summary_time: str | None = "09:00"  # HH:MM format

    # Display preferences
    theme: str = "light"  # light, dark, auto
    language: str = "en"
    timezone: str = "UTC"

    # Goal preferences
    weekly_task_goal: int = 10
    daily_habit_goal: int = 3
    monthly_learning_hours: int = 20

    # Vault bridge (ADR-070) — user must acknowledge one-time notice before
    # SKUEL writes 🆔 IDs or [x] status back to their vault files.
    vault_write_consent: bool = False


# ============================================================================
# SIMPLIFIED USER MODEL
# ============================================================================


@dataclass(frozen=True, kw_only=True)
class User:
    """
    Core user domain model.

    This immutable model focuses on identity and preferences, delegating:
    - Activity management to UserOwnedEntity types
    - Relationships to the unified relationship system
    """

    # Core identity
    uid: str
    title: str  # We'll use title as username for consistency
    description: str = ""
    email: str = ""
    display_name: str = ""
    password_hash: str = ""  # Bcrypt password hash (graph-native authentication)

    # User preferences
    preferences: UserPreferences = field(default_factory=UserPreferences)

    # Active entities
    # These are just UIDs - the actual entities are stored elsewhere
    active_entity_uids: set[str] = field(default_factory=set)
    archived_entity_uids: set[str] = field(default_factory=set)

    # Pinned entities - GRAPH-NATIVE: Relationships stored as Neo4j edges
    # Graph relationship: (user)-[:PINNED {order: int}]->(entity)

    # Interests and goals
    interests: list[str] = field(default_factory=list)
    achievements: list[str] = field(default_factory=list)

    # Current goals - GRAPH-NATIVE: Relationships stored as Neo4j edges
    # Graph relationship: (user)-[:PURSUING_GOAL]->(goal)

    # Social connections - GRAPH-NATIVE: Relationships stored as Neo4j edges
    # Graph relationship: (user)-[:FOLLOWS]->(other_user)
    # Graph relationship: (user)-[:MEMBER_OF]->(team)
    # Note: follower_uids removed - use inverse query: MATCH (follower)-[:FOLLOWS]->(user)

    # Account metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_active_at: datetime | None = None
    last_login_at: datetime | None = None

    # Account status
    is_active: bool = True
    is_verified: bool = False
    is_premium: bool = False

    # User role (four-tier hierarchy)
    # REGISTERED < MEMBER < TEACHER < ADMIN
    role: UserRole = field(default_factory=UserRole.default)

    # Journal workflow tier — orthogonal to UserRole
    # STANDARD: continuous single-response workflow (default)
    # FOUNDER:  full three-stage DNWF workflow (linguistic76 pilot)
    journal_tier: JournalTier = field(default_factory=JournalTier.default)

    # Settings
    settings: dict[str, Any] = field(default_factory=dict)

    # Dual-track perception-gap check-ins (ADR-030), user-level dimensions only.
    # Keyed by DualTrackDimension value (productivity/engagement/decision_quality);
    # each value is an append-only log of snapshots (DualTrackResult.to_checkin_snapshot),
    # capped at DualTrackCheckin.HISTORY_LIMIT. This is the user-level analog of the
    # per-entity `dual_track_checkins: tuple[dict, ...]` field on Goal/Habit/Principle —
    # user-level dims (Tasks/Events/Choices) assess the user across all their entities
    # and have no :Entity row to attach to, so they persist here on the :User node.
    # Round-trips as a JSON property via neo4j_mapper (dict -> json -> dict).
    # Written by UserService.append_dual_track_checkin; read by the Self Check-In page
    # and UserContextIntelligence.get_cross_domain_perception_analysis.
    dual_track_checkins: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    # Knowledge dual-track perception-gap check-ins (ADR-030), keyed by Ku uid.
    # The Knowledge dimension is per-(user, Ku): "how well I've mastered this Ku"
    # (MasteryLevel) vs the system-measured substance score. A Ku is SHARED/public
    # curriculum (not user-owned), so a mastery check-in can't live on the :Ku node
    # without colliding across users — it lives here on the :User node, keyed by the
    # Ku uid. A separate field (not a key inside dual_track_checkins) keeps the three
    # fixed DualTrackDimension values distinct from the open-ended per-Ku keys.
    # Each value is an append-only log of snapshots, capped at
    # DualTrackCheckin.HISTORY_LIMIT. Round-trips as a JSON property via neo4j_mapper.
    # Written by UserService.append_knowledge_checkin; read by the Ku detail page and
    # UserContextIntelligence.get_cross_domain_perception_analysis.
    knowledge_checkins: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def is_entity_active(self, entity_uid: EntityUID) -> bool:
        """Check if an entity is in the active set"""
        return entity_uid in self.active_entity_uids

    def is_entity_archived(self, entity_uid: EntityUID) -> bool:
        """Check if an entity is archived"""
        return entity_uid in self.archived_entity_uids

    def get_pinned_entities(self) -> list[str]:
        """
        Get ordered list of pinned entities.

        GRAPH-NATIVE PLACEHOLDER: always returns empty — pins live on the
        ``PINNED`` edge, whose ``order`` property carries the ordering, so the
        model cannot answer this without the graph.

        Service: UserRelationshipBackend.get_pinned_entities(user_uid), which
        scopes the read to one user. Do not hand-write the traversal at a call
        site: an unscoped version returns every user's pins.
        """
        return []  # Placeholder - use service layer

    def has_capacity(self) -> bool:
        """Check if user has capacity for more active items"""
        # Simple heuristic: limit active items based on available time
        max_active = self.preferences.available_minutes_daily // 10  # 10 min per item average
        return len(self.active_entity_uids) < max_active

    def get_energy_at_time(self, time_of_day: TimeOfDay) -> EnergyLevel:
        """Get user's energy level at a specific time"""
        return self.preferences.energy_pattern.get(time_of_day, EnergyLevel.MEDIUM)

    # ==========================================================================
    # ROLE-BASED ACCESS CONTROL
    # ==========================================================================

    def has_permission(self, required_role: UserRole) -> bool:
        """
        Check if user has at least the permissions of required_role.

        Uses hierarchy-aware comparison:
            REGISTERED < MEMBER < TEACHER < ADMIN

        Args:
            required_role: Minimum required role

        Returns:
            True if user's role meets or exceeds required_role
        """
        return self.role.has_permission(required_role)

    def can_create_curriculum(self) -> bool:
        """
        Check if user can create curriculum content (KU, LP, MOC).

        Requires TEACHER role or higher.
        """
        return self.role.can_create_curriculum()

    def can_manage_users(self) -> bool:
        """
        Check if user can manage other users (list, change roles, deactivate).

        Requires ADMIN role.
        """
        return self.role.can_manage_users()

    def is_subscriber(self) -> bool:
        """
        Check if user has paid subscription (MEMBER or higher).

        REGISTERED users are in free trial with limits.
        """
        return self.role.is_subscriber()

    def is_trial(self) -> bool:
        """
        Check if user is in free trial (REGISTERED role).
        """
        return self.role.is_trial()

    # ==========================================================================
    # GRAPH INTELLIGENCE (Intent Suggestion)
    # ==========================================================================

    def get_user_query_intent(self) -> QueryIntent:
        """
        Get suggested QueryIntent based on user preferences and state.

        Business rules:
        - Users with active learning paths → EXPLORATORY (discover content)
        - Users with many active entities → HIERARCHICAL (organize activities)
        - Users with high energy → PRACTICE (engage with content)
        - Users with specific interests → SPECIFIC (targeted content)
        - Default → RELATIONSHIP (explore connections)

        Returns:
            Recommended QueryIntent for this user's current context
        """
        # Check learning focus
        if len(self.interests) > 3 and self.preferences.learning_level in [
            LearningLevel.BEGINNER,
            LearningLevel.INTERMEDIATE,
        ]:
            return QueryIntent.EXPLORATORY

        # Check activity organization needs
        if len(self.active_entity_uids) > 10:
            return QueryIntent.HIERARCHICAL

        # Check energy and engagement
        current_time = TimeOfDay.ANYTIME  # Would be determined by current time
        if self.get_energy_at_time(current_time) == EnergyLevel.HIGH:
            return QueryIntent.PRACTICE

        # Check for specific interests
        # GRAPH-NATIVE: current_goals field removed - would query via service layer
        # if has_active_goals: # Would use UserRelationshipBackend.has_active_goals(user_uid)
        # return QueryIntent.SPECIFIC

        # Default to relationship exploration
        return QueryIntent.RELATIONSHIP


# ============================================================================
# USER CONTEXT FOR SERVICES
# ============================================================================


@dataclass(frozen=True, kw_only=True)
class UserServiceContext:
    """
    Lightweight context for service operations.

    This replaces the complex UserContext with a simpler structure that
    services can use without loading the full user model.
    """

    user_uid: UserUID
    username: str
    learning_level: LearningLevel

    # Current focus
    active_entity_uids: set[str]
    current_goal_uids: list[str]

    # Preferences relevant to services
    preferred_time: TimeOfDay
    available_minutes: int
    interests: list[str]

    # Session info
    session_id: str | None = None
    session_start: datetime | None = None

    @classmethod
    def from_user(
        cls, user: User, session_id: str | None = None, current_goal_uids: list[str] | None = None
    ) -> "UserServiceContext":
        """
        Create service context from user model.

        GRAPH-NATIVE: current_goal_uids must be provided from service layer query.
        Use UserRelationshipBackend.get_current_goals(user_uid) to populate.
        """
        return cls(
            user_uid=UserUID(user.uid),
            username=user.title,  # Username stored in title field
            learning_level=user.preferences.learning_level,
            active_entity_uids=user.active_entity_uids,
            current_goal_uids=current_goal_uids or [],  # Populated from service layer
            preferred_time=user.preferences.preferred_time_of_day,
            available_minutes=user.preferences.available_minutes_daily,
            interests=user.interests,
            session_id=session_id,
            session_start=datetime.now() if session_id else None,
        )


# ============================================================================
# USER STATISTICS (computed, not stored)
# ============================================================================


@dataclass
class UserStatistics:
    """
    Computed statistics about a user.

    These are calculated from user activity data, not stored in the user model.
    """

    user_uid: UserUID
    computed_at: datetime = field(default_factory=datetime.now)

    # Activity counts
    total_tasks: int = 0
    completed_tasks: int = 0
    total_habits: int = 0
    active_habits: int = 0
    total_learning_sessions: int = 0
    completed_learning: int = 0

    # Progress metrics
    overall_completion_rate: float = 0.0  # Percentage
    average_task_duration_minutes: float = 0.0
    total_time_spent_hours: float = 0.0

    # Streak metrics
    current_streak_days: int = 0
    longest_streak_days: int = 0
    consistency_score: float = 0.0  # 0-100

    # Learning metrics
    topics_mastered: int = 0
    average_mastery_level: float = 0.0
    learning_velocity: float = 1.0  # Relative to average

    # Time patterns
    most_active_time: TimeOfDay | None = None
    most_productive_day: str | None = None  # Day of week

    @classmethod
    def compute_from_progress(
        cls, user_uid: UserUID, progress_records: list[Any]
    ) -> "UserStatistics":
        """
        Compute statistics from progress records.

        This would be implemented by a service that has access to
        all progress records for the user.
        """
        stats = cls(user_uid=user_uid)

        if not progress_records:
            return stats

        # Count by type
        from core.models.enums import ActivityType, EntityStatus

        for progress in progress_records:
            if progress.entity_type == ActivityType.TASK:
                stats.total_tasks += 1
                if progress.metrics.is_complete():
                    stats.completed_tasks += 1
            elif progress.entity_type == ActivityType.HABIT:
                stats.total_habits += 1
                if progress.status == EntityStatus.ACTIVE:
                    stats.active_habits += 1
            elif progress.entity_type == ActivityType.LEARNING:
                stats.total_learning_sessions += 1
                if progress.metrics.is_complete():
                    stats.completed_learning += 1

            # Accumulate time
            stats.total_time_spent_hours += progress.metrics.time_spent_minutes / 60.0

            # Track streaks
            if progress.streaks:
                stats.current_streak_days = max(
                    stats.current_streak_days, progress.streaks.current_streak
                )
                stats.longest_streak_days = max(
                    stats.longest_streak_days, progress.streaks.longest_streak
                )

        # Calculate rates
        total_items = stats.total_tasks + stats.total_learning_sessions
        completed_items = stats.completed_tasks + stats.completed_learning
        if total_items > 0:
            stats.overall_completion_rate = (completed_items / total_items) * 100

        return stats


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================


def create_user(
    username: str,
    email: str,
    display_name: str | None = None,
    learning_level: LearningLevel = LearningLevel.INTERMEDIATE,
    role: UserRole = UserRole.REGISTERED,
    **kwargs: Any,
) -> User:
    """
    Create a new user with defaults.

    Uses username as the UID for human-readable identifiers.
    Example: username 'mfan0110' becomes UID 'user_mfan0110'

    New users default to REGISTERED (free trial) role.

    Args:
        username: Unique username
        email: User email address
        display_name: Display name (defaults to username)
        learning_level: Initial learning level
        role: User role (defaults to REGISTERED for new users)
        **kwargs: Additional User fields (password_hash, interests, is_verified, is_premium, settings, etc.)

    Returns:
        New User instance
    """
    return User(
        uid=f"user_{username}",  # Use username as UID for human-readable identifiers
        title=username,  # Username stored as title (from BaseEntity)
        description=f"User account for {display_name or username}",
        email=email,
        display_name=display_name or username,
        preferences=UserPreferences(learning_level=learning_level),
        role=role,
        **kwargs,  # Pass through additional fields (password_hash, is_verified, etc.)
    )


def create_guest_user(session_id: str) -> User:
    """Create a temporary guest user"""
    return User(
        uid=f"guest_{session_id}",
        title=f"guest_{session_id[:8]}",  # Username as title
        description="Temporary guest user account",
        email="guest@example.com",
        display_name="Guest User",
        is_verified=False,
    )
