"""Profile UI components.

This module provides the profile page layout and domain-specific views
following the UserContext-driven architecture pattern.

Components:
- create_profile_page: Modern BasePage-based profile layout
- Domain views: TasksDomainView, HabitsDomainView, etc.
- Badges: StatusBadge, CountBadge for sidebar indicators
"""

from ui.profile.badges import CountBadge, DomainSidebarItem, StatusBadge
from ui.profile.domain_views import (
    ChoicesDomainView,
    DomainSummaryCard,
    EventsDomainView,
    GoalsDomainView,
    HabitsDomainView,
    OverviewView,
    PrinciplesDomainView,
    TasksDomainView,
)
from ui.profile.layout import (
    build_profile_sidebar,
    create_profile_page,
    ProfileDomainItem,
)

__all__ = [
    # Layout
    "build_profile_sidebar",
    "create_profile_page",
    "ProfileDomainItem",
    # Domain views
    "ChoicesDomainView",
    "DomainSummaryCard",
    "EventsDomainView",
    "GoalsDomainView",
    "HabitsDomainView",
    "OverviewView",
    "PrinciplesDomainView",
    "TasksDomainView",
    # Badges
    "CountBadge",
    "DomainSidebarItem",
    "StatusBadge",
]
