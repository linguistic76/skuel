"""Profile UI components.

This module provides the profile hub page and supporting components
following the hub page (MOC) pattern.

See: /docs/design-principles/HUB_PAGES.md
"""

from ui.profile._shared import DomainSummaryCard
from ui.profile.badges import CountBadge, DomainSidebarItem, HealthIndicator
from ui.profile.hub import ProfileHubView

__all__ = [
    # Hub
    "ProfileHubView",
    # Shared components
    "DomainSummaryCard",
    # Badges
    "CountBadge",
    "DomainSidebarItem",
    "HealthIndicator",
]
