"""
Entity Enums - Entity Type Identification and Domain Categorization
====================================================================

Core enums for entity type discrimination and domain classification.
"""

from enum import Enum


class Domain(str, Enum):
    """
    Core domains in the SKUEL system.
    Each domain represents a distinct area of functionality.
    """

    # Core system domains
    KNOWLEDGE = "knowledge"
    LEARNING = "learning"
    TASKS = "tasks"
    HABITS = "habits"
    FINANCE = "finance"
    EVENTS = "events"
    REPORTS = "reports"
    JOURNALS = "journals"  # Alias for REPORTS (migration aid)
    PRINCIPLES = "principles"
    GOALS = "goals"
    CHOICES = "choices"
    SYSTEM = "system"
    ALL = "all"  # Special case for cross-domain operations

    # Knowledge categorization domains
    TECH = "tech"
    BUSINESS = "business"
    PERSONAL = "personal"
    HEALTH = "health"
    EDUCATION = "education"
    CREATIVE = "creative"
    RESEARCH = "research"
    SOCIAL = "social"
    META = "meta"
    CROSS_DOMAIN = "cross_domain"

    def get_search_synonyms(self) -> tuple[str, ...]:
        """Return search terms that match this domain"""
        synonyms = {
            Domain.KNOWLEDGE: ("knowledge", "learn", "study", "education", "info", "ku"),
            Domain.LEARNING: ("learning", "course", "path", "curriculum", "lp", "ls"),
            Domain.TASKS: ("task", "todo", "work", "action", "assignment"),
            Domain.HABITS: ("habit", "routine", "practice", "behavior", "pattern"),
            Domain.FINANCE: ("finance", "money", "budget", "expense", "income"),
            Domain.EVENTS: ("event", "calendar", "meeting", "appointment", "schedule"),
            Domain.REPORTS: ("report", "journal", "entry", "log", "diary", "reflection"),
            Domain.PRINCIPLES: ("principle", "value", "belief", "philosophy", "guideline"),
            Domain.GOALS: ("goal", "objective", "target", "aim", "milestone"),
            Domain.CHOICES: ("choice", "decision", "option", "selection"),
            Domain.TECH: ("tech", "technology", "programming", "software", "code"),
            Domain.BUSINESS: ("business", "work", "professional", "career"),
            Domain.PERSONAL: ("personal", "self", "life", "individual"),
            Domain.HEALTH: ("health", "fitness", "wellness", "medical"),
            Domain.EDUCATION: ("education", "academic", "school", "university"),
            Domain.CREATIVE: ("creative", "art", "design", "music"),
            Domain.RESEARCH: ("research", "study", "investigation", "analysis"),
            Domain.SOCIAL: ("social", "people", "relationship", "community"),
        }
        return synonyms.get(self, (self.value,))

    @classmethod
    def from_search_text(cls, text: str) -> list["Domain"]:
        """Find matching domains from search text"""
        text_lower = text.lower()
        return [
            domain
            for domain in cls
            if any(synonym in text_lower for synonym in domain.get_search_synonyms())
        ]


class EntityType(str, Enum):
    """
    Entity types that can be created via DSL @context() tag.

    This enum provides type-safe context parsing for SKUEL's Activity DSL.
    When users write `@context(task)` or `@context(habit,learning)`, the parser
    converts these strings to EntityType values, enabling compile-time verification.

    Maps directly to SKUEL's 13-domain + 5-system architecture:

    Activity Domains (7) - What I DO:
        TASK, HABIT, GOAL, EVENT, PRINCIPLE, CHOICE, FINANCE

    Curriculum Domains (3) - What I LEARN:
        KU (Knowledge Unit), LS (Learning Step), LP (Learning Path)

    Content/Organization Domains (2) - How I ORGANIZE:
        REPORT (includes journals), MOC (Map of Content)

    LifePath (1) - The Destination:
        LIFEPATH

    Cross-Cutting Systems (not domains, but may appear in search):
        CALENDAR
    """

    # Activity Domains (7) - What I DO
    TASK = "task"
    HABIT = "habit"
    GOAL = "goal"
    EVENT = "event"
    PRINCIPLE = "principle"
    CHOICE = "choice"
    FINANCE = "finance"

    # Curriculum Domains (3) - What I LEARN
    KU = "ku"
    KNOWLEDGE = "knowledge"  # Alias for KU
    LS = "ls"
    LEARNINGSTEP = "learningstep"  # Alias for LS
    LP = "lp"
    LEARNINGPATH = "learningpath"  # Alias for LP
    LEARNING = "learning"  # General learning context

    # Content/Organization Domains (2) - How I ORGANIZE
    REPORT = "report"
    JOURNAL = "journal"  # Alias for REPORT (migration aid — journal is a ReportType)
    MOC = "moc"  # Map of Content - non-linear knowledge navigation

    # Organizational (1) - How I ORGANIZE people
    GROUP = "group"  # Teacher-student class management (ADR-040)

    # The Destination (1) - Where I'm GOING
    LIFEPATH = "lifepath"
    LIFE_PATH = "life_path"  # Alias for LIFEPATH

    # Cross-Cutting Systems (not domains, but may appear in search)
    CALENDAR = "calendar"

    def is_lifepath(self) -> bool:
        """Check if this is the LifePath destination entity type."""
        return self in {EntityType.LIFEPATH, EntityType.LIFE_PATH}

    def get_canonical(self) -> "EntityType":
        """
        Get the canonical (non-alias) form of this entity type.

        Aliases are normalized to their canonical form:
            KNOWLEDGE -> KU, LEARNINGSTEP -> LS, LEARNINGPATH -> LP,
            LIFE_PATH -> LIFEPATH, JOURNAL -> REPORT
        """
        alias_map = {
            EntityType.KNOWLEDGE: EntityType.KU,
            EntityType.LEARNINGSTEP: EntityType.LS,
            EntityType.LEARNINGPATH: EntityType.LP,
            EntityType.LIFE_PATH: EntityType.LIFEPATH,
            EntityType.JOURNAL: EntityType.REPORT,
        }
        return alias_map.get(self, self)

    @classmethod
    def from_string(cls, value: str) -> "EntityType | None":
        """
        Parse a string to EntityType, handling case-insensitivity.

        This is the primary entry point for DSL parsing.
        """
        value = value.lower().strip()
        try:
            return cls(value)
        except ValueError:
            return None


