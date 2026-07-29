"""
User Enums - Role, Health, and Account Status Enums
====================================================

User-specific enumerations for role hierarchy, context health scoring,
account management, and journal workflow tier.

Four-tier role hierarchy (lowest to highest):
    REGISTERED < MEMBER < TEACHER < ADMIN

Each role inherits permissions from lower roles.

Design Principles:
- Roles stored in Neo4j User.role field
- Role checking uses helper methods for hierarchy-aware comparisons
- New users default to REGISTERED
- Payment upgrades REGISTERED -> MEMBER
- Only ADMIN can promote to TEACHER or ADMIN

Two-state account lifecycle:
    ACTIVE < DELETED

Soft-delete marks the User node with status=DELETED, scrubs PII, and keeps the
node + OWNS-linked entities (UserEntry, Task, Goal, ...) intact so teachers can
still render the owner's historical submissions. Hard-delete (admin-only, GDPR
right-to-erasure) deletes the User + cascade over every OWNS edge.

Journal tier — orthogonal to UserRole:
    STANDARD (default) — continuous single-response workflow
    FOUNDER            — full DNWF three-stage workflow (linguistic76 pilot)
"""

from enum import StrEnum


class UserRole(StrEnum):
    """
    Four-tier user role hierarchy for SKUEL.

    Hierarchy (lowest to highest):
        REGISTERED < MEMBER < TEACHER < ADMIN

    Role descriptions:
    - REGISTERED: Free trial with limited access (5 KUs, 1 LP, 10 tasks, etc.)
    - MEMBER: Paid subscription with unlimited content consumption
    - TEACHER: Member + can create/edit curriculum content (KU, LP, MOC)
    - ADMIN: Teacher + can manage users and assign roles
    """

    REGISTERED = "registered"  # Free trial, limited access
    MEMBER = "member"  # Paid, full consumption
    TEACHER = "teacher"  # Member + content creation
    ADMIN = "admin"  # Teacher + user management

    def get_badge_class(self) -> str:
        """Get Tailwind badge classes for role display."""
        return {
            UserRole.ADMIN: "bg-red-100 text-red-800 border-red-200",
            UserRole.TEACHER: "bg-yellow-100 text-yellow-800 border-yellow-200",
            UserRole.MEMBER: "bg-green-100 text-green-800 border-green-200",
            UserRole.REGISTERED: "bg-blue-100 text-blue-800 border-blue-200",
        }.get(self, "bg-muted text-muted-foreground border-border")

    @property
    def _hierarchy_level(self) -> int:
        """Get numeric hierarchy level for comparison."""
        hierarchy = {
            UserRole.REGISTERED: 0,
            UserRole.MEMBER: 1,
            UserRole.TEACHER: 2,
            UserRole.ADMIN: 3,
        }
        return hierarchy[self]

    def has_permission(self, required_role: "UserRole") -> bool:
        """
        Check if this role has at least the permissions of required_role.

        Hierarchy: REGISTERED < MEMBER < TEACHER < ADMIN

        Example:
            UserRole.ADMIN.has_permission(UserRole.TEACHER)  # True
            UserRole.MEMBER.has_permission(UserRole.TEACHER) # False
        """
        return self._hierarchy_level >= required_role._hierarchy_level

    def can_create_curriculum(self) -> bool:
        """Check if role can create KU, LP, MOC content."""
        return self.has_permission(UserRole.TEACHER)

    def can_manage_users(self) -> bool:
        """Check if role can list users, change roles, deactivate accounts."""
        return self == UserRole.ADMIN

    def is_subscriber(self) -> bool:
        """Check if role has paid subscription (Member or higher)."""
        return self.has_permission(UserRole.MEMBER)

    def is_trial(self) -> bool:
        """Check if role is in free trial (REGISTERED only)."""
        return self == UserRole.REGISTERED

    @classmethod
    def from_string(cls, value: str | None) -> "UserRole | None":
        """
        Parse string to UserRole, handling case-insensitivity.

        Args:
            value: Role string (e.g., "admin", "ADMIN", "Admin")

        Returns:
            UserRole if valid, None otherwise
        """
        if value is None:
            return None
        try:
            return cls(value.lower().strip())
        except ValueError:
            return None

    @classmethod
    def default(cls) -> "UserRole":
        """Get the default role for new users."""
        return cls.REGISTERED


