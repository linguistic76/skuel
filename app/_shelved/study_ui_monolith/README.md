# Shelved: study_ui.py Monolith (2026-03-29)

The monolithic `study_ui.py` (879 lines) has been decomposed into entity-typed files:
- `submissions_ui.py` — /submit, /submissions, /submissions/{uid}, HTMX fragments
- `exercise_reports_ui.py` — /exercise-reports, /reports/list
- `activity_reports_ui.py` — /activity-reports, /submit-activity-report, /activity-reports/detail

The `study_routes.py` orchestrator now wires the three decomposed files.
