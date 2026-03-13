"""Activity sidebar configuration.

Sidebar items for activity domain pages (/{domain}).
Also shown on /journals and /submissions/reports.
"""

from ui.patterns.sidebar import SidebarItem

ACTIVITY_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Tasks", "/tasks", "tasks", icon="✅"),
    SidebarItem("Events", "/events", "events", icon="📅"),
    SidebarItem("Goals", "/goals", "goals", icon="🎯"),
    SidebarItem("Habits", "/habits", "habits", icon="🔄"),
    SidebarItem("Principles", "/principles", "principles", icon="⚖️"),
    SidebarItem("Choices", "/choices", "choices", icon="🔀"),
    SidebarItem("Journals", "/journals", "journals", icon="📓"),
    SidebarItem("Reports", "/submissions/reports", "reports", icon="📊"),
]
