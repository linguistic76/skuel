# Shelved: Curriculum Sidebar

Shelved 2026-03-29. Hub page pattern (MOC) replaces sidebar navigation.
Pages (`/lessons`, `/learning-steps`, `/learning-paths`, `/exercises`) now use
`BasePage(STANDARD)`. Navigation via `/profile` hub cards and navbar.

## Files
- `layout.py` — `create_curriculum_page()` wrapper using `SidebarPage`
- `sidebar.py` — `CURRICULUM_SIDEBAR_ITEMS` (Lessons, Learning Steps, Learning Paths, Exercises)
