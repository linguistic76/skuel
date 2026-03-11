"""Learning sidebar configuration.

Reflects the learning loop workflow:
Study (content) → Practice (the loop) → Pathways (structured progression)

Sidebar appears on /learn/study, /learn/practice, /learn/pathways — NOT on /learn landing.
"""

from ui.patterns.sidebar import SidebarItem

LEARN_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Study", "/learn/study", "study", icon="📖"),
    SidebarItem("Practice", "/learn/practice", "practice", icon="✏️"),
    SidebarItem("Pathways", "/learn/pathways", "pathways", icon="🗺️"),
]
