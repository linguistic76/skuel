"""Activities UI components — landing page and sidebar layout."""

from ui.activities.landing import ActivitiesLandingView
from ui.activities.layout import create_activities_page
from ui.activities.sidebar import ACTIVITY_SIDEBAR_ITEMS

__all__ = [
    "ACTIVITY_SIDEBAR_ITEMS",
    "ActivitiesLandingView",
    "create_activities_page",
]
