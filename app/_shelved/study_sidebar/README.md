# Shelved: Study Sidebar

Shelved 2026-03-29. Hub page pattern (MOC) replaces sidebar navigation.
Pages (`/submit`, `/submissions`, `/exercise-reports`, `/activity-reports`,
`/submit-activity-report`) now use `BasePage(STANDARD)`. Navigation via `/profile`
hub cards and `/transfer` dual-pane page.

## Files
- `layout.py` — `create_study_page()` wrapper using `SidebarPage`
- `sidebar.py` — `STUDY_SIDEBAR_ITEMS` (Submit, My Submissions, Exercise Reports, Activity Reports, Submit Activity Report)
