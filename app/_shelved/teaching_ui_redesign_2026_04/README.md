# Shelved: Teaching UI Redesign (2026-04-03)

Code removed during the Teaching UI redesign that eliminated:
- Overview dashboard (replaced by Review Queue as root page)
- Exercise creation/edit forms (exercises created via ingestion)
- Learning sidebar link (KU Progress absorbed into student detail tab)
- Reports placeholder page

## Files

- `forms.py` — Exercise create/edit form component (`render_exercise_form`)
- `shelved_cards.py` — Dashboard/stat/exercise card components (`render_dashboard`, `render_stat_card`, `render_exercise_summary_card`)
- `shelved_types.py` — Removed type definitions (`TeachingDashboardStats`, `ExerciseSummary`)
- `shelved_requests.py` — Exercise create/update request models (`CreateTeachingExerciseRequest`, `UpdateTeachingExerciseRequest`)
