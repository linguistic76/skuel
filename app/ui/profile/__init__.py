"""Profile UI components.

This module provides the profile page layout and domain-specific views
following the UserContext-driven architecture pattern.

Components:
- ProfileLayout: Sidebar layout similar to DocsLayout
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
    ProfileDomainItem,
    ProfileLayout,
    create_profile_page,
)

__all__ = [
    "ChoicesDomainView",
    "CountBadge",
    "DomainSidebarItem",
    # Domain views
    "DomainSummaryCard",
    "EventsDomainView",
    "GoalsDomainView",
    "HabitsDomainView",
    "OverviewView",
    "PrinciplesDomainView",
    "ProfileDomainItem",
    # Layout
    "ProfileLayout",
    # Badges
    "StatusBadge",
    "TasksDomainView",
    "create_profile_page",
]
