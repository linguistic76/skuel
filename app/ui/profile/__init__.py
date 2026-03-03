"""Profile UI components.

This module provides the profile page layout and domain-specific views
following the UserContext-driven architecture pattern.

Components:
- create_profile_page: Modern BasePage-based profile layout
- Domain views: TasksDomainView, HabitsDomainView, etc.
- Badges: StatusBadge, CountBadge for sidebar indicators
"""

from ui.profile.badges import CountBadge, DomainSidebarItem, StatusBadge
from ui.profile._shared import DomainSummaryCard
from ui.profile.activity_views import (
    ChoicesDomainView,
    EventsDomainView,
    GoalsDomainView,
    HabitsDomainView,
    PrinciplesDomainView,
    TasksDomainView,
)
from ui.profile.overview import OverviewView
from ui.profile.layout import (
    ProfileDomainItem,
    create_profile_page,
)

__all__ = [
    # Layout
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
