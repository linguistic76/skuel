"""
Components Package
==================

UI components for SKUEL application.

Architecture:
    Components are extracted from route files for separation of concerns.
    Each component module contains UI building functions that are imported
    by their corresponding route files.

    Pattern:
        Route Files (HTTP handling only)
            ↓
        /components/*.py (UI components)
            ↓
        /static/css/*.css (styles)
        /static/js/*.js (client-side logic)

Modules:
    - auth_components: Authentication forms (login, register, password reset)
    - calendar_components: Calendar UI (month, week, day views)
    - drawer_layout: Reusable DaisyUI drawer sidebar component
    - form_generator: Dynamic form generation from Pydantic models
    - search_components: Search page with filter sidebar
    - timeline_components: Markwhen timeline viewer

Design Philosophy:
    "Users can handle complexity, but they need visual calm to process it."

    We leverage pre-built DaisyUI components where possible to:
    - Reduce custom CSS/JS maintenance burden
    - Ensure consistent responsive behavior
    - Benefit from framework updates and accessibility improvements
"""

__version__ = "2.0"

# Calendar components
from components.calendar_components import (
    calendar_item_to_dict,
    create_day_timeline,
    create_month_grid,
    create_quick_add_button,
    create_quick_add_modal,
    create_view_switcher,
    create_week_grid,
    error_response,
)

# Drawer layout (DaisyUI-based sidebar)
from components.drawer_layout import (
    DrawerLayout,
    MenuItem,
    create_drawer_layout,
)

# Timeline components
from components.timeline_components import (
    render_timeline_error,
    render_timeline_viewer_page,
)

__all__ = [
    # Drawer layout
    "DrawerLayout",
    "MenuItem",
    "calendar_item_to_dict",
    "create_day_timeline",
    "create_drawer_layout",
    # Calendar
    "create_month_grid",
    "create_quick_add_button",
    "create_quick_add_modal",
    "create_view_switcher",
    "create_week_grid",
    "error_response",
    "render_timeline_error",
    # Timeline
    "render_timeline_viewer_page",
]
