"""Study workspace sidebar configuration.

5-item sidebar for the student workspace sub-pages:
Submit -> My Submissions -> Exercise Reports -> Activity Reports -> Generate Reports

Exercises moved to Curriculum sidebar. All sub-pages are top-level routes.
Sidebar appears on sub-pages — NOT on /study landing.
"""

from ui.patterns.sidebar import SidebarItem

STUDY_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Submit", "/submit", "submit", icon="📤"),
    SidebarItem("My Submissions", "/submissions", "submissions", icon="📝"),
    SidebarItem("Exercise Reports", "/exercise-reports", "exercise-reports", icon="📋"),
    SidebarItem("Activity Reports", "/activity-reports", "activity-reports", icon="📊"),
    SidebarItem("Generate Reports", "/generate-reports", "generate-reports", icon="⚡"),
]
