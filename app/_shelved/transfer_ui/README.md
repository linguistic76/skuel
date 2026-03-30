# Shelved: Transfer UI (2026-03-29)

The `/transfer` tabbed submission hub has been decomposed and absorbed into:
- `/profile` — Submissions section with tabs (My Submissions | Submit | Request Report)
- `submissions_ui.py` — Standalone submission pages
- `exercise_reports_ui.py` — Exercise report pages
- `activity_reports_ui.py` — Activity report pages

The "Transfer" concept (sending/receiving) was replaced by entity-typed routes.
