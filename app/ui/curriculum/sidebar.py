"""Curriculum sidebar configuration.

Sidebar items for curriculum domain pages (/lessons, /learning-steps, /learning-paths, /exercises).
"""

from ui.patterns.sidebar import SidebarItem

CURRICULUM_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Lessons", "/lessons", "lessons", icon="📖"),
    SidebarItem("Learning Steps", "/learning-steps", "learning-steps", icon="🧩"),
    SidebarItem("Learning Paths", "/learning-paths", "learning-paths", icon="🗺️"),
    SidebarItem("Exercises", "/exercises", "exercises", icon="🏋️"),
]
