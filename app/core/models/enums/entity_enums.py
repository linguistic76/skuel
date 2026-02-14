"""
Entity Enums - Entity Type Identification and Domain Categorization
====================================================================

Core enums for entity type discrimination and domain classification.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from .ku_enums import KuType


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


class NonKuDomain(str, Enum):
    """
    Non-knowledge-unit domains outside the unified Ku model.

    These 4 domains exist in SKUEL but are NOT represented as :Ku nodes:
    - FINANCE: Admin-only bookkeeping (:Expense nodes)
    - GROUP: Teacher-student class management (:Group nodes, ADR-040)
    - CALENDAR: Aggregation meta-service (no dedicated nodes)
    - LEARNING: DSL context modifier (not a domain entity)
    """

    FINANCE = "finance"
    GROUP = "group"
    CALENDAR = "calendar"
    LEARNING = "learning"  # DSL context modifier

    @classmethod
    def from_string(cls, value: str) -> NonKuDomain | None:
        """Parse a string to NonKuDomain, case-insensitive."""
        normalized = value.strip().lower()
        try:
            return cls(normalized)
        except ValueError:
            return None


# Union type for any domain identifier in SKUEL.
# KuType covers all 14 Ku manifestations; NonKuDomain covers the 4 non-Ku domains.
DomainIdentifier = Union["KuType", NonKuDomain]


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
    - SHARED: Public reading, admin-only creation (curriculum domains)

    Combined with require_role=UserRole.ADMIN for write operations:
    - Read (get, list): Public, no authentication required
    - Write (create, update, delete): ADMIN role required

    Usage in route factories:
        CRUDRouteFactory(
            service=tasks_service,
            scope=ContentScope.USER_OWNED,  # Tasks are user-owned
        )

        CRUDRouteFactory(
            service=ku_service,
            scope=ContentScope.SHARED,       # Knowledge Units are shared
            require_role=UserRole.ADMIN,      # Admin-only writes
            user_service_getter=getter,
        )

    IMPORTANT: SHARED content means user_uid=None in list() requests for
    unauthenticated users. Services must handle this correctly:
    - user_uid=None → return shared/public content
    - user_uid=None does NOT mean "return everything"

    Access control summary:
    - Activity domains (USER_OWNED): Any user creates and owns their content
    - Curriculum domains (SHARED + ADMIN): Admin creates, everyone reads
    - Finance (ADMIN_ONLY via require_role): Admin creates and reads
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