class UserStatus(StrEnum):
    """
    Account lifecycle state for User nodes.

    Two states:
    - ACTIVE: normal account. Can authenticate; owned entities are mutable.
    - DELETED: soft-deleted. Blocks login, PII scrubbed, but the User node +
      every OWNS-linked entity are preserved so downstream views
      (teacher gradebook, analytics, audit) still resolve.

    Paired with the legacy ``User.is_active`` boolean, which
    ``authenticate()`` still checks. Soft-delete flips both
    (``status=DELETED``, ``is_active=False``) so the existing auth guard
    continues to reject the user without a migration.
    """

    ACTIVE = "active"
    DELETED = "deleted"

    def is_deleted(self) -> bool:
        return self is UserStatus.DELETED


class ContextHealthScore(StrEnum):
    """
    User context health scoring levels.

    Matches FinancialHealthTier pattern for consistency across domains.
    Used to assess overall user context system health based on metrics
    and alerts.

    Hierarchy (lowest to highest):
        POOR < FAIR < GOOD < EXCELLENT
    """

    POOR = "poor"
    FAIR = "fair"
    GOOD = "good"
    EXCELLENT = "excellent"

    def get_numeric(self) -> float:
        """
        Convert to numeric value for scoring and comparison.

        Returns:
            Float between 0.0 and 1.0
        """
        mapping = {
            ContextHealthScore.POOR: 0.25,
            ContextHealthScore.FAIR: 0.50,
            ContextHealthScore.GOOD: 0.75,
            ContextHealthScore.EXCELLENT: 1.0,
        }
        return mapping.get(self, 0.5)

    def get_text_class(self) -> str:
        """Get Tailwind CSS text color class for health score."""
        colors = {
            ContextHealthScore.POOR: "text-red-600",
            ContextHealthScore.FAIR: "text-yellow-600",
            ContextHealthScore.GOOD: "text-blue-600",
            ContextHealthScore.EXCELLENT: "text-green-600",
        }
        return colors.get(self, "text-gray-600")

    def get_icon(self) -> str:
        """
        Get emoji icon for health score.

        Returns:
            Emoji representing health level
        """
        icons = {
            ContextHealthScore.POOR: "🔴",
            ContextHealthScore.FAIR: "🟡",
            ContextHealthScore.GOOD: "🔵",
            ContextHealthScore.EXCELLENT: "🟢",
        }
        return icons.get(self, "⚪")


class JournalTier(StrEnum):
    """Journal workflow tier — orthogonal to UserRole.

    STANDARD: Continuous single-response workflow for all users. AI reads the
              journal entry, connects it to active goals/tasks/habits, and
              returns a motivating response.
    FOUNDER:  Full DNWF three-stage workflow (Scribe → Thought Partner →
              What Is Related), each stage gated by user review. Reserved for
              the linguistic76 pilot account. Paves the path for per-user
              journal configuration.

    See: /docs/decisions/ (ADR forthcoming), project_journals_domain memory.
    """

    STANDARD = "standard"
    FOUNDER = "founder"

    @classmethod
    def default(cls) -> "JournalTier":
        return cls.STANDARD

    def is_founder(self) -> bool:
        return self is JournalTier.FOUNDER


class JournalMode(StrEnum):
    """Function of the journal companion's response — maps to DNWF stage.

    SCRIBE:          Stage 1 — faithful structural record of the raw entry.
    THOUGHT_PARTNER: Stage 2 — patterns, tensions, interpretive challenge.
    WHAT_IS_RELATED: Stage 3 — connections to knowledge, curriculum, and graph.
    """

    SCRIBE = "scribe"
    THOUGHT_PARTNER = "thought_partner"
    WHAT_IS_RELATED = "what_is_related"

    @classmethod
    def default(cls) -> "JournalMode":
        return cls.THOUGHT_PARTNER

    @classmethod
    def from_string(cls, value: str | None) -> "JournalMode":
        if not value:
            return cls.default()
        normalized = value.lower().strip().replace(" ", "_").replace("-", "_")
        try:
            return cls(normalized)
        except ValueError:
            return cls.default()

    def display_label(self) -> str:
        return {
            JournalMode.SCRIBE: "Scribe",
            JournalMode.THOUGHT_PARTNER: "Thought Partner",
            JournalMode.WHAT_IS_RELATED: "What Is Related",
        }[self]
