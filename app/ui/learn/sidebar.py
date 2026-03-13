"""Learning workspace sidebar configuration.

6-item sidebar for the student workspace sub-pages:
Exercises → Submit → My Submissions → Assessments → Activity Reports → Generate Reports

Sidebar appears on sub-pages — NOT on /learn landing.
"""

from ui.patterns.sidebar import SidebarItem

LEARN_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Exercises", "/ui/exercises", "exercises", icon="🏋️"),
    SidebarItem("Submit", "/learn/submit", "submit", icon="📤"),
    SidebarItem("My Submissions", "/learn/submissions", "submissions", icon="📝"),
    SidebarItem("Assessments", "/learn/assessments", "assessments", icon="📋"),
    SidebarItem("Activity Reports", "/learn/activity-reports", "activity-reports", icon="📊"),
    SidebarItem("Generate Reports", "/learn/generate-reports", "generate-reports", icon="⚡"),
]
