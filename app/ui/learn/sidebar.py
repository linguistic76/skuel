"""Learning workspace sidebar configuration.

4-item sidebar for the student workspace sub-pages:
Exercises (practice) → Submit (upload work) → My Submissions (track work) → Reports (feedback received)

Sidebar appears on /learn/submit, /learn/submissions, /learn/reports — NOT on /learn landing.
"""

from ui.patterns.sidebar import SidebarItem

LEARN_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Exercises", "/exercises", "exercises", icon="🏋️"),
    SidebarItem("Submit", "/learn/submit", "submit", icon="📤"),
    SidebarItem("My Submissions", "/learn/submissions", "submissions", icon="📝"),
    SidebarItem("Reports", "/learn/reports", "reports", icon="💬"),
]
