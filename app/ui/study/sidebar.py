"""Study workspace sidebar configuration.

6-item sidebar for the student workspace sub-pages:
Exercises -> Submit -> My Submissions -> Exercise Reports -> Activity Reports -> Generate Reports

All sub-pages are top-level routes. Sidebar appears on sub-pages — NOT on /study landing.
"""

from ui.patterns.sidebar import SidebarItem

STUDY_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Exercises", "/exercises", "exercises", icon="🏋️"),
    SidebarItem("Submit", "/submit", "submit", icon="📤"),
    SidebarItem("My Submissions", "/submissions", "submissions", icon="📝"),
    SidebarItem("Exercise Reports", "/exercise-reports", "exercise-reports", icon="📋"),
    SidebarItem("Activity Reports", "/activity-reports", "activity-reports", icon="📊"),
    SidebarItem("Generate Reports", "/generate-reports", "generate-reports", icon="⚡"),
]
