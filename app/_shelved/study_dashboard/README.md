# Shelved: Study Dashboard Landing Page

Shelved 2026-03-29. The `/study` hub landing page is replaced by `/profile`
as THE main hub. Profile cards link directly to domain pages (`/submissions`,
`/exercise-reports`, `/activity-reports`, etc.).

The `/study` route now redirects 301 to `/profile`.

## Files
- `dashboard.py` — `StudyDashboardView()` 6-card vertical stack with curriculum discovery links