class AnalyticsDomain(str, Enum):
    """
    Core system domains that can generate statistical analytics.

    Analytics provide quantitative assessment of user data within each domain.
    """

    TASKS = "tasks"
    HABITS = "habits"
    GOALS = "goals"
    EVENTS = "events"
    FINANCE = "finance"
    CHOICES = "choices"

    def get_metrics(self) -> list[str]:
        """Get available metrics for this analytics domain"""
        metrics = {
            AnalyticsDomain.TASKS: [
                "completion_rate",
                "total_count",
                "completed_count",
                "in_progress_count",
                "pending_count",
                "overdue_count",
                "priority_distribution",
                "avg_completion_time_days",
            ],
            AnalyticsDomain.HABITS: [
                "total_active",
                "completion_rate",
                "current_streaks",
                "best_streaks",
                "consistency_rate",
                "completion_by_day_of_week",
            ],
            AnalyticsDomain.GOALS: [
                "total_active",
                "total_completed",
                "on_track_count",
                "at_risk_count",
                "avg_progress_percentage",
                "completion_rate",
            ],
            AnalyticsDomain.EVENTS: [
                "total_count",
                "upcoming_count",
                "completed_count",
                "cancelled_count",
                "total_hours_scheduled",
                "events_by_type",
            ],
            AnalyticsDomain.FINANCE: [
                "total_expenses",
                "total_income",
                "net_balance",
                "expenses_by_category",
                "budget_adherence",
                "avg_daily_expense",
            ],
            AnalyticsDomain.CHOICES: [
                "total_choices",
                "choices_by_domain",
                "decision_quality_avg",
                "choices_reviewed_count",
            ],
        }
        return metrics.get(self, [])


class ContentScope(str, Enum):
    """
    Defines content ownership/sharing model for domain entities.

    This enum makes the critical security contract explicit in code:
    - USER_OWNED: User-specific content with ownership verification
    - SHARED: Public/shared content accessible to all users

    This is orthogonal to role-based access control (require_role).
    When require_role is set, ContentScope is ignored as role controls all access.

    Usage in route factories:
        CRUDRouteFactory(
            service=tasks_service,
            scope=ContentScope.USER_OWNED,  # Tasks are user-owned
        )

        CRUDRouteFactory(
            service=ku_service,
            scope=ContentScope.SHARED,  # Knowledge Units are shared
        )

    IMPORTANT: SHARED content means user_uid=None in list() requests for
    unauthenticated users. Services must handle this correctly:
    - user_uid=None → return shared/public content
    - user_uid=None does NOT mean "return everything"

    Create operations ALWAYS require authentication regardless of scope
    (shared content can be read publicly, but only authenticated users
    can create new content).
    """

    USER_OWNED = "user_owned"  # User-specific with ownership checks
    SHARED = "shared"  # Public/shared, no ownership required


class Context(str, Enum):
    """Context where activity can be performed"""

    HOME = "home"
    WORK = "work"
    COMPUTER = "computer"
    PHONE = "phone"
    ERRANDS = "errands"
    ANYWHERE = "anywhere"
