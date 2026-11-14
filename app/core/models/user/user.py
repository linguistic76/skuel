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
- External: user_request.py (Pydantic validation)
- Transfer: user_dto.py (mutable DTOs)
- Core: user.py (this file, frozen domain model)
"""

__version__ = "2.1"


import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final
from zoneinfo import ZoneInfo

from core.models.enums import EnergyLevel, JournalTier, LearningLevel, TimeOfDay, UserRole
from core.models.query_types import QueryIntent
from core.models.type_hints import EntityUID, UserUID
from core.utils.uid_generator import UIDGenerator
from core.utils.zone_context import zone_for

#: The display themes a user may choose (``UserPreferences.theme``).
THEMES: tuple[str, ...] = ("light", "dark")

#: The interface languages a user may choose (``UserPreferences.language``).
LANGUAGES: tuple[str, ...] = ("en", "es", "fr", "de")


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
    theme: str = "light"  # one of THEMES
    language: str = "en"  # one of LANGUAGES
    # The user's zone: an IANA name chosen in Settings, validated at the doors
    # (core/utils/zone_context.py). None — no choice — follows SKUEL_TIMEZONE.
    timezone: str | None = None

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
    uid: UserUID
    title: str  # We'll use title as username for consistency
    description: str = ""
    email: str = ""
    display_name: str = ""
    # Bcrypt password hash (graph-native authentication). repr=False: a bcrypt
    # digest is offline-crackable, so it is a credential, not an opaque id.
    password_hash: str = field(default="", repr=False)

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

    def zone(self) -> ZoneInfo:
        """The zone this user's calendar values belong to: their choice, else the app default."""
        return zone_for(self.preferences.timezone)

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

    def is_teacher(self) -> bool:
        """
        Check if user is a teacher: TEACHER role or higher.

        Curriculum is authored in the content vault (ADR-091 S8), so this
        grants no authoring; it sets the session's teacher flag.
        """
        return self.role.is_teacher()

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
        - More than three interests at a beginner or intermediate level →
          EXPLORATORY (discover content)
        - Users with many active entities → HIERARCHICAL (organize activities)
        - Users with high energy → PRACTICE (engage with content)
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

        # Default to relationship exploration
        return QueryIntent.RELATIONSHIP


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================


#: A username — the account's login handle and display name, never part of its
#: uid: 3-30 lowercase letters, digits, ``_`` and ``-``.
USERNAME: Final = re.compile(r"[a-z0-9_-]{3,30}")


def fold_username(raw: str) -> str:
    """``raw`` as a username is stored and compared: trimmed and lowercase.

    Folding first is what makes ``Mike`` and ``mike`` one name.
    """
    return raw.strip().lower()


def username_problem(username: str) -> str | None:
    """Why ``username`` (already folded) is not a username, or ``None``."""
    if USERNAME.fullmatch(username):
        return None
    return "A username is 3-30 characters: lowercase letters, digits, '_' and '-'"


#: The longest display name, in characters, at every door that takes one.
DISPLAY_NAME_MAX_LENGTH: Final = 100

#: Format characters a name may hold: the joiners that Persian spelling and
#: multi-part emoji are written with.
_NAME_JOINERS: Final = frozenset({"\u200c", "\u200d"})

#: Unicode general categories no display name holds: control, format, surrogate,
#: line separator, paragraph separator.
_REFUSED_CATEGORIES: Final = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})


def display_name_problem(name: str) -> str | None:
    """Why ``name`` (already trimmed) is not a display name, or ``None``.

    A display name is what other people read beside a user's work, and one line of
    the AI prompts: 1 to ``DISPLAY_NAME_MAX_LENGTH`` characters of any script,
    punctuation or emoji, on one line. Refused: a control character (newline and
    tab among them), a format character other than the two joiners (the direction
    overrides among them), a surrogate, and a line or paragraph separator. An
    unassigned code point passes, so an emoji newer than this Python's Unicode
    tables is a name. Names are not unique: the username is the identity.
    """
    if not name:
        return "A display name cannot be blank"
    if len(name) > DISPLAY_NAME_MAX_LENGTH:
        return f"A display name is at most {DISPLAY_NAME_MAX_LENGTH} characters"
    for char in name:
        if unicodedata.category(char) in _REFUSED_CATEGORIES and char not in _NAME_JOINERS:
            return "A display name is one line, with no control characters"
    return None


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

    The uid is generated — ``user_{16 hex}``, random — and the username is
    stored as ``title``, never in the uid. The caller folds and checks the
    username first (``fold_username``, ``username_problem``).

    New users default to REGISTERED (free trial) role.

    Args:
        username: Unique username, folded and checked
        email: User email address
        display_name: Display name (defaults to username)
        learning_level: Initial learning level
        role: User role (defaults to REGISTERED for new users)
        **kwargs: Additional User fields (password_hash, interests, is_verified, is_premium, settings, etc.)

    Returns:
        New User instance
    """
    return User(
        uid=UserUID(UIDGenerator.generate_random_uid("user")),
        title=username,  # Username stored as title (from BaseEntity)
        description=f"User account for {display_name or username}",
        email=email,
        display_name=display_name or username,
        preferences=UserPreferences(learning_level=learning_level),
        role=role,
        **kwargs,  # Pass through additional fields (password_hash, is_verified, etc.)
    )
