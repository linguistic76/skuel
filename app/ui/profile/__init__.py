"""Profile UI components.

This module provides the profile page layout and domain-specific views
following the UserContext-driven architecture pattern.

Components:
- create_profile_page: Modern BasePage-based profile layout
- Badges: StatusBadge, CountBadge for sidebar indicators
"""

from ui.profile._shared import DomainSummaryCard
from ui.profile.badges import CountBadge, DomainSidebarItem, StatusBadge
from ui.profile.layout import (
    ProfileDomainItem,
    create_profile_page,
)
from ui.profile.overview import OverviewView

__all__ = [
    # Layout
    "create_profile_page",
    "ProfileDomainItem",
    # Shared components
    "DomainSummaryCard",
    "OverviewView",
    # Badges
    "CountBadge",
    "DomainSidebarItem",
    "StatusBadge",
]
