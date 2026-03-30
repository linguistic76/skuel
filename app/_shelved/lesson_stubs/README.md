# Shelved: Lesson UI Stub Routes

**Date shelved:** 2026-03-29
**Reason:** Placeholder routes serving static "will be implemented here" text. No UI links to any of these. Removing dead weight to keep lesson_ui.py focused on its 4 real routes.

## What was removed from `adapters/inbound/lesson_ui.py`

| Route | Purpose |
|-------|---------|
| `GET /lesson/discovery` | Placeholder discovery dashboard |
| `GET /lesson/analytics` | Placeholder analytics dashboard |
| `GET /lesson/graph` | Placeholder graph page |
| `GET /lesson/moc-nav` | MOC navigation fragment (unreferenced) |
| `GET /lesson/{uid}/edit` | Placeholder edit form |
| `GET /lesson/{uid}/graph` | Placeholder per-lesson graph |
| `GET /static/js/knowledge.js` | Inline JS served from route (anti-pattern, unreferenced) |

Also removed: `LessonUIComponents` class (single static method, never used outside the file).

## Restoration

Copy the route functions back into `lesson_ui.py` inside `create_lesson_ui_routes()` and re-register via `@rt()`.
