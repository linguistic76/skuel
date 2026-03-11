"""Activity sidebar configuration.

Sidebar items for individual activity domain pages (/activities/tasks, etc.).
NOT shown on the /activities landing page.
"""

from ui.patterns.sidebar import SidebarItem

ACTIVITY_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Tasks", "/activities/tasks", "tasks", icon="✅"),
    SidebarItem("Events", "/activities/events", "events", icon="📅"),
    SidebarItem("Goals", "/activities/goals", "goals", icon="🎯"),
    SidebarItem("Habits", "/activities/habits", "habits", icon="🔄"),
    SidebarItem("Principles", "/activities/principles", "principles", icon="⚖️"),
    SidebarItem("Choices", "/activities/choices", "choices", icon="🔀"),
    SidebarItem("Journals", "/activities/journals", "journals", icon="📓"),
    SidebarItem("Reports", "/activities/reports", "reports", icon="📊"),
]
